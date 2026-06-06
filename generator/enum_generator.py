"""Gera enums Java a partir de constraints CHECK col IN ('A','B',...).

Cada coluna com `enum_values` vira um enum no pacote `enums`. O nome do enum é
`<Entidade><Campo>` (ex.: ProdutoStatus). Para que o `@Enumerated(STRING)` funcione,
o nome de cada constante precisa ser igual ao valor armazenado no banco — por isso
mantemos o valor original quando ele já é um identificador Java válido.
"""
from __future__ import annotations

import re

from generator.base import GenContext, GeneratedFile
from parser.model import Table

_VALID_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _constant_name(value: str) -> str:
    """Converte o valor do banco numa constante de enum válida."""
    if _VALID_IDENT.match(value):
        return value  # mantém exatamente (necessário p/ @Enumerated STRING)
    # fallback: troca caracteres inválidos por _ e sobe para maiúsculas
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", value).upper()
    if cleaned and cleaned[0].isdigit():
        cleaned = "V_" + cleaned
    return cleaned or "VALOR"


class EnumGenerator:
    """Gera 0..N enums para uma tabela (um por coluna com CHECK IN)."""

    def __init__(self, ctx: GenContext):
        self.ctx = ctx

    def generate(self, table: Table) -> list[GeneratedFile]:
        if not self.ctx.gen_enums:
            return []
        files: list[GeneratedFile] = []
        for col in table.columns:
            if not col.enum_type_name or not col.enum_values:
                continue
            files.append(self._build(table, col))
        return files

    def _build(self, table: Table, col) -> GeneratedFile:
        pkg = self.ctx.pkg("enums")
        constants = []
        for v in col.enum_values:
            name = _constant_name(v)
            comment = "" if name == v else f"  // valor no banco: '{v}'"
            constants.append(f"    {name},{comment}")
        # troca a última vírgula por ponto-e-vírgula
        if constants:
            last = constants[-1]
            constants[-1] = last.replace(",", ";", 1)

        body = "\n".join(constants)
        content = (
            f"package {pkg};\n\n"
            f"/**\n * Valores possíveis para {table.name}.{col.name}\n"
            f" * (derivado de CHECK ... IN (...)).\n */\n"
            f"public enum {col.enum_type_name} {{\n\n"
            f"{body}\n"
            f"}}\n"
        )
        return GeneratedFile(pkg, col.enum_type_name, content)
