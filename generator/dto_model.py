"""Modelo dos campos do DTO, compartilhado entre dto_generator e mapper_generator.

Centralizar a ordem e a natureza dos campos garante que o record do DTO e o
construtor chamado pelo Mapper fiquem sempre em sincronia.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from generator.base import GenContext, emit_columns
from parser.model import Column, ForeignKey, ManyToMany, Schema, Table

# Colunas candidatas a "rótulo" de um relacionamento (resumo de leitura na FK).
_DISPLAY_COLUMNS = (
    "nome", "name", "descricao", "description", "titulo", "title",
    "razao_social", "label",
)


def display_column(table: Optional[Table]) -> Optional[Column]:
    """Devolve a melhor coluna de exibição da tabela (para o `<rel>Nome` da FK)."""
    if table is None:
        return None
    for col in table.columns:
        if col.name.lower() in _DISPLAY_COLUMNS:
            return col
    return None


@dataclass
class DtoField:
    """Um componente do record DTO."""
    name: str                       # nome do campo no DTO (camelCase)
    java_type: str                  # tipo Java
    java_import: Optional[str]      # import necessário (ou None)
    kind: str                       # id|created|updated|created_by|updated_by|scalar|enum|fk_id|fk_name|m2m
    column: Optional[Column] = None
    fk: Optional[ForeignKey] = None
    rel_field: Optional[str] = None  # nome do campo de relacionamento na entidade (ex.: "cliente")
    display_getter: Optional[str] = None  # getter de exibição no alvo (ex.: "getNome")
    m2m: Optional[ManyToMany] = None  # relacionamento N:N (lista de ids)


def _pascal(name: str) -> str:
    return name[:1].upper() + name[1:] if name else name


def build_dto_fields(table: Table, schema: Schema, ctx: GenContext) -> list[DtoField]:
    """Constrói a lista ordenada de campos do DTO da tabela."""
    fields: list[DtoField] = []
    by_name = schema.by_name()
    uses_base = table.supports_base_entity

    if uses_base:
        fields.append(DtoField("id", "Long", None, "id"))

    # Para tabelas sem BaseEntity, não pulamos PK/auditoria (não há herança).
    columns = emit_columns(table, ctx, skip_audit=True) if uses_base else table.columns

    for col in columns:
        if col.is_foreign_key and col.fk:
            target = by_name.get(col.fk.ref_table.lower())
            rel = col.fk.relationship_field_name or col.java_field
            if target is not None:
                # FK para entidade conhecida: id (escrita) + nome (leitura, se houver).
                fields.append(DtoField(f"{rel}Id", "Long", None, "fk_id",
                                       column=col, fk=col.fk, rel_field=rel))
                disp = display_column(target)
                if disp is not None:
                    fields.append(DtoField(f"{rel}Nome", disp.java_type, disp.java_import,
                                           "fk_name", column=col, fk=col.fk, rel_field=rel,
                                           display_getter="get" + _pascal(disp.java_field)))
            else:
                # FK para tabela fora do schema: cai para o id escalar.
                fields.append(DtoField(f"{col.java_field}", col.java_type, col.java_import,
                                       "scalar", column=col))
        elif ctx.gen_enums and col.enum_type_name:
            fields.append(DtoField(col.java_field, col.enum_type_name,
                                   ctx.pkg("enums") + "." + col.enum_type_name, "enum", column=col))
        else:
            fields.append(DtoField(col.java_field, col.java_type, col.java_import, "scalar", column=col))

    # Relacionamentos N:N: lista de ids do alvo (ex.: perfisIds).
    for m in table.many_to_many:
        fields.append(DtoField(f"{m.field_name}Ids", "List<Long>", "java.util.List", "m2m", m2m=m))

    if uses_base:
        fields.append(DtoField("criadoEm", "LocalDateTime", "java.time.LocalDateTime", "created"))
        fields.append(DtoField("atualizadoEm", "LocalDateTime", "java.time.LocalDateTime", "updated"))
        if ctx.audit_user:
            fields.append(DtoField("criadoPor", "String", None, "created_by"))
            fields.append(DtoField("atualizadoPor", "String", None, "updated_by"))

    return fields
