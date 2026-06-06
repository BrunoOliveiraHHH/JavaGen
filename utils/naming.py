"""Conversões de nomenclatura entre SQL (snake_case) e Java (camelCase/PascalCase).

Funções puras, sem dependências externas. Acentos são removidos dos identificadores
Java (o nome original da coluna/tabela é preservado nas anotações @Column/@Table).
"""
import re
import unicodedata


def _strip_accents(text: str) -> str:
    """Remove acentos: 'bônus' -> 'bonus', 'ação' -> 'acao'."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )

# Prefixos comuns de tabela que removemos do nome da classe (tb_user -> User).
_TABLE_PREFIXES = ("tb_", "tbl_", "tab_")

# Sufixos de coluna FK removidos ao derivar o nome do campo objeto.
_FK_SUFFIXES = ("_id", "_fk", "_key", "_cod", "_codigo")
_FK_PREFIXES = ("id_", "fk_")


def _clean(token: str) -> str:
    """Remove aspas, schema-qualificação e acentos do identificador."""
    token = token.strip().strip('"').strip("`").strip("[").strip("]")
    if "." in token:  # public.tabela -> tabela
        token = token.split(".")[-1]
    return _strip_accents(token)


def snake_to_camel(snake: str) -> str:
    """created_at -> createdAt"""
    parts = [p for p in _clean(snake).split("_") if p]
    if not parts:
        return snake
    return parts[0].lower() + "".join(w.capitalize() for w in parts[1:])


def to_pascal_case(snake: str) -> str:
    """item_pedido -> ItemPedido"""
    parts = [p for p in _clean(snake).split("_") if p]
    return "".join(w.capitalize() for w in parts) or snake


def strip_table_prefix(name: str) -> str:
    """tb_user -> user (preserva o resto)."""
    low = _clean(name).lower()
    for pref in _TABLE_PREFIXES:
        if low.startswith(pref) and len(low) > len(pref):
            return _clean(name)[len(pref):]
    return _clean(name)


def class_name_for_table(name: str) -> str:
    """tb_item_pedido -> ItemPedido"""
    return to_pascal_case(strip_table_prefix(name))


def derive_fk_field(fk_column: str) -> str:
    """cliente_id -> cliente ; id_produto -> produto ; fornecedor_fk -> fornecedor"""
    base = _clean(fk_column).lower()
    for suf in _FK_SUFFIXES:
        if base.endswith(suf) and len(base) > len(suf):
            base = base[: -len(suf)]
            break
    else:
        for pre in _FK_PREFIXES:
            if base.startswith(pre) and len(base) > len(pre):
                base = base[len(pre):]
                break
    return snake_to_camel(base)


def pluralize(word: str) -> str:
    """Pluralização simples PT/EN para nomes de coleção (heurística)."""
    if not word:
        return word
    if word.endswith(("s", "x", "z")):
        return word
    if word.endswith("m"):
        return word[:-1] + "ns"   # ex.: homem -> homens
    if word.endswith("il"):
        return word[:-2] + "is"   # ex.: perfil -> perfis
    if word.endswith("l"):
        return word[:-1] + "is"   # ex.: animal -> animais, papel -> papeis
    if word.endswith("ão"):
        return word[:-2] + "oes"  # ex.: cao -> coes (sem acento)
    return word + "s"


def package_to_path(package: str) -> str:
    """com.sinapsis.sistema -> com/sinapsis/sistema"""
    return package.replace(".", "/")


_PKG_RE = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)*$")


def is_valid_package(package: str) -> bool:
    """Valida um nome de pacote Java (minúsculo, segmentos separados por ponto)."""
    return bool(_PKG_RE.match(package or ""))
