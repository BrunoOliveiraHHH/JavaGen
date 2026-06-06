"""Gera a interface Service de cada tabela (estende GenericService<E, D, F>)."""
from __future__ import annotations

from generator.base import BaseGenerator, GeneratedFile
from parser.model import Table


class ServiceGenerator(BaseGenerator):
    layer = "service"

    def generate(self, table: Table) -> GeneratedFile:
        ctx = self.ctx
        entity = table.class_name
        content = (
            f"package {self.package()};\n\n"
            f"import {ctx.pkg('common')}.GenericService;\n"
            f"import {ctx.pkg('dto')}.{entity}Dto;\n"
            f"import {ctx.pkg('entity')}.{entity};\n"
            f"import {ctx.pkg('filter')}.{entity}Filter;\n\n"
            f"/**\n * Serviço de {entity}. Adicione aqui métodos específicos do domínio.\n */\n"
            f"public interface {entity}Service "
            f"extends GenericService<{entity}, {entity}Dto, {entity}Filter> {{\n"
            f"}}\n"
        )
        return GeneratedFile(self.package(), f"{entity}Service", content)
