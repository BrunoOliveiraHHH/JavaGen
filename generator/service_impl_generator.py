"""Gera a implementação do Service (XServiceImpl).

- Injeta repositório e mapper como `private final` (Lombok @RequiredArgsConstructor).
- Fornece os acessores genéricos (getRepository/getMapper/getEntityClass/toSpecification).
- Gera `validate(entity)` a partir das constraints do SQL (NOT NULL, length, CHECK >= 0),
  com mensagens padronizadas ("Campo {x} é obrigatório").
"""
from __future__ import annotations

import re

from generator.base import BaseGenerator, GeneratedFile, emit_columns
from parser.model import Column, Schema, Table

_NUMERIC = {"Integer", "Long", "Short", "Double", "Float", "BigDecimal"}
_POSITIVE_RE = re.compile(r">=?\s*0\b")


def _pascal(name: str) -> str:
    return name[:1].upper() + name[1:] if name else name


class ServiceImplGenerator(BaseGenerator):
    layer = "service.impl"

    def __init__(self, ctx, schema: Schema):
        super().__init__(ctx)
        self.schema = schema
        self._by_name = schema.by_name()

    def generate(self, table: Table) -> GeneratedFile:
        ctx = self.ctx
        entity = table.class_name
        val_lines, needs_bigdecimal = self._build_validation(table)

        imports = {
            ctx.pkg("common") + ".GenericMapper",
            ctx.pkg("common") + ".GenericRepository",
            ctx.pkg("common") + ".GenericServiceImpl",
            ctx.pkg("dto") + "." + entity + "Dto",
            ctx.pkg("entity") + "." + entity,
            ctx.pkg("filter") + "." + entity + "Filter",
            ctx.pkg("mapper") + "." + entity + "Mapper",
            ctx.pkg("repository") + "." + entity + "Repository",
            ctx.pkg("service") + "." + entity + "Service",
            ctx.pkg("specification") + "." + entity + "Specification",
            "lombok.RequiredArgsConstructor",
            "org.springframework.data.jpa.domain.Specification",
            "org.springframework.stereotype.Service",
        }
        if val_lines:
            imports.add(ctx.pkg("common.validation") + ".ValidationError")
            imports.add(ctx.pkg("common.validation") + ".ValidationException")
            imports.add("java.util.ArrayList")
            imports.add("java.util.List")
        if needs_bigdecimal:
            imports.add("java.math.BigDecimal")

        # FKs e N:N cujo alvo é uma entidade conhecida (gera repo + getX + resolveRelationships).
        fk_rels: list[tuple[str, str]] = []    # (classe alvo, campo do relacionamento @ManyToOne)
        m2m_rels: list[tuple[str, str]] = []   # (classe alvo, coleção N:N do lado dono)
        targets: list[str] = []                # alvos distintos, na ordem de uso
        for fk in table.foreign_keys:
            target_tbl = self._by_name.get(fk.ref_table.lower())
            if target_tbl is None:
                continue
            tgt = target_tbl.class_name
            fk_rels.append((tgt, fk.relationship_field_name))
            if tgt not in targets:
                targets.append(tgt)
        for m in table.many_to_many:
            if not m.owning:
                continue
            m2m_rels.append((m.target_entity, m.field_name))
            if m.target_entity not in targets:
                targets.append(m.target_entity)

        for tgt in targets:
            imports.add(ctx.pkg("repository") + "." + tgt + "Repository")
            imports.add(ctx.pkg("entity") + "." + tgt)
        if fk_rels or m2m_rels:
            imports.add(ctx.pkg("common.validation") + ".ResourceNotFoundException")

        imports_block = "\n".join(f"import {i};" for i in sorted(imports))
        validate_method = self._render_validate(entity, val_lines)
        secondary_fields = "".join(
            f"    private final {tgt}Repository {tgt[:1].lower() + tgt[1:]}Repository;\n"
            for tgt in targets
        )
        resolve_block = self._render_resolve(entity, fk_rels, m2m_rels, targets)

        content = (
            f"package {self.package()};\n\n"
            f"{imports_block}\n\n"
            f"/**\n * Implementação do serviço de {entity}.\n */\n"
            f"@Service\n"
            f"@RequiredArgsConstructor\n"
            f"public class {entity}ServiceImpl\n"
            f"        extends GenericServiceImpl<{entity}, {entity}Dto, {entity}Filter>\n"
            f"        implements {entity}Service {{\n\n"
            f"    private final {entity}Repository repository;\n"
            f"    private final {entity}Mapper mapper;\n"
            f"{secondary_fields}\n"
            f"    @Override\n"
            f"    protected GenericRepository<{entity}> getRepository() {{\n"
            f"        return repository;\n"
            f"    }}\n\n"
            f"    @Override\n"
            f"    protected GenericMapper<{entity}, {entity}Dto> getMapper() {{\n"
            f"        return mapper;\n"
            f"    }}\n\n"
            f"    @Override\n"
            f"    protected Class<{entity}> getEntityClass() {{\n"
            f"        return {entity}.class;\n"
            f"    }}\n\n"
            f"    @Override\n"
            f"    protected Specification<{entity}> toSpecification({entity}Filter f) {{\n"
            f"        return {entity}Specification.build(f);\n"
            f"    }}\n\n"
            f"{resolve_block}"
            f"{validate_method}"
            f"}}\n"
        )
        return GeneratedFile(self.package(), f"{entity}ServiceImpl", content)

    def _render_resolve(self, entity: str, fk_rels: list[tuple[str, str]],
                        m2m_rels: list[tuple[str, str]], targets: list[str]) -> str:
        """Gera resolveRelationships(entity) + os métodos getX (findById no repo do alvo)."""
        if not fk_rels and not m2m_rels:
            return ""
        # resolveRelationships: troca referências rasas (FK e itens da lista N:N) pelas gerenciadas.
        body = []
        for tgt, rel in fk_rels:
            rel_p = rel[:1].upper() + rel[1:]
            body.append(f"        if (entity.get{rel_p}() != null) {{")
            body.append(f"            entity.set{rel_p}(get{tgt}(entity.get{rel_p}().getId()));")
            body.append("        }")
        for tgt, coll in m2m_rels:
            coll_p = coll[:1].upper() + coll[1:]
            body.append(f"        if (entity.get{coll_p}() != null) {{")
            body.append(f"            entity.set{coll_p}(entity.get{coll_p}().stream()")
            body.append(f"                    .map(x -> get{tgt}(x.getId())).toList());")
            body.append("        }")
        resolve = (
            f"    /**\n"
            f"     * Substitui as referências rasas de FK (só id) pelas entidades gerenciadas,\n"
            f"     * carregadas dos respectivos repositórios.\n"
            f"     */\n"
            f"    @Override\n"
            f"    protected void resolveRelationships({entity} entity) {{\n"
            + "\n".join(body) + "\n"
            f"    }}\n\n"
        )
        # Métodos getX, um por alvo distinto.
        getters = []
        for tgt in targets:
            repo_field = tgt[:1].lower() + tgt[1:] + "Repository"
            getters.append(
                f"    /** Carrega {tgt} pelo id (referência gerenciada; use getReferenceById p/ lazy). */\n"
                f"    private {tgt} get{tgt}(Long id) {{\n"
                f"        if (id == null) {{\n"
                f"            return null;\n"
                f"        }}\n"
                f"        return {repo_field}.findById(id)\n"
                f'                .orElseThrow(() -> new ResourceNotFoundException("{tgt}", id));\n'
                f"    }}\n\n"
            )
        return resolve + "".join(getters)

    # ------------------------------------------------------------------ #
    def _has_positive_check(self, table: Table, col: Column) -> bool:
        if col.check and _POSITIVE_RE.search(col.check) and col.name.lower() in col.check.lower():
            return True
        for chk in table.check_constraints:
            if col.name.lower() in chk.expression.lower() and _POSITIVE_RE.search(chk.expression):
                return True
        return False

    def _build_validation(self, table: Table) -> tuple[list[str], bool]:
        """Devolve (linhas de validação, precisa importar BigDecimal)."""
        lines: list[str] = []
        needs_bigdecimal = False

        for col in emit_columns(table, self.ctx, skip_audit=True):
            if col.is_pk or col.is_auto_increment:
                continue

            # Foreign key conhecida -> validar relacionamento
            if col.is_foreign_key and col.fk and self._by_name.get(col.fk.ref_table.lower()):
                rel = col.fk.relationship_field_name
                getter = f"get{_pascal(rel)}"
                if not col.nullable:
                    lines += [
                        f"        if (entity.{getter}() == null) {{",
                        f'            errors.add(ValidationError.required("{rel}"));',
                        "        }",
                    ]
                continue

            field = col.java_field
            getter = f"get{_pascal(field)}"

            # Coluna enum: tipo é o enum (não String) -> só checagem de obrigatório.
            if self.ctx.gen_enums and col.enum_type_name:
                if not col.nullable:
                    lines += [
                        f"        if (entity.{getter}() == null) {{",
                        f'            errors.add(ValidationError.required("{field}"));',
                        "        }",
                    ]
                continue

            if col.java_type == "String":
                if not col.nullable:
                    block = [
                        f"        if (entity.{getter}() == null || entity.{getter}().isBlank()) {{",
                        f'            errors.add(ValidationError.required("{field}"));',
                        "        }",
                    ]
                    if col.length:
                        block[-1] = "        } else if (entity.%s().length() > %d) {" % (getter, col.length)
                        block += [
                            f'            errors.add(ValidationError.maxLength("{field}", {col.length}));',
                            "        }",
                        ]
                    lines += block
                elif col.length:
                    lines += [
                        f"        if (entity.{getter}() != null && entity.{getter}().length() > {col.length}) {{",
                        f'            errors.add(ValidationError.maxLength("{field}", {col.length}));',
                        "        }",
                    ]
            else:
                if not col.nullable:
                    lines += [
                        f"        if (entity.{getter}() == null) {{",
                        f'            errors.add(ValidationError.required("{field}"));',
                        "        }",
                    ]
                if col.java_type in _NUMERIC and self._has_positive_check(table, col):
                    if col.java_type == "BigDecimal":
                        needs_bigdecimal = True
                        cond = f"entity.{getter}() != null && entity.{getter}().compareTo(BigDecimal.ZERO) < 0"
                    else:
                        cond = f"entity.{getter}() != null && entity.{getter}() < 0"
                    lines += [
                        f"        if ({cond}) {{",
                        f'            errors.add(ValidationError.positive("{field}"));',
                        "        }",
                    ]

        return lines, needs_bigdecimal

    def _render_validate(self, entity: str, val_lines: list[str]) -> str:
        if not val_lines:
            # Nada a validar: sobrescreve com corpo vazio explícito (documentado).
            return (
                f"    @Override\n"
                f"    public void validate({entity} entity) {{\n"
                f"        // Nenhuma constraint NOT NULL/length/CHECK detectada para validar.\n"
                f"    }}\n"
            )
        body = "\n".join(val_lines)
        return (
            f"    /**\n"
            f"     * Valida os campos de {entity} conforme as constraints do SQL.\n"
            f"     */\n"
            f"    @Override\n"
            f"    public void validate({entity} entity) {{\n"
            f"        List<ValidationError> errors = new ArrayList<>();\n"
            f"{body}\n"
            f"        if (!errors.isEmpty()) {{\n"
            f"            throw new ValidationException(errors);\n"
            f"        }}\n"
            f"    }}\n"
        )
