"""Modelo dos campos de filtro + predicados de Specification por tipo de coluna.

Compartilhado entre filter_generator e specification_generator para que o record
do filtro e a montagem da Specification fiquem sempre alinhados.

Convenção (dirigida pelo tipo da coluna):
- String                 -> 1 campo  + LIKE (contains)
- Data/hora              -> 2 campos (Inicio/Fim) + BETWEEN
- Numérico               -> 1 campo  + EQUAL
- Boolean / Enum         -> 1 campo  + EQUAL
- FK (relacionamento)    -> 1 campo (<rel>Id) + EQUAL via join no id
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Optional

from generator.base import GenContext, emit_columns
from parser.model import Schema, Table

_TEMPORAL = {"LocalDate", "LocalDateTime", "LocalTime", "OffsetDateTime", "OffsetTime"}


@dataclass
class FilterField:
    name: str
    java_type: str
    java_import: Optional[str]


@dataclass
class FilterSpec:
    """Um critério de filtro: 1+ campos no record + a expressão da Specification."""
    fields: list[FilterField]
    predicate: str                       # ex.: GenericSpecification.like("numero", f.numero())
    imports: set[str] = dc_field(default_factory=set)


def build_filters(table: Table, schema: Schema, ctx: GenContext) -> list[FilterSpec]:
    """Gera os critérios de filtro da tabela, na ordem das colunas."""
    specs: list[FilterSpec] = []
    by_name = schema.by_name()

    columns = emit_columns(table, ctx, skip_audit=True) if table.supports_base_entity else table.columns

    for col in columns:
        attr = col.java_field  # nome do atributo na entidade

        # --- Foreign key -> EQUAL por join (quando o alvo é entidade conhecida) ---
        if col.is_foreign_key and col.fk:
            target = by_name.get(col.fk.ref_table.lower())
            rel = col.fk.relationship_field_name or attr
            if target is not None:
                specs.append(FilterSpec(
                    fields=[FilterField(f"{rel}Id", "Long", None)],
                    predicate=f'GenericSpecification.equalJoin("{rel}", "id", f.{rel}Id())',
                ))
            else:
                specs.append(FilterSpec(
                    fields=[FilterField(f"{attr}", "Long", None)],
                    predicate=f'GenericSpecification.equal("{attr}", f.{attr}())',
                ))
            continue

        # --- Enum -> EQUAL ---
        if ctx.gen_enums and col.enum_type_name:
            imp = ctx.pkg("enums") + "." + col.enum_type_name
            specs.append(FilterSpec(
                fields=[FilterField(attr, col.enum_type_name, imp)],
                predicate=f'GenericSpecification.equal("{attr}", f.{attr}())',
            ))
            continue

        jt = col.java_type

        # --- String -> LIKE ---
        if jt == "String":
            specs.append(FilterSpec(
                fields=[FilterField(attr, "String", None)],
                predicate=f'GenericSpecification.like("{attr}", f.{attr}())',
            ))
        # --- Data/hora -> BETWEEN (Inicio/Fim) ---
        elif jt in _TEMPORAL:
            specs.append(FilterSpec(
                fields=[
                    FilterField(f"{attr}Inicio", jt, col.java_import),
                    FilterField(f"{attr}Fim", jt, col.java_import),
                ],
                predicate=f'GenericSpecification.between("{attr}", f.{attr}Inicio(), f.{attr}Fim())',
            ))
        # --- Numérico / Boolean / Duration / UUID / outros -> EQUAL ---
        else:
            # Sempre usa o import do tipo da coluna (cobre Duration, UUID, BigDecimal...).
            specs.append(FilterSpec(
                fields=[FilterField(attr, jt, col.java_import)],
                predicate=f'GenericSpecification.equal("{attr}", f.{attr}())',
            ))

    return specs
