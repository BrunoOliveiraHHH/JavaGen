# JavaGen

**Helper web que gera classes Java/Spring Boot a partir de um arquivo `.sql`.**

Você cola (ou envia) os `CREATE TABLE`, preenche algumas opções e baixa um `.zip`
com toda a estrutura de uma aplicação Spring Boot 3 pronta para colar no seu projeto:
entidades, DTOs (record), services genéricos, repositórios, filtros, specifications,
mapeadores, tratamento de exceções e resposta padronizada da API.

O Java gerado é validado por compilação (`javac` contra Spring Boot 3.4 / Java 17) —
veja [Validação](#validação).

---

## Sumário

- [Como rodar](#como-rodar)
- [Como usar](#como-usar)
- [O que é gerado](#o-que-é-gerado)
- [Recursos de SQL suportados](#recursos-de-sql-suportados)
- [Decisões de arquitetura do Java gerado](#decisões-de-arquitetura-do-java-gerado)
- [Arquitetura do projeto Python](#arquitetura-do-projeto-python)
- [Opções do formulário](#opções-do-formulário)
- [Validação](#validação)
- [Limitações e ideias futuras](#limitações-e-ideias-futuras)

---

## Como rodar

Requisitos: **Python 3.11+**.

```powershell
# 1. (opcional) ambiente virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. dependências (Flask + sqlglot)
pip install -r requirements.txt

# 3. subir a aplicação (abre o navegador automaticamente)
python app.py
```

A aplicação sobe em **http://127.0.0.1:5000**.

---

## Como usar

1. **SQL de origem** — clique em *Carregar SQL de exemplo*, cole seu DDL no campo de
   texto, ou envie um arquivo `.sql`.
2. **Configuração** — preencha o nome do sistema, o pacote base, o banco de origem
   (dialeto) e as opções de geração.
3. **Analisar SQL** (opcional) — mostra as tabelas/colunas detectadas antes de gerar.
4. **Gerar e baixar .zip** — o `.zip` é baixado e um aviso de sucesso aparece na tela.

> A cada geração, os arquivos são materializados numa pasta temporária `_output/`
> dentro do projeto e, em seguida, **ela é sempre limpa** (antes e depois). O download
> é entregue em memória.

---

## O que é gerado

Para o pacote base `com.sua.empresa.app`, a estrutura do `.zip` é:

```
src/main/java/com/sua/empresa/app/
├── common/
│   ├── ApiResponse.java            # envelope padrão (carimba o nome do sistema)
│   ├── PageResponse.java           # paginação própria (não expõe o Page do Spring)
│   ├── SystemInfo.java             # constante com o nome do sistema
│   ├── BaseEntity.java             # id + auditoria (criado/atualizado em/por)
│   ├── JpaAuditingConfig.java      # @EnableJpaAuditing
│   ├── AuditorAwareImpl.java       # usuário atual p/ a auditoria (stub)
│   ├── GenericRepository.java      # JpaRepository + JpaSpecificationExecutor (id Long)
│   ├── GenericMapper.java          # contrato toDto / toEntity
│   ├── GenericService.java         # CRUD + filtro paginado (interface)
│   ├── GenericServiceImpl.java     # implementação genérica (abstrata)
│   ├── GenericSpecification.java   # helpers de Predicate (like, equal, between, ...)
│   └── validation/                 # ValidationError, ValidationException,
│                                   # ResourceNotFoundException, GlobalExceptionHandler
├── entity/        ├── enums/       ├── dto/         ├── mapper/
├── filter/        ├── specification/├── repository/  ├── service/
├── service/impl/  └── controller/
```

Por tabela (ex.: `Pedido`): `Pedido`, `PedidoDto`, `PedidoMapper`, `PedidoFilter`,
`PedidoSpecification`, `PedidoRepository`, `PedidoService`, `PedidoServiceImpl`,
`PedidoController` (+ enums quando houver `CHECK ... IN (...)`).

---

## Recursos de SQL suportados

O parser usa **sqlglot** (com AST e ciente de dialeto) e tem um *fallback* por regex.
São lidos:

| Recurso SQL | Reflexo no Java |
|---|---|
| Tipos (VARCHAR, NUMERIC(p,s), BIGINT, BOOLEAN, DATE, TIMESTAMP, UUID, …) | tipo Java + `@Column(precision/scale)` |
| `VARCHAR(n)` | `@Column(length = n)` + validação de tamanho |
| `NOT NULL` | `@Column(nullable = false)` + validação de obrigatório |
| `UNIQUE` | `@Column(unique = true)` |
| `PRIMARY KEY` / `SERIAL` / `BIGSERIAL` | `@Id` + `@GeneratedValue` (via `BaseEntity`) |
| `FOREIGN KEY` (inline e de tabela) | **`@ManyToOne` (objeto, não Long)** + `@JoinColumn` |
| Tabela de junção (2 FKs) | **`@ManyToMany`** dos dois lados (ex.: perfis em usuários) |
| `CHECK (col IN (...))` | **enum Java** + `@Enumerated(STRING)` |
| `CHECK (col >= 0)` | validação `positive` no service |
| `CONSTRAINT ... CHECK` | `@Check` (Hibernate 6) na entidade |
| `CREATE INDEX` / `UNIQUE INDEX` | `@Table(indexes = @Index(...))` |
| Colunas de auditoria (`criado_em`, `atualizado_em`, ...) | herdadas de `BaseEntity` |

---

## Decisões de arquitetura do Java gerado

- **Service genérico**: `GenericService<E, D, F>` (entidade, DTO, filtro) + uma
  implementação abstrata `GenericServiceImpl`. O id é sempre `Long`.
  `create`/`update` são expostos ao controller (validam e mapeiam); `save` é interno
  (`saveAndFlush` — insert/update + flush do Hibernate).
- **Repository genérico**: `GenericRepository<E>` (`@NoRepositoryBean`) reúne
  `JpaRepository` + `JpaSpecificationExecutor`.
- **DTO**: um único `record` por entidade (sem separar request/response). FKs viram
  `<rel>Id` (escrita) + `<rel>Nome` (leitura). N:N vira `List<Long> <coleção>Ids`.
- **Mapper**: implementa `GenericMapper<E, D>`. No `toEntity`, as FKs são preenchidas
  apenas como **referência rasa** (só o id).
- **Resolução de relacionamentos no Service**: cada `XServiceImpl` injeta os
  repositórios das entidades relacionadas e, em `resolveRelationships`, troca as
  referências rasas pelas entidades gerenciadas via um método `getX(id)`
  (`findById` / referência). Relacionamentos carregam **EAGER**.
- **Filtro + Specification (separados)**: o `XFilter` é um record de dados; o
  `XSpecification` monta a `Specification` escolhendo o predicado pelo tipo do campo
  (String → `like`, data → `between` com início/fim, numérico/enum/FK → `equal`).
- **Validação**: gerada por entidade a partir das constraints, com mensagem padrão
  *"Campo {x} é obrigatório"* (e tamanho máximo, valor positivo, etc.).
- **Resposta padronizada**: `ApiResponse<T>` carimba o nome do sistema; erros são
  convertidos pelo `GlobalExceptionHandler` (`@RestControllerAdvice`).

---

## Arquitetura do projeto Python

```
app.py                 # rotas Flask (/, /sample, /preview, /generate)
config.py              # caminhos e defaults
parser/                # SQL -> modelo de dados
  ├── model.py         #   dataclasses (Schema, Table, Column, ForeignKey, ManyToMany, ...)
  ├── type_mapper.py   #   tipos SQL -> Java
  └── sql_parser.py    #   sqlglot (primário) + fallback regex
generator/             # modelo -> código Java
  ├── base.py, dto_model.py, filtering.py      # infra/helpers
  ├── common_generator.py                       # classes do pacote common
  ├── entity/enum/dto/mapper/filter/specification/repository/service/
  │   service_impl/controller_generator.py      # um por artefato
  └── orchestrator.py                           # junta tudo -> lista de arquivos
utils/                 # naming, fileio (limpeza segura), zipper
templates/index.html   # formulário
static/                # style.css, app.js, sample.sql (SQL de exemplo)
```

Camadas desacopladas: `parser/` não conhece Java; `generator/` não conhece SQL nem
Flask; `utils/` é puro; `app.py` só orquestra o HTTP.

---

## Opções do formulário

| Campo | Descrição | Padrão |
|---|---|---|
| Nome do sistema | usado no `ApiResponse` (`SystemInfo.SYSTEM_NAME`) | `SISTEMA` |
| Pacote base | raiz dos pacotes Java | `com.exemplo.app` |
| Banco de origem | dialeto do SQL (PostgreSQL, MySQL, SQL Server, Oracle, SQLite) | PostgreSQL |
| Base path da API | prefixo das rotas REST | `/api` |
| Usar Lombok | `@Getter/@Setter/...` nas entidades | ligado |
| Relacionamento inverso | gera `@OneToMany` no lado pai | ligado |
| Enums de CHECK IN | gera enums Java | ligado |
| Anotações OpenAPI | `@Tag/@Operation/@Schema` (springdoc) | ligado |
| Auditoria com usuário | `criadoPor/atualizadoPor` + `AuditorAware` | ligado |
| Soft delete | `@SQLDelete` + `@SQLRestriction` + campo `deleted` | desligado |

---

## Validação

O Java gerado a partir do `static/sample.sql` (7 tabelas — clientes, categorias,
produtos, pedidos e o N:N usuário/perfil) **compila sem erros** com `javac` usando
as dependências do Spring Boot 3.4 (Spring 6.2, Spring Data JPA 3.4, Hibernate 6.6,
Jakarta Persistence 3.1, Lombok, springdoc/Swagger, Jackson).

Para validar num projeto real: crie um projeto Spring Boot 3 (Java 17+) com
`spring-boot-starter-data-jpa`, `spring-boot-starter-web`, `lombok` e
`springdoc-openapi-starter-webmvc-ui`, cole o conteúdo do `.zip` em `src/main/java`
e rode `mvn compile`.

---

## Limitações e ideias futuras

- **PK composta** (não-junção) é sinalizada com `// TODO` (use `@EmbeddedId`/`@IdClass`).
- A **pluralização** de coleções é heurística (PT/EN) — revise nomes quando necessário.
- `AuditorAwareImpl` é um *stub* (`"system"`); plugue seu contexto de autenticação.
- Próximos passos possíveis: Bean Validation no DTO, MapStruct, classes de teste
  (`@DataJpaTest`/`@WebMvcTest`), projeto runnable completo (pom.xml + Application),
  e migrações Flyway.
