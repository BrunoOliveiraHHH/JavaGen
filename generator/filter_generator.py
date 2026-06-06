"""Gera o Filter (record de dados puro) de cada tabela.

Os campos são derivados do tipo de cada coluna (ver generator/filtering.py).
O record não tem lógica de predicado — isso fica na Specification, separada.
"""
from __future__ import annotations

from generator.base import BaseGenerator, GeneratedFile
from generator.filtering import build_filters
from parser.model import Schema, Table


class FilterGenerator(BaseGenerator):
    layer = "filter"

    def __init__(self, ctx, schema: Schema):
        super().__init__(ctx)
        self.schema = schema

    def generate(self, table: Table) -> GeneratedFile:
        specs = build_filters(table, self.schema, self.ctx)

        imports: set[str] = set()
        comps: list[str] = []
        for spec in specs:
            for fld in spec.fields:
                comps.append(f"        {fld.java_type} {fld.name}")
                if fld.java_import:
                    imports.add(fld.java_import)

        class_name = f"{table.class_name}Filter"
        imports_block = "\n".join(f"import {i};" for i in sorted(imports))
        imports_block = (imports_block + "\n\n") if imports_block else ""

        if comps:
            components = ",\n".join(comps)
            record_body = f"public record {class_name}(\n{components}\n) {{\n}}\n"
        else:
            # Tabela sem campos filtráveis: record vazio (ainda válido).
            record_body = f"public record {class_name}() {{\n}}\n"

        content = (
            f"package {self.package()};\n\n"
            f"{imports_block}"
            f"/**\n * Filtros de busca de {table.class_name} (todos opcionais).\n */\n"
            f"{record_body}"
        )
        return GeneratedFile(self.package(), class_name, content)
