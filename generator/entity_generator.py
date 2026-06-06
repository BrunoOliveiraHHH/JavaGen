"""Gera a classe @Entity de cada tabela.

Destaques:
- FK vira RELACIONAMENTO objeto (@ManyToOne @JoinColumn), não um Long.
- Lê length/nullable/unique/precision/scale para o @Column.
- Detecta enums (CHECK ... IN) e usa @Enumerated(STRING).
- Index -> @Table(indexes=@Index). CHECK -> @Check (Hibernate 6).
- Entidades estendem BaseEntity (id + auditoria herdados).
"""
from __future__ import annotations

from generator.base import BaseGenerator, GeneratedFile, emit_columns, java_field_type
from parser.model import Column, Schema, Table


class EntityGenerator(BaseGenerator):
    layer = "entity"

    def __init__(self, ctx, schema: Schema):
        super().__init__(ctx)
        self.schema = schema
        self._by_name = schema.by_name()

    def generate(self, table: Table) -> GeneratedFile:
        ctx = self.ctx
        uses_base = table.supports_base_entity
        imports: set[str] = {"jakarta.persistence.*", "lombok.Getter", "lombok.Setter",
                             "lombok.NoArgsConstructor", "lombok.AllArgsConstructor"}
        body: list[str] = []

        if uses_base:
            imports.add(ctx.pkg("common") + ".BaseEntity")
            imports.add("lombok.EqualsAndHashCode")

        # Quando não há BaseEntity (PK composta etc.), emitimos a PK manualmente.
        if not uses_base:
            body.extend(self._render_standalone_id(table, imports))

        for col in emit_columns(table, ctx, skip_audit=True):
            if uses_base and col.is_pk:
                continue
            if col.is_foreign_key and col.fk and self._by_name.get(col.fk.ref_table.lower()):
                body.extend(self._render_relationship(col))
            else:
                body.extend(self._render_column(col, imports))

        # Lado inverso @OneToMany (opcional).
        if ctx.gen_inverse_rel and table.one_to_many:
            imports.add("java.util.List")
            for otm in table.one_to_many:
                body.append("")
                body.append(f'    @OneToMany(mappedBy = "{otm.mapped_by}")')
                body.append(f"    private List<{otm.child_entity}> {otm.collection_field_name};")

        # Relacionamentos N:N (coleções de entidades, ex.: perfis em usuário).
        if table.many_to_many:
            imports.add("java.util.List")
            for m in table.many_to_many:
                body.append("")
                if m.owning:
                    # Lado dono: carrega a lista EAGER (sem lazy) e define a @JoinTable.
                    body.append("    @ManyToMany(fetch = FetchType.EAGER)")
                    body.append(f'    @JoinTable(name = "{m.join_table}",')
                    body.append(f'            joinColumns = @JoinColumn(name = "{m.join_column}"),')
                    body.append(f'            inverseJoinColumns = @JoinColumn(name = "{m.inverse_join_column}"))')
                    body.append(f"    private List<{m.target_entity}> {m.field_name};")
                else:
                    body.append(f'    @ManyToMany(mappedBy = "{m.mapped_by}")')
                    body.append(f"    private List<{m.target_entity}> {m.field_name};")

        # Coleta imports de tipos (BigDecimal, LocalDate, enums...).
        for col in emit_columns(table, ctx, skip_audit=True):
            if not (col.is_foreign_key and col.fk and self._by_name.get(col.fk.ref_table.lower())):
                _, imp = java_field_type(ctx, col)
                if imp:
                    imports.add(imp)

        class_anns = self._class_annotations(table, imports, uses_base)
        content = self._assemble(table, imports, class_anns, body, uses_base)
        return GeneratedFile(self.package(), table.class_name, content)

    # ------------------------------------------------------------------ #
    def _render_standalone_id(self, table: Table, imports: set[str]) -> list[str]:
        """Para tabelas sem BaseEntity: emite a(s) coluna(s) de PK com @Id."""
        lines: list[str] = []
        if table.has_composite_pk:
            lines.append("    // TODO: PK composta — considere @EmbeddedId/@IdClass.")
        return lines

    def _render_relationship(self, col: Column) -> list[str]:
        fk = col.fk
        optional = "true" if col.nullable else "false"
        join_args = [f'name = "{col.name}"']
        if not col.nullable:
            join_args.append("nullable = false")
        # Carregamento EAGER por decisão de projeto (evita LazyInitializationException).
        return [
            "",
            f"    @ManyToOne(fetch = FetchType.EAGER, optional = {optional})",
            f'    @JoinColumn({", ".join(join_args)})',
            f"    private {fk.target_entity} {fk.relationship_field_name};",
        ]

    def _render_column(self, col: Column, imports: set[str]) -> list[str]:
        ctx = self.ctx
        java_type, _ = java_field_type(ctx, col)
        lines: list[str] = [""]

        if col.is_pk:  # só ocorre em tabelas sem BaseEntity
            lines.append("    @Id")
            if col.is_auto_increment:
                lines.append("    @GeneratedValue(strategy = GenerationType.IDENTITY)")

        col_args = [f'name = "{col.name}"']
        if col.java_type == "String" and col.length:
            col_args.append(f"length = {col.length}")
        if not col.nullable and not col.is_pk:
            col_args.append("nullable = false")
        if col.unique:
            col_args.append("unique = true")
        if col.java_type == "BigDecimal" and col.precision:
            col_args.append(f"precision = {col.precision}")
            if col.scale is not None:
                col_args.append(f"scale = {col.scale}")
        lines.append(f'    @Column({", ".join(col_args)})')

        if ctx.gen_enums and col.enum_type_name:
            lines.append("    @Enumerated(EnumType.STRING)")
        if col.type_unknown:
            lines.append(f"    // TODO: tipo SQL '{col.raw_sql_type}' não mapeado — revisar.")

        lines.append(f"    private {java_type} {col.java_field};")
        return lines

    def _class_annotations(self, table: Table, imports: set[str], uses_base: bool) -> list[str]:
        anns = ["@Entity"]

        table_args = [f'name = "{table.name}"']
        if table.indexes:
            idx_parts = []
            for idx in table.indexes:
                cols = ", ".join(idx.columns)
                extra = ", unique = true" if idx.unique else ""
                idx_parts.append(f'        @Index(name = "{idx.name}", columnList = "{cols}"{extra})')
            joined = ",\n".join(idx_parts)
            table_args.append("indexes = {\n" + joined + "\n    }")
        anns.append(f'@Table({", ".join(table_args)})')

        checks = [c.expression for c in table.check_constraints]
        checks += [col.check for col in table.columns if col.check]
        if checks:
            imports.add("org.hibernate.annotations.Check")
            combined = " AND ".join(f"({c})" for c in checks if c)
            combined = combined.replace('"', '\\"')
            anns.append(f'@Check(constraints = "{combined}")')

        # Soft delete: DELETE vira UPDATE e as consultas escondem os removidos.
        if self.ctx.soft_delete and uses_base:
            imports.add("org.hibernate.annotations.SQLDelete")
            imports.add("org.hibernate.annotations.SQLRestriction")
            anns.append(f'@SQLDelete(sql = "UPDATE {table.name} SET deleted = true WHERE id = ?")')
            anns.append('@SQLRestriction("deleted = false")')

        anns += ["@Getter", "@Setter", "@NoArgsConstructor", "@AllArgsConstructor"]
        if uses_base:
            anns.append("@EqualsAndHashCode(callSuper = true)")
        return anns

    def _assemble(self, table, imports, class_anns, body, uses_base) -> str:
        imports_block = "\n".join(f"import {i};" for i in sorted(imports))
        extends = " extends BaseEntity" if uses_base else ""
        anns_block = "\n".join(class_anns)
        body_block = "\n".join(body)
        return (
            f"package {self.package()};\n\n"
            f"{imports_block}\n\n"
            f"/**\n * Entidade JPA mapeada para a tabela {table.name}.\n */\n"
            f"{anns_block}\n"
            f"public class {table.class_name}{extends} {{\n"
            f"{body_block}\n"
            f"}}\n"
        )
