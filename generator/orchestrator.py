"""Orquestra todos os geradores e produz a lista final de arquivos Java.

Emite uma vez as classes do pacote `common` e, por tabela, todas as camadas
(entity, enum, dto, mapper, filter, specification, repository, service,
service.impl, controller).
"""
from __future__ import annotations

from generator.base import GenContext, GeneratedFile
from generator.common_generator import CommonGenerator
from generator.controller_generator import ControllerGenerator
from generator.dto_generator import DtoGenerator
from generator.entity_generator import EntityGenerator
from generator.enum_generator import EnumGenerator
from generator.filter_generator import FilterGenerator
from generator.mapper_generator import MapperGenerator
from generator.repository_generator import RepositoryGenerator
from generator.service_generator import ServiceGenerator
from generator.service_impl_generator import ServiceImplGenerator
from generator.specification_generator import SpecificationGenerator
from parser.model import Schema


class ProjectGenerator:
    """Ponto único de geração: schema + contexto -> lista de GeneratedFile."""

    def __init__(self, ctx: GenContext, schema: Schema):
        self.ctx = ctx
        self.schema = schema
        # Geradores que dependem do schema (FKs, alvos de relacionamento).
        self._schema_aware = [
            EntityGenerator(ctx, schema),
            DtoGenerator(ctx, schema),
            MapperGenerator(ctx, schema),
            FilterGenerator(ctx, schema),
            SpecificationGenerator(ctx, schema),
        ]
        # Geradores simples (só dependem da tabela).
        self._simple = [
            RepositoryGenerator(ctx),
            ServiceGenerator(ctx),
            ServiceImplGenerator(ctx, schema),
            ControllerGenerator(ctx),
        ]
        self._enum_gen = EnumGenerator(ctx)

    def generate(self) -> list[GeneratedFile]:
        files: list[GeneratedFile] = []

        # 1) Classes comuns (uma vez).
        files.extend(CommonGenerator(self.ctx).generate_all())

        # 2) Por tabela, todas as camadas (tabelas de junção N:N são puladas).
        for table in self.schema.tables:
            if table.is_join_table:
                continue
            files.extend(self._enum_gen.generate(table))  # 0..N enums
            for gen in self._schema_aware:
                files.append(gen.generate(table))
            for gen in self._simple:
                files.append(gen.generate(table))

        return files

    def summary(self) -> dict:
        """Resumo para exibir na tela (nº de tabelas e arquivos)."""
        files = self.generate()
        return {
            "tables": len(self.schema.tables),
            "files": len(files),
            "table_names": [t.class_name for t in self.schema.tables],
        }
