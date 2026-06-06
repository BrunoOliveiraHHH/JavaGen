"""Gera as classes do pacote `common` (e `common.validation`).

São emitidas UMA vez por projeto (independem das tabelas), apenas substituindo
o pacote base e o nome do sistema. Aqui ficam as peças genéricas reutilizáveis:
BaseEntity, ApiResponse, PageResponse, GenericRepository/Mapper/Service/ServiceImpl,
GenericSpecification, auditoria e o tratamento de exceções.
"""
from __future__ import annotations

from generator.base import GenContext, GeneratedFile

# Placeholders substituídos em cada template:
#   __PKG__ -> pacote base (ex.: com.sinapsis.sisgel)
#   __SYS__ -> nome do sistema (ex.: SISGEL)


def _file(ctx: GenContext, subpackage: str, class_name: str, template: str) -> GeneratedFile:
    """Aplica as substituições e devolve um GeneratedFile já pronto."""
    content = template.replace("__PKG__", ctx.base_package).replace("__SYS__", ctx.system_name)
    return GeneratedFile(package=ctx.pkg(subpackage) if subpackage else ctx.base_package,
                         class_name=class_name, content=content.lstrip("\n"))


_SYSTEM_INFO = """
package __PKG__.common;

/**
 * Informações do sistema, preenchidas pelo gerador a partir do formulário.
 */
public final class SystemInfo {

    /** Nome do sistema, usado para carimbar todas as respostas da API. */
    public static final String SYSTEM_NAME = "__SYS__";

    private SystemInfo() {
        // Classe utilitária: não deve ser instanciada.
    }
}
"""

_GENERIC_REPOSITORY = """
package __PKG__.common;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.repository.NoRepositoryBean;

/**
 * Repositório base de todas as entidades.
 *
 * <p>Reúne CRUD ({@link JpaRepository}) e consultas dinâmicas
 * ({@link JpaSpecificationExecutor}). O tipo do id é fixado em {@code Long},
 * consistente com {@link BaseEntity}.</p>
 *
 * @param <E> tipo da entidade
 */
@NoRepositoryBean
public interface GenericRepository<E> extends JpaRepository<E, Long>, JpaSpecificationExecutor<E> {
}
"""

_GENERIC_MAPPER = """
package __PKG__.common;

/**
 * Contrato de mapeamento entre Entidade e DTO.
 *
 * @param <E> entidade
 * @param <D> DTO
 */
public interface GenericMapper<E, D> {

    /** Converte a entidade em DTO (leitura). */
    D toDto(E entity);

    /** Converte o DTO em entidade (escrita), resolvendo relacionamentos. */
    E toEntity(D dto);
}
"""

_API_RESPONSE = """
package __PKG__.common;

import com.fasterxml.jackson.annotation.JsonInclude;

import java.time.LocalDateTime;
import java.util.List;

/**
 * Envelope padrão de resposta da API, carimbado com o nome do sistema.
 *
 * @param <T> tipo do dado retornado
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record ApiResponse<T>(
        String system,
        boolean success,
        String message,
        T data,
        List<String> errors,
        LocalDateTime timestamp
) {

    /** Resposta de sucesso com mensagem padrão. */
    public static <T> ApiResponse<T> ok(T data) {
        return new ApiResponse<>(SystemInfo.SYSTEM_NAME, true,
                "Operação realizada com sucesso.", data, null, LocalDateTime.now());
    }

    /** Resposta de sucesso com mensagem customizada. */
    public static <T> ApiResponse<T> ok(T data, String message) {
        return new ApiResponse<>(SystemInfo.SYSTEM_NAME, true, message, data, null, LocalDateTime.now());
    }

    /** Resposta de erro simples. */
    public static <T> ApiResponse<T> error(String message) {
        return new ApiResponse<>(SystemInfo.SYSTEM_NAME, false, message, null, null, LocalDateTime.now());
    }

    /** Resposta de erro com lista de mensagens (ex.: validação). */
    public static <T> ApiResponse<T> error(String message, List<String> errors) {
        return new ApiResponse<>(SystemInfo.SYSTEM_NAME, false, message, null, errors, LocalDateTime.now());
    }
}
"""

_PAGE_RESPONSE = """
package __PKG__.common;

import org.springframework.data.domain.Page;

import java.util.List;

/**
 * Representação de página própria do sistema, para não expor o tipo {@code Page}
 * do Spring diretamente na API.
 *
 * @param <T> tipo do conteúdo
 */
public record PageResponse<T>(
        List<T> content,
        int page,
        int size,
        long totalElements,
        int totalPages,
        boolean last
) {

    /** Converte um {@link Page} do Spring Data nesta representação. */
    public static <T> PageResponse<T> from(Page<T> p) {
        return new PageResponse<>(p.getContent(), p.getNumber(), p.getSize(),
                p.getTotalElements(), p.getTotalPages(), p.isLast());
    }
}
"""

_GENERIC_SERVICE = """
package __PKG__.common;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

import java.util.List;

/**
 * Contrato genérico de serviço: CRUD + filtro paginado.
 *
 * <p>{@code create} e {@code update} são expostos ao controller (recebem/retornam
 * DTO e validam). {@code save} é interno: faz INSERT/UPDATE + flush no Hibernate.</p>
 *
 * @param <E> entidade
 * @param <D> DTO (record unificado)
 * @param <F> filtro
 */
public interface GenericService<E, D, F> {

    /** Lista paginada aplicando o filtro; retorna DTOs. */
    Page<D> filter(F filtro, Pageable pageable);

    /** Lista completa (uso administrativo / combos); retorna DTOs. */
    List<D> findAll();

    /** Busca por id; lança ResourceNotFoundException se ausente. */
    D findById(Long id);

    /** Exposto ao controller: valida, mapeia e persiste um novo registro. */
    D create(D dto);

    /** Exposto ao controller: valida e persiste um registro existente. */
    D update(Long id, D dto);

    /** Remove por id (verifica existência). */
    void delete(Long id);

    /** Interno: INSERT/UPDATE + FLUSH imediato no Hibernate (saveAndFlush). */
    E save(E entity);

    /** Valida os campos da entidade; lança ValidationException se houver erros. */
    void validate(E entity);
}
"""

_GENERIC_SERVICE_IMPL = """
package __PKG__.common;

import __PKG__.common.validation.ResourceNotFoundException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * Implementação genérica de CRUD + filtro paginado.
 *
 * <p>O fluxo (filter/create/update/save/delete) é 100% genérico aqui; as subclasses
 * geradas (XServiceImpl) só fornecem o repositório, o mapper, a classe da entidade,
 * a Specification do filtro e (opcionalmente) a validação.</p>
 *
 * @param <E> entidade (estende BaseEntity, garantindo acesso a setId)
 * @param <D> DTO
 * @param <F> filtro
 */
public abstract class GenericServiceImpl<E extends BaseEntity, D, F> implements GenericService<E, D, F> {

    /** Repositório da entidade (fornecido pela subclasse, injetado via Lombok). */
    protected abstract GenericRepository<E> getRepository();

    /** Mapper Entidade<->DTO (fornecido pela subclasse). */
    protected abstract GenericMapper<E, D> getMapper();

    /** Classe da entidade, usada para mensagens de "não encontrado". */
    protected abstract Class<E> getEntityClass();

    /** Constrói a Specification a partir do filtro (delega à XSpecification). */
    protected abstract Specification<E> toSpecification(F filtro);

    /**
     * Resolve os relacionamentos (FKs) da entidade antes de persistir.
     *
     * <p>O Mapper preenche as FKs apenas como referência rasa (id). Aqui o Service
     * substitui cada referência pela entidade carregada do repositório correspondente
     * (findById/getReference). Padrão: não faz nada; é sobrescrito por entidade.</p>
     */
    protected void resolveRelationships(E entity) {
        // Sobrescrito pela subclasse gerada quando há FKs.
    }

    @Override
    @Transactional(readOnly = true)
    public Page<D> filter(F filtro, Pageable pageable) {
        return getRepository().findAll(toSpecification(filtro), pageable).map(getMapper()::toDto);
    }

    @Override
    @Transactional(readOnly = true)
    public List<D> findAll() {
        return getRepository().findAll().stream().map(getMapper()::toDto).toList();
    }

    @Override
    @Transactional(readOnly = true)
    public D findById(Long id) {
        E entity = getRepository().findById(id)
                .orElseThrow(() -> new ResourceNotFoundException(getEntityClass().getSimpleName(), id));
        return getMapper().toDto(entity);
    }

    @Override
    @Transactional
    public D create(D dto) {
        E entity = getMapper().toEntity(dto);
        entity.setId(null); // garante INSERT
        resolveRelationships(entity); // troca refs rasas por entidades gerenciadas
        validate(entity);
        return getMapper().toDto(save(entity));
    }

    @Override
    @Transactional
    public D update(Long id, D dto) {
        if (!getRepository().existsById(id)) {
            throw new ResourceNotFoundException(getEntityClass().getSimpleName(), id);
        }
        E entity = getMapper().toEntity(dto);
        entity.setId(id); // o id do path prevalece sobre o do corpo
        resolveRelationships(entity); // troca refs rasas por entidades gerenciadas
        validate(entity);
        return getMapper().toDto(save(entity));
    }

    @Override
    @Transactional
    public void delete(Long id) {
        if (!getRepository().existsById(id)) {
            throw new ResourceNotFoundException(getEntityClass().getSimpleName(), id);
        }
        getRepository().deleteById(id);
    }

    @Override
    @Transactional
    public E save(E entity) {
        return getRepository().saveAndFlush(entity);
    }

    @Override
    public void validate(E entity) {
        // Validação padrão vazia; as subclasses geradas sobrescrevem com regras por campo.
    }
}
"""

_GENERIC_SPECIFICATION = """
package __PKG__.common;

import jakarta.persistence.criteria.JoinType;
import jakarta.persistence.criteria.Path;
import org.springframework.data.jpa.domain.Specification;

/**
 * Fábrica de Specifications reutilizáveis.
 *
 * <p>Cada helper devolve uma condição "neutra" ({@code cb.conjunction()}) quando o
 * valor do filtro é nulo, permitindo encadear com {@code .and(...)} sem ifs e sem
 * usar {@code Specification.where(null)} (depreciado no Spring Boot 3.4+).</p>
 */
public final class GenericSpecification {

    private GenericSpecification() {
        // Classe utilitária: não deve ser instanciada.
    }

    /** LIKE case-insensitive (contains) em coluna String. */
    public static <E> Specification<E> like(String attribute, String value) {
        return (root, query, cb) -> (value == null || value.isBlank())
                ? cb.conjunction()
                : cb.like(cb.lower(root.get(attribute)), "%" + value.toLowerCase() + "%");
    }

    /** Igualdade exata. */
    public static <E, V> Specification<E> equal(String attribute, V value) {
        return (root, query, cb) -> value == null ? cb.conjunction() : cb.equal(root.get(attribute), value);
    }

    /** Igualdade através de um relacionamento (ex.: cliente.id). */
    public static <E, V> Specification<E> equalJoin(String association, String attribute, V value) {
        return (root, query, cb) -> {
            if (value == null) {
                return cb.conjunction();
            }
            Path<V> path = root.join(association, JoinType.LEFT).get(attribute);
            return cb.equal(path, value);
        };
    }

    /** Maior ou igual. */
    public static <E, V extends Comparable<? super V>> Specification<E> gte(String attribute, V value) {
        return (root, query, cb) -> value == null
                ? cb.conjunction() : cb.greaterThanOrEqualTo(root.get(attribute), value);
    }

    /** Menor ou igual. */
    public static <E, V extends Comparable<? super V>> Specification<E> lte(String attribute, V value) {
        return (root, query, cb) -> value == null
                ? cb.conjunction() : cb.lessThanOrEqualTo(root.get(attribute), value);
    }

    /** Intervalo inclusivo [from, to]; limites nulos são ignorados. */
    public static <E, V extends Comparable<? super V>> Specification<E> between(String attribute, V from, V to) {
        return (root, query, cb) -> {
            if (from != null && to != null) {
                return cb.between(root.get(attribute), from, to);
            }
            if (from != null) {
                return cb.greaterThanOrEqualTo(root.get(attribute), from);
            }
            if (to != null) {
                return cb.lessThanOrEqualTo(root.get(attribute), to);
            }
            return cb.conjunction();
        };
    }
}
"""

_VALIDATION_ERROR = """
package __PKG__.common.validation;

/**
 * Erro de validação de um campo, com mensagens padronizadas.
 *
 * @param field   nome do campo
 * @param message mensagem amigável
 */
public record ValidationError(String field, String message) {

    /** "Campo {field} é obrigatório". */
    public static ValidationError required(String field) {
        return new ValidationError(field, "Campo " + field + " é obrigatório");
    }

    /** "Campo {field} deve ter no máximo {max} caracteres". */
    public static ValidationError maxLength(String field, int max) {
        return new ValidationError(field, "Campo " + field + " deve ter no máximo " + max + " caracteres");
    }

    /** "Campo {field} deve ser maior ou igual a zero". */
    public static ValidationError positive(String field) {
        return new ValidationError(field, "Campo " + field + " deve ser maior ou igual a zero");
    }

    /** "Campo {field} é inválido". */
    public static ValidationError invalid(String field) {
        return new ValidationError(field, "Campo " + field + " é inválido");
    }
}
"""

_VALIDATION_EXCEPTION = """
package __PKG__.common.validation;

import java.util.List;

/**
 * Lançada quando a validação de campos falha. É tratada pelo
 * {@link GlobalExceptionHandler}, virando uma resposta HTTP 400 padronizada.
 */
public class ValidationException extends RuntimeException {

    private final transient List<ValidationError> errors;

    public ValidationException(List<ValidationError> errors) {
        super("Falha de validação: " + errors.size() + " erro(s).");
        this.errors = errors;
    }

    public ValidationException(ValidationError error) {
        this(List.of(error));
    }

    public List<ValidationError> getErrors() {
        return errors;
    }

    /** Apenas as mensagens, para devolver na resposta de erro. */
    public List<String> getMessages() {
        return errors.stream().map(ValidationError::message).toList();
    }
}
"""

_RESOURCE_NOT_FOUND = """
package __PKG__.common.validation;

/**
 * Recurso não encontrado. É tratada pelo {@link GlobalExceptionHandler},
 * virando uma resposta HTTP 404.
 */
public class ResourceNotFoundException extends RuntimeException {

    public ResourceNotFoundException(String resource, Object id) {
        super(resource + " não encontrado(a) para o id " + id);
    }
}
"""

_GLOBAL_HANDLER = """
package __PKG__.common.validation;

import __PKG__.common.ApiResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * Converte exceções da aplicação em respostas {@link ApiResponse} padronizadas.
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    /** Erros de validação -> HTTP 400 com a lista de mensagens. */
    @ExceptionHandler(ValidationException.class)
    public ResponseEntity<ApiResponse<Void>> handleValidation(ValidationException ex) {
        return ResponseEntity.badRequest().body(ApiResponse.error("Erro de validação", ex.getMessages()));
    }

    /** Recurso inexistente -> HTTP 404. */
    @ExceptionHandler(ResourceNotFoundException.class)
    public ResponseEntity<ApiResponse<Void>> handleNotFound(ResourceNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(ApiResponse.error(ex.getMessage()));
    }

    /** Qualquer outra exceção -> HTTP 500. */
    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiResponse<Void>> handleGeneric(Exception ex) {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ApiResponse.error("Erro interno: " + ex.getMessage()));
    }
}
"""


def _base_entity(ctx: GenContext) -> str:
    """BaseEntity com auditoria; campos de usuário só quando audit_user=True."""
    imports = [
        "jakarta.persistence.Column",
        "jakarta.persistence.EntityListeners",
        "jakarta.persistence.GeneratedValue",
        "jakarta.persistence.GenerationType",
        "jakarta.persistence.Id",
        "jakarta.persistence.MappedSuperclass",
        "lombok.Getter",
        "lombok.Setter",
        "org.springframework.data.annotation.CreatedDate",
        "org.springframework.data.annotation.LastModifiedDate",
        "org.springframework.data.jpa.domain.support.AuditingEntityListener",
        "java.time.LocalDateTime",
    ]
    if ctx.audit_user:
        imports += [
            "org.springframework.data.annotation.CreatedBy",
            "org.springframework.data.annotation.LastModifiedBy",
        ]
    imports_block = "\n".join(f"import {i};" for i in sorted(imports))
    audit_ref = " e {@link AuditorAwareImpl}" if ctx.audit_user else ""

    soft_field = ""
    if ctx.soft_delete:
        soft_field = """
    /** Marca de exclusão lógica (soft delete). false = ativo. */
    @Column(name = "deleted", nullable = false)
    private Boolean deleted = false;
"""

    user_fields = ""
    if ctx.audit_user:
        user_fields = """
    /** Usuário que criou o registro (preenchido via AuditorAware). */
    @CreatedBy
    @Column(name = "criado_por", updatable = false)
    private String criadoPor;

    /** Usuário da última alteração (preenchido via AuditorAware). */
    @LastModifiedBy
    @Column(name = "atualizado_por")
    private String atualizadoPor;
"""

    return f"""package {ctx.base_package}.common;

{imports_block}

/**
 * Superclasse de todas as entidades: id auto-gerado + campos de auditoria.
 *
 * <p>A auditoria é preenchida automaticamente pelo Spring Data JPA Auditing
 * (ver {{@link JpaAuditingConfig}}{audit_ref}).</p>
 */
@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
@Getter
@Setter
public abstract class BaseEntity {{

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** Data/hora de criação do registro. */
    @CreatedDate
    @Column(name = "criado_em", updatable = false)
    private LocalDateTime criadoEm;

    /** Data/hora da última atualização. */
    @LastModifiedDate
    @Column(name = "atualizado_em")
    private LocalDateTime atualizadoEm;
{soft_field}{user_fields}}}
"""


def _jpa_auditing_config(ctx: GenContext) -> str:
    ref = '(auditorAwareRef = "auditorAware")' if ctx.audit_user else ""
    user_doc = "/criadoPor/atualizadoPor" if ctx.audit_user else ""
    return f"""package {ctx.base_package}.common;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

/**
 * Ativa o Spring Data JPA Auditing, responsável por preencher os campos de
 * auditoria do {{@link BaseEntity}} (criadoEm/atualizadoEm{user_doc}).
 */
@Configuration
@EnableJpaAuditing{ref}
public class JpaAuditingConfig {{
}}
"""


_AUDITOR_AWARE = """
package __PKG__.common;

import org.springframework.data.domain.AuditorAware;
import org.springframework.stereotype.Component;

import java.util.Optional;

/**
 * Fornece o usuário atual para os campos {@code @CreatedBy}/{@code @LastModifiedBy}.
 *
 * <p>TODO: integrar com o contexto de autenticação. Exemplo com Spring Security:
 * {@code SecurityContextHolder.getContext().getAuthentication().getName()}.</p>
 */
@Component("auditorAware")
public class AuditorAwareImpl implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        // Stub: enquanto não há autenticação plugada, devolve "system".
        return Optional.of("system");
    }
}
"""


class CommonGenerator:
    """Gera todos os arquivos do pacote common (e common.validation)."""

    def __init__(self, ctx: GenContext):
        self.ctx = ctx

    def generate_all(self) -> list[GeneratedFile]:
        ctx = self.ctx
        files = [
            _file(ctx, "common", "SystemInfo", _SYSTEM_INFO),
            GeneratedFile(ctx.pkg("common"), "BaseEntity", _base_entity(ctx)),
            GeneratedFile(ctx.pkg("common"), "JpaAuditingConfig", _jpa_auditing_config(ctx)),
            _file(ctx, "common", "GenericRepository", _GENERIC_REPOSITORY),
            _file(ctx, "common", "GenericMapper", _GENERIC_MAPPER),
            _file(ctx, "common", "ApiResponse", _API_RESPONSE),
            _file(ctx, "common", "PageResponse", _PAGE_RESPONSE),
            _file(ctx, "common", "GenericService", _GENERIC_SERVICE),
            _file(ctx, "common", "GenericServiceImpl", _GENERIC_SERVICE_IMPL),
            _file(ctx, "common", "GenericSpecification", _GENERIC_SPECIFICATION),
            _file(ctx, "common.validation", "ValidationError", _VALIDATION_ERROR),
            _file(ctx, "common.validation", "ValidationException", _VALIDATION_EXCEPTION),
            _file(ctx, "common.validation", "ResourceNotFoundException", _RESOURCE_NOT_FOUND),
            _file(ctx, "common.validation", "GlobalExceptionHandler", _GLOBAL_HANDLER),
        ]
        if ctx.audit_user:
            files.append(_file(ctx, "common", "AuditorAwareImpl", _AUDITOR_AWARE))
        return files
