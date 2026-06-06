"""Modelo de dados produzido pelo parser e consumido pelos geradores.

O parser só CAPTURA metadados; quem decide anotações JPA é o gerador.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from utils.naming import (
    class_name_for_table,
    snake_to_camel,
)


@dataclass
class CheckConstraint:
    name: Optional[str]
    expression: str


@dataclass
class Index:
    name: str
    columns: list[str] = field(default_factory=list)
    unique: bool = False
    where: Optional[str] = None


@dataclass
class ForeignKey:
    column: str                       # coluna local (FK simples)
    ref_table: str                    # tabela referenciada (sem schema)
    ref_column: str = "id"
    on_delete: Optional[str] = None   # CASCADE | SET NULL | RESTRICT | ...
    on_update: Optional[str] = None
    name: Optional[str] = None        # nome da constraint, se nomeada
    relationship_field_name: str = "" # ex: "cliente"
    target_entity: str = ""           # ex: "Cliente"
    # FK composta (raro):
    columns: list[str] = field(default_factory=list)
    ref_columns: list[str] = field(default_factory=list)


@dataclass
class Column:
    name: str                          # nome original snake_case
    raw_sql_type: str                  # ex: "VARCHAR(255)"
    java_type: str                     # ex: "String"
    java_import: Optional[str] = None  # import necessário p/ o tipo (ou None)
    length: Optional[int] = None
    precision: Optional[int] = None
    scale: Optional[int] = None
    nullable: bool = True
    unique: bool = False
    default: Optional[str] = None
    is_pk: bool = False
    is_auto_increment: bool = False
    check: Optional[str] = None
    comment: Optional[str] = None
    is_foreign_key: bool = False
    fk: Optional[ForeignKey] = None
    enum_values: Optional[list[str]] = None  # de CHECK col IN (...)
    enum_type_name: Optional[str] = None      # nome do enum Java gerado, se houver
    type_unknown: bool = False

    @property
    def java_field(self) -> str:
        return snake_to_camel(self.name)


@dataclass
class OneToMany:
    child_table: str
    child_entity: str
    mapped_by: str
    collection_field_name: str


@dataclass
class ManyToMany:
    """Relacionamento N:N derivado de uma tabela de junção.

    Ex.: usuario_perfil(usuario_id, perfil_id) gera, em Usuario, a coleção
    `perfis` (dona, com @JoinTable) e, em Perfil, `usuarios` (inversa, mappedBy).
    """
    field_name: str                 # nome da coleção nesta entidade (ex.: "perfis")
    target_entity: str              # classe alvo (ex.: "Perfil")
    target_table: str               # tabela alvo (para resolver o repositório)
    owning: bool                    # True = lado dono (@JoinTable); False = inverso
    join_table: str = ""            # tabela de junção (lado dono)
    join_column: str = ""           # coluna FK desta entidade na junção
    inverse_join_column: str = ""   # coluna FK do alvo na junção
    mapped_by: str = ""             # campo dono no alvo (lado inverso)


@dataclass
class Table:
    name: str
    schema: Optional[str] = None
    columns: list[Column] = field(default_factory=list)
    primary_key: list[str] = field(default_factory=list)
    foreign_keys: list[ForeignKey] = field(default_factory=list)
    unique_constraints: list[list[str]] = field(default_factory=list)
    check_constraints: list[CheckConstraint] = field(default_factory=list)
    indexes: list[Index] = field(default_factory=list)
    comment: Optional[str] = None
    one_to_many: list[OneToMany] = field(default_factory=list)
    many_to_many: list[ManyToMany] = field(default_factory=list)
    is_join_table: bool = False   # tabela de junção pura N:N (não vira entidade)

    @property
    def class_name(self) -> str:
        return class_name_for_table(self.name)

    @property
    def has_composite_pk(self) -> bool:
        return len(self.primary_key) > 1

    @property
    def pk_column(self) -> Optional[Column]:
        for c in self.columns:
            if c.is_pk:
                return c
        return None

    @property
    def supports_base_entity(self) -> bool:
        """Toda tabela gerada estende BaseEntity (surrogate id Long). Apenas as
        tabelas de junção pura (N:N) não viram entidade."""
        return not self.is_join_table

    @property
    def has_surrogate_id(self) -> bool:
        """True quando a própria tabela já tem uma PK 'id' Long de incremento
        (então o id do BaseEntity substitui a coluna e ela não é emitida)."""
        pk = self.pk_column
        return (
            not self.has_composite_pk
            and pk is not None
            and pk.java_type == "Long"
            and pk.name.lower() == "id"
            and not pk.is_foreign_key
        )

    @property
    def pk_unique_columns(self) -> list[str]:
        """Colunas da PK original que viram UNIQUE quando usamos surrogate id
        (PK composta, ou PK simples que não é o 'id' Long)."""
        if self.is_join_table or self.has_surrogate_id or not self.primary_key:
            return []
        return list(self.primary_key)

    def column(self, name: str) -> Optional[Column]:
        for c in self.columns:
            if c.name.lower() == name.lower():
                return c
        return None


@dataclass
class Schema:
    tables: list[Table] = field(default_factory=list)
    # Comandos SQL ignorados (não-DDL de tabela), agrupados por tipo -> quantidade.
    # Ex.: {"INSERT": 3, "UPDATE": 1, "ALTER TABLE": 2}
    ignored: dict[str, int] = field(default_factory=dict)
    # Quantos ALTER TABLE foram consolidados dentro dos CREATE TABLE (quando a opção está ligada).
    consolidated_alters: int = 0

    def by_name(self) -> dict[str, Table]:
        return {t.name.lower(): t for t in self.tables}
