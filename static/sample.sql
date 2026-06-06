-- =====================================================================
-- MODELO DE REFERÊNCIA — JavaGen
-- Exercita os recursos suportados pelo gerador:
--   VARCHAR(n), CHAR(n), TEXT, NUMERIC(p,s), DOUBLE PRECISION, INTEGER,
--   BOOLEAN, DATE, TIMESTAMP, NOT NULL, UNIQUE, DEFAULT, PRIMARY KEY,
--   FOREIGN KEY (inline) com ON DELETE, CONSTRAINT nomeada, CHECK
--   (numérico e IN -> enum) e CREATE INDEX / CREATE UNIQUE INDEX.
-- Dialeto base: PostgreSQL.
-- =====================================================================

-- ---------------------------------------------------------------------
-- CLIENTE
-- ---------------------------------------------------------------------
CREATE TABLE cliente (
    id              BIGSERIAL     PRIMARY KEY,
    nome            VARCHAR(120)  NOT NULL,
    email           VARCHAR(180)  NOT NULL UNIQUE,
    cpf             CHAR(11)      UNIQUE,
    telefone        VARCHAR(20),
    limite_credito  NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    ativo           BOOLEAN       NOT NULL DEFAULT TRUE,
    data_nascimento DATE,
    criado_em       TIMESTAMP     NOT NULL DEFAULT NOW(),
    atualizado_em   TIMESTAMP,
    CONSTRAINT chk_cliente_limite CHECK (limite_credito >= 0)
);

CREATE INDEX idx_cliente_nome ON cliente (nome);
CREATE UNIQUE INDEX idx_cliente_email ON cliente (email);

-- ---------------------------------------------------------------------
-- CATEGORIA
-- ---------------------------------------------------------------------
CREATE TABLE categoria (
    id        BIGSERIAL    PRIMARY KEY,
    nome      VARCHAR(80)  NOT NULL UNIQUE,
    descricao VARCHAR(255),
    ativa     BOOLEAN      NOT NULL DEFAULT TRUE
);

-- ---------------------------------------------------------------------
-- PRODUTO  (FK -> categoria, enum de status via CHECK IN)
-- ---------------------------------------------------------------------
CREATE TABLE produto (
    id            BIGSERIAL     PRIMARY KEY,
    sku           VARCHAR(40)   NOT NULL UNIQUE,
    descricao     VARCHAR(255)  NOT NULL,
    categoria_id  BIGINT        NOT NULL REFERENCES categoria(id) ON DELETE RESTRICT,
    preco         NUMERIC(10,2) NOT NULL,
    estoque       INTEGER       NOT NULL DEFAULT 0,
    peso          DOUBLE PRECISION,
    status        VARCHAR(20)   NOT NULL DEFAULT 'ATIVO',
    criado_em     TIMESTAMP     NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMP,
    CONSTRAINT chk_produto_preco   CHECK (preco >= 0),
    CONSTRAINT chk_produto_estoque CHECK (estoque >= 0),
    CONSTRAINT chk_produto_status  CHECK (status IN ('ATIVO', 'INATIVO', 'DESCONTINUADO'))
);

CREATE INDEX idx_produto_categoria ON produto (categoria_id);

-- ---------------------------------------------------------------------
-- PEDIDO  (FK -> cliente, enum de status, CHECK numérico)
-- ---------------------------------------------------------------------
CREATE TABLE pedido (
    id            BIGSERIAL     PRIMARY KEY,
    numero        VARCHAR(30)   NOT NULL UNIQUE,
    cliente_id    BIGINT        NOT NULL REFERENCES cliente(id) ON DELETE CASCADE,
    data_pedido   DATE          NOT NULL,
    valor_total   NUMERIC(14,2) NOT NULL DEFAULT 0.00,
    desconto      NUMERIC(5,2)  NOT NULL DEFAULT 0.00,
    pago          BOOLEAN       NOT NULL DEFAULT FALSE,
    status        VARCHAR(20)   NOT NULL DEFAULT 'ABERTO',
    observacao    TEXT,
    criado_em     TIMESTAMP     NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMP,
    CONSTRAINT chk_pedido_valor  CHECK (valor_total >= 0),
    CONSTRAINT chk_pedido_status CHECK (status IN ('ABERTO', 'PAGO', 'CANCELADO'))
);

CREATE INDEX idx_pedido_cliente ON pedido (cliente_id);
CREATE INDEX idx_pedido_status ON pedido (status);

-- ---------------------------------------------------------------------
-- USUARIO / PERFIL / USUARIO_PERFIL  (relacionamento N:N — perfis em usuários)
-- ---------------------------------------------------------------------
CREATE TABLE usuario (
    id            BIGSERIAL    PRIMARY KEY,
    nome          VARCHAR(120) NOT NULL,
    login         VARCHAR(60)  NOT NULL UNIQUE,
    senha         VARCHAR(255) NOT NULL,
    ativo         BOOLEAN      NOT NULL DEFAULT TRUE,
    criado_em     TIMESTAMP    NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMP
);

CREATE TABLE perfil (
    id        BIGSERIAL   PRIMARY KEY,
    nome      VARCHAR(60) NOT NULL UNIQUE,
    descricao VARCHAR(255)
);

-- Tabela de junção pura: vira @ManyToMany (não é gerada como entidade).
CREATE TABLE usuario_perfil (
    usuario_id BIGINT NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    perfil_id  BIGINT NOT NULL REFERENCES perfil(id)  ON DELETE CASCADE,
    CONSTRAINT pk_usuario_perfil PRIMARY KEY (usuario_id, perfil_id)
);
