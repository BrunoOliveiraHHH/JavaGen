"""Gera a Specification (classe separada) de cada tabela.

`build(XFilter)` monta a Specification encadeando os helpers de GenericSpecification,
escolhendo o predicado pelo tipo de cada campo (ver generator/filtering.py).
"""
from __future__ import annotations

from generator.base import BaseGenerator, GeneratedFile
from generator.filtering import build_filters
from parser.model import Schema, Table


class SpecificationGenerator(BaseGenerator):
    layer = "specification"

    def __init__(self, ctx, schema: Schema):
        super().__init__(ctx)
        self.schema = schema

    def generate(self, table: Table) -> GeneratedFile:
        ctx = self.ctx
        specs = build_filters(table, self.schema, ctx)
        entity = table.class_name
        flt = f"{entity}Filter"
        class_name = f"{entity}Specification"

        imports = {
            ctx.pkg("common") + ".GenericSpecification",
            ctx.pkg("entity") + "." + entity,
            ctx.pkg("filter") + "." + flt,
            "org.springframework.data.jpa.domain.Specification",
        }

        lines = [f"        Specification<{entity}> spec = (root, query, cb) -> cb.conjunction();"]
        for spec in specs:
            lines.append(f"        spec = spec.and({spec.predicate});")
        lines.append("        return spec;")
        body = "\n".join(lines)

        imports_block = "\n".join(f"import {i};" for i in sorted(imports))
        content = (
            f"package {self.package()};\n\n"
            f"{imports_block}\n\n"
            f"/**\n * Monta a Specification de busca de {entity} a partir do {flt}.\n */\n"
            f"public final class {class_name} {{\n\n"
            f"    private {class_name}() {{\n"
            f"        // Classe utilitária: não deve ser instanciada.\n"
            f"    }}\n\n"
            f"    public static Specification<{entity}> build({flt} f) {{\n"
            f"{body}\n"
            f"    }}\n"
            f"}}\n"
        )
        return GeneratedFile(self.package(), class_name, content)
