"""Parser de SQL DDL -> Schema.

Estratégia: tenta `sqlglot` (AST, dialeto-aware) e, em qualquer falha ou
resultado incompleto, cai para um tokenizador regex próprio com balanceamento
de parênteses. Ambos produzem o mesmo modelo (`Schema`).
"""
from __future__ import annotations

import re
from typing import Iterator, Optional

from parser.model import (
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    ManyToMany,
    OneToMany,
    Schema,
    Table,
)
from parser.type_mapper import map_type
from utils.naming import (
    class_name_for_table,
    derive_fk_field,
    pluralize,
    snake_to_camel,
    to_pascal_case,
)


class SqlParseError(Exception):
    """Erro amigável de SQL inválido (mensagem em PT, exibida na tela)."""


# --------------------------------------------------------------------------- #
# Helpers de texto (compartilhados pelo fallback regex)
# --------------------------------------------------------------------------- #
def strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n]*", " ", sql)
    return sql


def split_top_level(body: str, sep: str = ",") -> list[str]:
    """Divide por `sep` só no nível 0 de parênteses, ignorando aspas."""
    parts, depth, buf = [], 0, []
    in_s = in_d = False
    for ch in body:
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        if not in_s and not in_d:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == sep and depth == 0:
                parts.append("".join(buf).strip())
                buf = []
                continue
        buf.append(ch)
    if buf:
        parts.append("".join(buf).strip())
    return [p for p in parts if p]


_CREATE_RE = re.compile(
    r"CREATE\s+(?:GLOBAL\s+|LOCAL\s+|TEMP(?:ORARY)?\s+|UNLOGGED\s+)*TABLE\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>[\w\".`]+)\s*\(",
    re.IGNORECASE,
)

_CREATE_INDEX_RE = re.compile(
    r"CREATE\s+(?P<uniq>UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?P<name>[\w\".`]+)\s+ON\s+(?P<tbl>[\w\".`]+)\s*(?:USING\s+\w+\s*)?\(\s*(?P<cols>[^)]+)\)",
    re.IGNORECASE,
)


def extract_create_bodies(script: str) -> Iterator[tuple[str, str]]:
    """Itera (nome_tabela, corpo) achando o ')' que fecha o '(' por profundidade."""
    for m in _CREATE_RE.finditer(script):
        start = m.end()
        depth = 1
        i = start
        in_s = in_d = False
        while i < len(script) and depth > 0:
            c = script[i]
            if c == "'" and not in_d:
                in_s = not in_s
            elif c == '"' and not in_s:
                in_d = not in_d
            elif not in_s and not in_d:
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
            i += 1
        yield m.group("name"), script[start: i - 1]


# --------------------------------------------------------------------------- #
# Regexes de constraint (fallback)
# --------------------------------------------------------------------------- #
_COL_TYPE_RE = re.compile(
    r'^\s*(?P<name>"[^"]+"|`[^`]+`|\w+)\s+'
    r"(?P<type>\w+(?:\s+PRECISION|\s+VARYING)?(?:\s*\([^)]*\))?"
    r"(?:\s+WITH(?:OUT)?\s+TIME\s+ZONE)?(?:\[\])?)",
    re.IGNORECASE,
)
_NOT_NULL_RE = re.compile(r"\bNOT\s+NULL\b", re.IGNORECASE)
_PK_INLINE_RE = re.compile(r"\bPRIMARY\s+KEY\b", re.IGNORECASE)
_UNIQUE_INLINE_RE = re.compile(r"\bUNIQUE\b", re.IGNORECASE)
_AUTOINC_RE = re.compile(r"\b(AUTO_INCREMENT|AUTOINCREMENT|IDENTITY|GENERATED\s+(ALWAYS|BY\s+DEFAULT)\s+AS\s+IDENTITY)\b", re.IGNORECASE)
_DEFAULT_RE = re.compile(r"\bDEFAULT\s+(?P<val>'[^']*'|\"[^\"]*\"|\w+\s*\([^)]*\)|[^\s,]+)", re.IGNORECASE)
_INLINE_FK_RE = re.compile(
    r"\bREFERENCES\s+(?P<tbl>[\w\".`]+)\s*(?:\(\s*(?P<col>[\w\"`]+)\s*\))?",
    re.IGNORECASE,
)
_COL_CHECK_RE = re.compile(r"\bCHECK\s*\((?P<expr>.+)\)", re.IGNORECASE | re.DOTALL)
_ON_DELETE_RE = re.compile(r"\bON\s+DELETE\s+(?P<a>CASCADE|SET\s+NULL|SET\s+DEFAULT|RESTRICT|NO\s+ACTION)", re.IGNORECASE)
_ON_UPDATE_RE = re.compile(r"\bON\s+UPDATE\s+(?P<a>CASCADE|SET\s+NULL|SET\s+DEFAULT|RESTRICT|NO\s+ACTION)", re.IGNORECASE)

_TABLE_PK_RE = re.compile(r"^\s*(?:CONSTRAINT\s+[\w\"`]+\s+)?PRIMARY\s+KEY\s*\(\s*(?P<cols>[^)]+)\)", re.IGNORECASE)
_TABLE_FK_RE = re.compile(
    r"^\s*(?:CONSTRAINT\s+(?P<cname>[\w\"`]+)\s+)?FOREIGN\s+KEY\s*\(\s*(?P<cols>[^)]+)\)\s*"
    r"REFERENCES\s+(?P<tbl>[\w\".`]+)\s*\(\s*(?P<refcols>[^)]+)\)",
    re.IGNORECASE,
)
_TABLE_UNIQUE_RE = re.compile(r"^\s*(?:CONSTRAINT\s+[\w\"`]+\s+)?UNIQUE\s*\(\s*(?P<cols>[^)]+)\)", re.IGNORECASE)
_TABLE_CHECK_RE = re.compile(r"^\s*(?:CONSTRAINT\s+(?P<cname>[\w\"`]+)\s+)?CHECK\s*\((?P<expr>.+)\)\s*$", re.IGNORECASE | re.DOTALL)

_IN_VALUES_RE = re.compile(r"IN\s*\(\s*(?P<vals>[^)]+)\)", re.IGNORECASE)


def _unquote(token: str) -> str:
    token = token.strip().strip('"').strip("`")
    if "." in token:
        token = token.split(".")[-1].strip('"').strip("`")
    return token


def _split_cols(s: str) -> list[str]:
    return [_unquote(c) for c in s.split(",") if c.strip()]


def _extract_enum(col_name: str, expr: Optional[str]) -> Optional[list[str]]:
    """Extrai valores de `<col> IN ('A','B',...)`, exigindo que a coluna preceda
    o IN (com fronteira de palavra) — evita casar nomes como substring."""
    if not expr or not col_name:
        return None
    m = re.search(
        r"\b" + re.escape(col_name) + r"\b\s+IN\s*\(\s*(?P<vals>[^)]+)\)",
        expr,
        re.IGNORECASE,
    )
    if not m:
        return None
    vals = [v.strip().strip("'").strip('"') for v in m.group("vals").split(",")]
    vals = [v for v in vals if v]
    return vals or None


# --------------------------------------------------------------------------- #
# Fallback regex
# --------------------------------------------------------------------------- #
def _parse_column_regex(defn: str, dialect: str) -> Optional[Column]:
    m = _COL_TYPE_RE.match(defn)
    if not m:
        return None
    name = _unquote(m.group("name"))
    raw_type = re.sub(r"\s+", " ", m.group("type").strip())
    rest = defn[m.end():]

    jt = map_type(raw_type, dialect)
    col = Column(
        name=name,
        raw_sql_type=raw_type,
        java_type=jt.java_type,
        java_import=jt.java_import,
        length=jt.length,
        precision=jt.precision,
        scale=jt.scale,
        type_unknown=jt.unknown,
    )

    if _NOT_NULL_RE.search(rest):
        col.nullable = False
    if _PK_INLINE_RE.search(rest):
        col.is_pk = True
        col.nullable = False
    if _UNIQUE_INLINE_RE.search(rest):
        col.unique = True
    if _AUTOINC_RE.search(defn) or "SERIAL" in raw_type.upper():
        col.is_auto_increment = True
    dm = _DEFAULT_RE.search(rest)
    if dm:
        col.default = dm.group("val")
    cm = _COL_CHECK_RE.search(rest)
    if cm:
        col.check = cm.group("expr").strip()
        col.enum_values = _extract_enum(name, col.check)

    fm = _INLINE_FK_RE.search(rest)
    if fm:
        fk = ForeignKey(
            column=name,
            ref_table=_unquote(fm.group("tbl")),
            ref_column=_unquote(fm.group("col")) if fm.group("col") else "id",
        )
        odm = _ON_DELETE_RE.search(rest)
        oum = _ON_UPDATE_RE.search(rest)
        if odm:
            fk.on_delete = re.sub(r"\s+", " ", odm.group("a").upper())
        if oum:
            fk.on_update = re.sub(r"\s+", " ", oum.group("a").upper())
        col.is_foreign_key = True
        col.fk = fk
    return col


def _parse_table_regex(raw_name: str, body: str, dialect: str) -> Table:
    schema = None
    full = _unquote(raw_name)
    if "." in raw_name.replace('"', "").replace("`", ""):
        schema = raw_name.replace('"', "").replace("`", "").split(".")[0]
    table = Table(name=full, schema=schema)

    for defn in split_top_level(body):
        upper = defn.upper().lstrip()
        if _TABLE_FK_RE.match(defn):
            mm = _TABLE_FK_RE.match(defn)
            cols = _split_cols(mm.group("cols"))
            refcols = _split_cols(mm.group("refcols"))
            fk = ForeignKey(
                column=cols[0] if cols else "",
                ref_table=_unquote(mm.group("tbl")),
                ref_column=refcols[0] if refcols else "id",
                name=_unquote(mm.group("cname")) if mm.group("cname") else None,
                columns=cols,
                ref_columns=refcols,
            )
            odm = _ON_DELETE_RE.search(defn)
            oum = _ON_UPDATE_RE.search(defn)
            if odm:
                fk.on_delete = re.sub(r"\s+", " ", odm.group("a").upper())
            if oum:
                fk.on_update = re.sub(r"\s+", " ", oum.group("a").upper())
            table.foreign_keys.append(fk)
        elif _TABLE_PK_RE.match(defn):
            table.primary_key = _split_cols(_TABLE_PK_RE.match(defn).group("cols"))
        elif _TABLE_UNIQUE_RE.match(defn) and upper.startswith(("UNIQUE", "CONSTRAINT")):
            table.unique_constraints.append(_split_cols(_TABLE_UNIQUE_RE.match(defn).group("cols")))
        elif _TABLE_CHECK_RE.match(defn) and (upper.startswith("CHECK") or "CHECK" in upper.split("(")[0]):
            mm = _TABLE_CHECK_RE.match(defn)
            table.check_constraints.append(
                CheckConstraint(name=_unquote(mm.group("cname")) if mm.group("cname") else None,
                                expression=mm.group("expr").strip())
            )
        else:
            col = _parse_column_regex(defn, dialect)
            if col:
                table.columns.append(col)
    return table


def _parse_with_regex(script: str, dialect: str) -> Schema:
    script = strip_comments(script)
    schema = Schema()
    for raw_name, body in extract_create_bodies(script):
        schema.tables.append(_parse_table_regex(raw_name, body, dialect))
    _attach_indexes_regex(schema, script)
    return schema


def _attach_indexes_regex(schema: Schema, script: str) -> None:
    by_name = schema.by_name()
    for m in _CREATE_INDEX_RE.finditer(script):
        tbl = by_name.get(_unquote(m.group("tbl")).lower())
        if not tbl:
            continue
        tbl.indexes.append(Index(
            name=_unquote(m.group("name")),
            columns=_split_cols(m.group("cols")),
            unique=bool(m.group("uniq")),
        ))


# --------------------------------------------------------------------------- #
# sqlglot (primário)
# --------------------------------------------------------------------------- #
def _sqlglot_type_str(coldef, dialect: str) -> str:
    kind = coldef.args.get("kind")
    if kind is None:
        return "TEXT"
    try:
        return kind.sql(dialect=dialect)
    except Exception:
        return kind.sql()


def _ref_table_and_col(ref):
    target = ref.this
    if target is None:
        return "", "id"
    if type(target).__name__ == "Schema":
        tbl = target.this
        cols = [c.name for c in target.expressions] if target.expressions else []
        return (tbl.name if tbl else ""), (cols[0] if cols else "id")
    return (target.name if hasattr(target, "name") else ""), "id"


def _ref_actions(ref):
    on_delete = on_update = None
    opts = ref.args.get("options") or []
    for o in opts:
        s = str(o).upper()
        dm = _ON_DELETE_RE.search(s)
        um = _ON_UPDATE_RE.search(s)
        if dm:
            on_delete = re.sub(r"\s+", " ", dm.group("a").upper())
        if um:
            on_update = re.sub(r"\s+", " ", um.group("a").upper())
    return on_delete, on_update


def _parse_with_sqlglot(script: str, dialect: str) -> Schema:
    import sqlglot
    from sqlglot import exp

    schema = Schema()
    statements = sqlglot.parse(script, read=dialect)
    indexes: list = []

    for stmt in statements:
        if stmt is None:
            continue
        if isinstance(stmt, exp.Create) and (stmt.kind or "").upper() == "TABLE":
            schema.tables.append(_table_from_ast(stmt, dialect, exp))
        elif isinstance(stmt, exp.Create) and (stmt.kind or "").upper() == "INDEX":
            indexes.append(stmt)

    _attach_indexes_ast(schema, indexes, exp)
    return schema


def _table_from_ast(node, dialect: str, exp) -> Table:
    schema_expr = node.this  # exp.Schema
    table_ident = schema_expr.this if hasattr(schema_expr, "this") else schema_expr
    name = table_ident.name
    db = getattr(table_ident, "db", None) or None
    table = Table(name=name, schema=db)

    defs = schema_expr.expressions if hasattr(schema_expr, "expressions") else []
    for d in defs:
        tname = type(d).__name__
        if isinstance(d, exp.ColumnDef):
            table.columns.append(_column_from_ast(d, dialect, exp))
        elif isinstance(d, exp.PrimaryKey):
            table.primary_key = [c.name for c in d.expressions]
        elif isinstance(d, exp.ForeignKey):
            table.foreign_keys.append(_table_fk_from_ast(d, exp))
        elif tname in ("UniqueColumnConstraint", "Unique"):
            cols = _constraint_columns(d)
            if cols:
                table.unique_constraints.append(cols)
        elif tname in ("Check", "CheckColumnConstraint"):
            expr = d.this.sql() if d.this else ""
            table.check_constraints.append(CheckConstraint(name=None, expression=expr))
        elif tname == "Constraint":
            _classify_named_constraint(d, table, exp)
    return table


def _constraint_columns(node) -> list[str]:
    cols = []
    for c in (node.expressions or []):
        if hasattr(c, "name") and c.name:
            cols.append(c.name)
    if not cols and node.this is not None and hasattr(node.this, "name"):
        cols.append(node.this.name)
    return cols


def _classify_named_constraint(node, table: Table, exp) -> None:
    """CONSTRAINT nomeada genérica (sqlglot às vezes encapsula em exp.Constraint)."""
    for child in node.expressions or []:
        tname = type(child).__name__
        if isinstance(child, exp.PrimaryKey):
            table.primary_key = [c.name for c in child.expressions]
        elif isinstance(child, exp.ForeignKey):
            table.foreign_keys.append(_table_fk_from_ast(child, exp))
        elif tname in ("UniqueColumnConstraint", "Unique"):
            cols = _constraint_columns(child)
            if cols:
                table.unique_constraints.append(cols)
        elif tname in ("Check", "CheckColumnConstraint"):
            table.check_constraints.append(
                CheckConstraint(name=node.this.name if node.this else None,
                                expression=child.this.sql() if child.this else "")
            )


def _table_fk_from_ast(node, exp) -> ForeignKey:
    cols = [c.name for c in (node.expressions or [])]
    ref = node.args.get("reference")
    ref_table, ref_col = ("", "id")
    on_delete = on_update = None
    if ref is not None:
        ref_table, ref_col = _ref_table_and_col(ref)
        on_delete, on_update = _ref_actions(ref)
    return ForeignKey(
        column=cols[0] if cols else "",
        ref_table=ref_table,
        ref_column=ref_col,
        on_delete=on_delete,
        on_update=on_update,
        columns=cols,
        ref_columns=[ref_col],
    )


def _column_from_ast(coldef, dialect: str, exp) -> Column:
    name = coldef.name
    raw_type = _sqlglot_type_str(coldef, dialect)
    jt = map_type(raw_type, dialect)
    col = Column(
        name=name,
        raw_sql_type=raw_type,
        java_type=jt.java_type,
        java_import=jt.java_import,
        length=jt.length,
        precision=jt.precision,
        scale=jt.scale,
        type_unknown=jt.unknown,
    )

    for cons in (coldef.constraints or []):
        kind = cons.kind
        kname = type(kind).__name__
        if kname == "NotNullColumnConstraint":
            # allow_null=True significa "NULL" explícito; senão é NOT NULL
            col.nullable = bool(kind.args.get("allow_null"))
        elif kname == "PrimaryKeyColumnConstraint":
            col.is_pk = True
            col.nullable = False
        elif kname == "UniqueColumnConstraint":
            col.unique = True
        elif kname == "DefaultColumnConstraint":
            col.default = kind.this.sql() if kind.this else None
        elif kname == "CheckColumnConstraint":
            col.check = kind.this.sql() if kind.this else None
            col.enum_values = _extract_enum(name, col.check)
        elif kname in ("GeneratedAsIdentityColumnConstraint", "AutoIncrementColumnConstraint"):
            col.is_auto_increment = True
        elif kname == "Reference":
            ref_table, ref_col = _ref_table_and_col(kind)
            on_delete, on_update = _ref_actions(kind)
            col.is_foreign_key = True
            col.fk = ForeignKey(column=name, ref_table=ref_table, ref_column=ref_col,
                                on_delete=on_delete, on_update=on_update)

    if "SERIAL" in raw_type.upper():
        col.is_auto_increment = True
    return col


def _attach_indexes_ast(schema: Schema, index_nodes, exp) -> None:
    by_name = schema.by_name()
    for node in index_nodes:
        try:
            this = node.this  # exp.Index
            idx_name = this.name if hasattr(this, "name") else ""
            tbl_expr = node.args.get("table") or (this.args.get("table") if hasattr(this, "args") else None)
            tname = tbl_expr.name if tbl_expr is not None and hasattr(tbl_expr, "name") else None
            params = this.args.get("params") if hasattr(this, "args") else None
            cols = []
            if params is not None:
                for c in (params.args.get("columns") or []):
                    cols.append(c.name if hasattr(c, "name") else str(c))
            unique = bool(node.args.get("unique"))
            tbl = by_name.get((tname or "").lower())
            if tbl and idx_name:
                tbl.indexes.append(Index(name=idx_name, columns=[c for c in cols if c], unique=unique))
        except Exception:
            continue


# --------------------------------------------------------------------------- #
# Pós-processamento (comum aos dois caminhos)
# --------------------------------------------------------------------------- #
def _finalize(schema: Schema) -> None:
    by_name = schema.by_name()
    for table in schema.tables:
        # marca is_pk a partir de PK de tabela
        for pk_col in table.primary_key:
            col = table.column(pk_col)
            if col:
                col.is_pk = True
                col.nullable = False
        if not table.primary_key:
            table.primary_key = [c.name for c in table.columns if c.is_pk]

        # liga FKs de tabela às colunas + deriva relacionamento
        for fk in table.foreign_keys:
            col = table.column(fk.column)
            if col:
                col.is_foreign_key = True
                col.fk = fk
        # FKs inline já estão nas colunas; garante que estão na lista da tabela
        for col in table.columns:
            if col.fk and col.fk not in table.foreign_keys:
                table.foreign_keys.append(col.fk)

        _derive_relationships(table)
        _assign_enum_names(table)

    _detect_many_to_many(schema, by_name)
    _infer_inverse(schema, by_name)


def _derive_relationships(table: Table) -> None:
    used: set[str] = set()
    for fk in table.foreign_keys:
        if not fk.column:
            continue
        field = derive_fk_field(fk.column)
        if field in used:  # colisão -> usa o nome completo da coluna
            field = snake_to_camel(fk.column)
        used.add(field)
        fk.relationship_field_name = field
        fk.target_entity = class_name_for_table(fk.ref_table)


def _assign_enum_names(table: Table) -> None:
    # Extrai enums também de CHECK de tabela (ex.: CONSTRAINT ... CHECK (col IN (...))).
    for chk in table.check_constraints:
        for col in table.columns:
            if col.enum_values:
                continue
            vals = _extract_enum(col.name, chk.expression)
            if vals:
                col.enum_values = vals
    for col in table.columns:
        if col.enum_values and not col.is_foreign_key:
            col.enum_type_name = table.class_name + to_pascal_case(col.name)


def _detect_many_to_many(schema: Schema, by_name: dict) -> None:
    """Detecta tabelas de junção puras (exatamente 2 colunas, ambas FK) e gera
    o relacionamento N:N nas duas entidades referenciadas. A tabela de junção em
    si é marcada como `is_join_table` e NÃO vira entidade.

    Tabelas com colunas extras (além das 2 FKs) NÃO são consideradas junção pura:
    permanecem como entidade de associação (dois @ManyToOne)."""
    for t in schema.tables:
        if len(t.foreign_keys) != 2 or len(t.columns) != 2:
            continue
        if not all(c.is_foreign_key for c in t.columns):
            continue
        fk_a, fk_b = t.foreign_keys[0], t.foreign_keys[1]
        a = by_name.get(fk_a.ref_table.lower())
        b = by_name.get(fk_b.ref_table.lower())
        if not a or not b or a is b:
            continue

        t.is_join_table = True
        a_field = pluralize(snake_to_camel(b.name))  # ex.: usuario.perfis
        b_field = pluralize(snake_to_camel(a.name))  # ex.: perfil.usuarios

        # Lado dono = A (primeira FK), com @JoinTable.
        a.many_to_many.append(ManyToMany(
            field_name=a_field, target_entity=b.class_name, target_table=b.name,
            owning=True, join_table=t.name,
            join_column=fk_a.column, inverse_join_column=fk_b.column,
        ))
        # Lado inverso = B, com mappedBy.
        b.many_to_many.append(ManyToMany(
            field_name=b_field, target_entity=a.class_name, target_table=a.name,
            owning=False, mapped_by=a_field,
        ))


def _infer_inverse(schema: Schema, by_name: dict) -> None:
    for child in schema.tables:
        if child.is_join_table:
            continue  # FKs da junção viram @ManyToMany, não @OneToMany
        for fk in child.foreign_keys:
            parent = by_name.get(fk.ref_table.lower())
            if not parent or parent is child:
                continue
            parent.one_to_many.append(OneToMany(
                child_table=child.name,
                child_entity=child.class_name,
                mapped_by=fk.relationship_field_name or snake_to_camel(fk.column),
                collection_field_name=pluralize(snake_to_camel(child.name)),
            ))


# --------------------------------------------------------------------------- #
# Entrada pública
# --------------------------------------------------------------------------- #
def _is_complete(schema: Schema) -> bool:
    return bool(schema.tables) and all(t.columns for t in schema.tables)


def parse_sql(text: str, dialect: str = "postgres") -> Schema:
    if not text or not text.strip():
        raise SqlParseError("Nenhum SQL informado.")

    schema: Optional[Schema] = None
    try:
        schema = _parse_with_sqlglot(text, dialect)
        if not _is_complete(schema):
            schema = None
    except ImportError:
        schema = None
    except Exception:
        schema = None

    if schema is None:
        schema = _parse_with_regex(text, dialect)

    if not schema.tables:
        raise SqlParseError("Nenhum CREATE TABLE encontrado no SQL informado.")

    _finalize(schema)
    return schema
