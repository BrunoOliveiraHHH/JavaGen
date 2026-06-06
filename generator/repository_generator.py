"""Gera o Repository de cada tabela (estende GenericRepository<E>)."""
from __future__ import annotations

from generator.base import BaseGenerator, GeneratedFile
from parser.model import Table


class RepositoryGenerator(BaseGenerator):
    layer = "repository"

    def generate(self, table: Table) -> GeneratedFile:
        ctx = self.ctx
        entity = table.class_name
        content = (
            f"package {self.package()};\n\n"
            f"import {ctx.pkg('common')}.GenericRepository;\n"
            f"import {ctx.pkg('entity')}.{entity};\n"
            f"import org.springframework.stereotype.Repository;\n\n"
            f"/**\n * Repositório de {entity}. Herda CRUD + Specifications do GenericRepository.\n */\n"
            f"@Repository\n"
            f"public interface {entity}Repository extends GenericRepository<{entity}> {{\n"
            f"}}\n"
        )
        return GeneratedFile(self.package(), f"{entity}Repository", content)
