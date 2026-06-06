"""Infraestrutura comum dos geradores.

Define:
- `GenContext`: configuração vinda do formulário web (nome do sistema, pacote, flags).
- `GeneratedFile`: um arquivo Java em memória (pacote + nome + conteúdo).
- `BaseGenerator`: classe-base abstrata para os geradores por entidade.
- Conjuntos/utilitários compartilhados (colunas de auditoria, imports, formatação).

Os geradores produzem objetos `GeneratedFile` em memória — nunca escrevem em
disco — o que desacopla geração, preview e empacotamento em .zip.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from parser.model import Column, Table
from utils.naming import package_to_path

# Nomes de coluna herdados do BaseEntity. Só pulamos da entidade as colunas cujo
# nome bate EXATAMENTE com as do BaseEntity (criado_em, atualizado_em,
# criado_por, atualizado_por). Colunas de auditoria com outros nomes (ex.:
# created_at em inglês) são emitidas normalmente, para não quebrar o mapeamento.
AUDIT_COLUMNS = {
    "criado_em",
    "atualizado_em",
    "criado_por",
    "atualizado_por",
}


def is_audit_column(name: str) -> bool:
    """Indica se a coluna é de auditoria (provida pelo BaseEntity)."""
    return name.lower() in AUDIT_COLUMNS


@dataclass
class GenContext:
    """Parâmetros de geração preenchidos no formulário web."""
    system_name: str = "SISTEMA"
    base_package: str = "com.exemplo.app"
    dialect: str = "postgres"
    use_lombok: bool = True
    gen_inverse_rel: bool = True   # gerar @OneToMany no lado pai
    gen_enums: bool = True         # gerar enums de CHECK ... IN (...)
    gen_openapi: bool = True       # anotações springdoc (@Tag/@Operation/@Schema)
    audit_user: bool = True        # criadoPor/atualizadoPor + AuditorAware
    soft_delete: bool = False      # (reservado) soft delete no BaseEntity
    rest_base_path: str = "/api"

    def pkg(self, *segments: str) -> str:
        """Monta um subpacote: pkg('entity') -> 'com.exemplo.app.entity'."""
        return ".".join([self.base_package, *segments])


@dataclass
class GeneratedFile:
    """Arquivo Java gerado, ainda em memória."""
    package: str
    class_name: str
    content: str

    @property
    def rel_path(self) -> str:
        """Caminho relativo na estrutura Maven: src/main/java/<pacote>/<Classe>.java"""
        return f"src/main/java/{package_to_path(self.package)}/{self.class_name}.java"


class BaseGenerator(ABC):
    """Base dos geradores por entidade. `layer` é o subpacote alvo."""
    layer: str = ""

    def __init__(self, ctx: GenContext):
        self.ctx = ctx

    def package(self) -> str:
        return self.ctx.pkg(self.layer) if self.layer else self.ctx.base_package

    @abstractmethod
    def generate(self, table: Table) -> GeneratedFile:
        ...


# --------------------------------------------------------------------------- #
# Helpers de formatação de código Java
# --------------------------------------------------------------------------- #
def render_imports(imports: set[str]) -> str:
    """Ordena e formata uma lista de imports (java.* e jakarta.* agrupados)."""
    clean = sorted(i for i in imports if i)
    return "\n".join(f"import {i};" for i in clean)


def java_field_type(ctx: GenContext, col: Column) -> tuple[str, str | None]:
    """Resolve o tipo Java de uma coluna e o import necessário.

    Considera enums gerados (que vivem no pacote `enums`).
    """
    if ctx.gen_enums and col.enum_type_name and not col.is_foreign_key:
        return col.enum_type_name, ctx.pkg("enums") + "." + col.enum_type_name
    return col.java_type, col.java_import


def emit_columns(table: Table, ctx: GenContext, *, skip_audit: bool):
    """Itera as colunas relevantes para entidade/DTO.

    Pula a PK (provida pelo BaseEntity) e, opcionalmente, colunas de auditoria,
    quando a tabela estende BaseEntity.
    """
    uses_base = table.supports_base_entity
    for col in table.columns:
        # Só pulamos a coluna 'id' Long (substituída pelo id do BaseEntity).
        # PKs compostas/atípicas continuam sendo emitidas (e viram UNIQUE).
        if uses_base and table.has_surrogate_id and col.is_pk and col.name.lower() == "id":
            continue
        if uses_base and skip_audit and is_audit_column(col.name):
            continue
        yield col
