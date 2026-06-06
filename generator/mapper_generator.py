"""Gera o Mapper de cada tabela (implementa GenericMapper<E, D>).

- `toDto`  : lê a entidade (resolve id/nome dos relacionamentos).
- `toEntity`: monta a entidade e RESOLVE as FKs via repositórios injetados,
  garantindo que o relacionamento aponte para um registro existente.
"""
from __future__ import annotations

from generator.base import BaseGenerator, GeneratedFile
from generator.dto_model import build_dto_fields
from parser.model import Schema, Table


def _pascal(name: str) -> str:
    return name[:1].upper() + name[1:] if name else name


class MapperGenerator(BaseGenerator):
    layer = "mapper"

    def __init__(self, ctx, schema: Schema):
        super().__init__(ctx)
        self.schema = schema
        self._by_name = schema.by_name()

    def generate(self, table: Table) -> GeneratedFile:
        ctx = self.ctx
        fields = build_dto_fields(table, self.schema, ctx)
        entity = table.class_name
        dto = f"{entity}Dto"

        imports = {
            ctx.pkg("common") + ".GenericMapper",
            ctx.pkg("entity") + "." + entity,
            ctx.pkg("dto") + "." + dto,
            "org.springframework.stereotype.Component",
        }

        # Imports das entidades-alvo das FKs (para a referência rasa `new Alvo()`).
        for f in fields:
            if f.kind == "fk_id" and f.fk:
                imports.add(ctx.pkg("entity") + "." + f.fk.target_entity)
            if f.kind == "m2m" and f.m2m:
                imports.add(ctx.pkg("entity") + "." + f.m2m.target_entity)
                imports.add("java.util.List")
                if f.m2m.owning:
                    imports.add("java.util.ArrayList")

        to_dto_args = ",\n".join("                " + self._to_dto_expr(f) for f in fields)
        to_entity_lines = self._to_entity_lines(table, fields)

        imports_block = "\n".join(f"import {i};" for i in sorted(imports))
        parts = [
            f"package {self.package()};\n",
            imports_block,
            "",
            f"/**\n"
            f" * Mapeia {entity} <-> {dto}.\n"
            f" *\n"
            f" * <p>Em toEntity, as FKs são preenchidas apenas como REFERÊNCIA RASA (só o id).\n"
            f" * A resolução do relacionamento gerenciado é feita no Service\n"
            f" * ({entity}ServiceImpl.resolveRelationships).</p>\n"
            f" */",
            "@Component",
            f"public class {entity}Mapper implements GenericMapper<{entity}, {dto}> {{",
            "",
            "    @Override",
            f"    public {dto} toDto({entity} e) {{",
            "        if (e == null) {",
            "            return null;",
            "        }",
            f"        return new {dto}(",
            to_dto_args,
            "        );",
            "    }",
            "",
            "    @Override",
            f"    public {entity} toEntity({dto} dto) {{",
            "        if (dto == null) {",
            "            return null;",
            "        }",
            f"        {entity} e = new {entity}();",
        ]
        parts += [f"        {ln}" for ln in to_entity_lines]
        parts += [
            "        return e;",
            "    }",
            "}",
        ]
        content = "\n".join(parts) + "\n"
        return GeneratedFile(self.package(), f"{entity}Mapper", content)

    # ------------------------------------------------------------------ #
    def _to_dto_expr(self, f) -> str:
        if f.kind == "id":
            return "e.getId()"
        if f.kind == "created":
            return "e.getCriadoEm()"
        if f.kind == "updated":
            return "e.getAtualizadoEm()"
        if f.kind == "created_by":
            return "e.getCriadoPor()"
        if f.kind == "updated_by":
            return "e.getAtualizadoPor()"
        if f.kind == "fk_id":
            rel = _pascal(f.rel_field)
            return f"e.get{rel}() != null ? e.get{rel}().getId() : null"
        if f.kind == "fk_name":
            rel = _pascal(f.rel_field)
            return f"e.get{rel}() != null ? e.get{rel}().{f.display_getter}() : null"
        if f.kind == "m2m":
            coll = _pascal(f.m2m.field_name)
            tgt = f.m2m.target_entity
            return (f"e.get{coll}() != null ? e.get{coll}().stream()"
                    f".map({tgt}::getId).toList() : null")
        # scalar / enum
        return f"e.get{_pascal(f.column.java_field)}()"

    def _to_entity_lines(self, table: Table, fields) -> list[str]:
        """toEntity: scalares direto; FK como REFERÊNCIA RASA (só o id).

        O Service substitui a referência rasa pela entidade gerenciada
        (ver resolveRelationships no ServiceImpl).
        """
        lines: list[str] = []
        if table.supports_base_entity:
            lines.append("e.setId(dto.id());")
        for f in fields:
            if f.kind in ("id", "created", "updated", "created_by", "updated_by", "fk_name"):
                continue
            if f.kind == "fk_id":
                tgt = f.fk.target_entity
                rel = _pascal(f.rel_field)
                var = f.rel_field
                lines.append(f"if (dto.{f.name}() != null) {{")
                lines.append(f"    {tgt} {var} = new {tgt}();")
                lines.append(f"    {var}.setId(dto.{f.name}());")
                lines.append(f"    e.set{rel}({var});")
                lines.append("}")
            elif f.kind == "m2m":
                # Só o lado DONO é escrito (o inverso é mappedBy/somente leitura).
                if not f.m2m.owning:
                    continue
                tgt = f.m2m.target_entity
                coll = _pascal(f.m2m.field_name)
                # Nomes locais neutros (cada bloco tem escopo próprio em Java),
                # evita colisão entre a variável da lista e a do elemento.
                lines.append(f"if (dto.{f.name}() != null) {{")
                lines.append(f"    List<{tgt}> _list = new ArrayList<>();")
                lines.append(f"    for (Long _id : dto.{f.name}()) {{")
                lines.append(f"        {tgt} _ref = new {tgt}();")
                lines.append(f"        _ref.setId(_id);")
                lines.append(f"        _list.add(_ref);")
                lines.append("    }")
                lines.append(f"    e.set{coll}(_list);")
                lines.append("}")
            else:  # scalar / enum
                setter = _pascal(f.column.java_field)
                lines.append(f"e.set{setter}(dto.{f.name}());")
        return lines
