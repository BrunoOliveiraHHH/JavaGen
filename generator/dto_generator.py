"""Gera o DTO (record unificado) de cada tabela.

O DTO é só dados — o mapeamento Entidade<->DTO fica no Mapper. FK é exposta como
`<rel>Id` (escrita) e, quando o alvo tem coluna de exibição, `<rel>Nome` (leitura).
"""
from __future__ import annotations

from generator.base import BaseGenerator, GeneratedFile
from generator.dto_model import build_dto_fields
from parser.model import Schema, Table


class DtoGenerator(BaseGenerator):
    layer = "dto"

    def __init__(self, ctx, schema: Schema):
        super().__init__(ctx)
        self.schema = schema

    def generate(self, table: Table) -> GeneratedFile:
        ctx = self.ctx
        fields = build_dto_fields(table, self.schema, ctx)

        imports: set[str] = set()
        for f in fields:
            if f.java_import:
                imports.add(f.java_import)

        class_name = f"{table.class_name}Dto"
        components = ",\n".join(f"        {f.java_type} {f.name}" for f in fields)

        schema_ann = ""
        if ctx.gen_openapi:
            imports.add("io.swagger.v3.oas.annotations.media.Schema")
            schema_ann = f'@Schema(name = "{class_name}", description = "DTO de {table.class_name}")\n'

        imports_block = "\n".join(f"import {i};" for i in sorted(imports))
        imports_block = (imports_block + "\n\n") if imports_block else ""

        content = (
            f"package {self.package()};\n\n"
            f"{imports_block}"
            f"/**\n * DTO unificado de {table.class_name} (entrada e saída).\n */\n"
            f"{schema_ann}"
            f"public record {class_name}(\n"
            f"{components}\n"
            f") {{\n}}\n"
        )
        return GeneratedFile(self.package(), class_name, content)
