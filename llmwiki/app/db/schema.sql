-- LLM-Wiki 存储 schema。Postgres 16 + pgvector。
-- 隔离策略:核心表按 tenant_id 做 LIST 分区(物理隔离),所有查询强制带分区键。
-- pgvector 承载 span 级向量检索;D0/D1 不依赖图数据库。

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- BM25 近似 / 模糊匹配辅助

-- ============ 文档与任务 ============
CREATE TABLE IF NOT EXISTS documents (
    document_id   TEXT NOT NULL,
    tenant_id     TEXT NOT NULL,
    title         TEXT NOT NULL,
    source_uri    TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'uploaded',
    depth         TEXT NOT NULL DEFAULT 'D1',
    page_count    INT  NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, document_id)
) PARTITION BY LIST (tenant_id);

-- ============ 上下文单元 chunk(parent) ============
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id      TEXT NOT NULL,
    tenant_id     TEXT NOT NULL,
    document_id   TEXT NOT NULL,
    content       TEXT NOT NULL,
    page_start    INT  NOT NULL,
    page_end      INT  NOT NULL,
    section_path  TEXT NOT NULL DEFAULT '',
    content_hash  TEXT NOT NULL,
    summary       TEXT NOT NULL DEFAULT '',     -- ≤200 字符,tier-0 摘要扫描
    tier          TEXT,                          -- core/supporting/peripheral
    PRIMARY KEY (tenant_id, chunk_id)
) PARTITION BY LIST (tenant_id);

-- ============ 证据原子 span(child,citation 落点) ============
CREATE TABLE IF NOT EXISTS spans (
    span_id       TEXT NOT NULL,
    tenant_id     TEXT NOT NULL,
    chunk_id      TEXT NOT NULL,
    document_id   TEXT NOT NULL,
    content       TEXT NOT NULL,
    page          INT  NOT NULL,
    bbox          REAL[4],
    span_type     TEXT NOT NULL DEFAULT 'text',
    embedding     vector(1024),
    tsv           tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
    PRIMARY KEY (tenant_id, span_id)
) PARTITION BY LIST (tenant_id);

-- ============ 导航层 ============
CREATE TABLE IF NOT EXISTS facts (
    fact_id          TEXT NOT NULL,
    tenant_id        TEXT NOT NULL,
    document_id      TEXT NOT NULL,
    subject_entity   TEXT NOT NULL,
    predicate        TEXT NOT NULL,
    object_value     TEXT NOT NULL,
    qualifiers       JSONB NOT NULL DEFAULT '{}',
    confidence       REAL NOT NULL DEFAULT 1.0,
    provenance       TEXT NOT NULL DEFAULT 'extracted',  -- extracted/inferred/ambiguous
    contradicts      TEXT[] NOT NULL DEFAULT '{}',        -- 冲突的 fact_id
    source_count     INT NOT NULL DEFAULT 1,              -- 来源数(强化信号)
    created_at       DOUBLE PRECISION NOT NULL DEFAULT 0,
    last_confirmed   DOUBLE PRECISION NOT NULL DEFAULT 0,
    retention        REAL NOT NULL DEFAULT 1.0,           -- Ebbinghaus 保留度
    superseded_by    TEXT,                                -- 版本化:被哪个 fact 取代
    stale            BOOLEAN NOT NULL DEFAULT FALSE,
    source_span_ids  TEXT[] NOT NULL DEFAULT '{}',
    source_hash      TEXT NOT NULL,
    PRIMARY KEY (tenant_id, fact_id)
) PARTITION BY LIST (tenant_id);

CREATE TABLE IF NOT EXISTS entities (
    entity_id        TEXT NOT NULL,
    tenant_id        TEXT NOT NULL,
    name             TEXT NOT NULL,
    aliases          TEXT[] NOT NULL DEFAULT '{}',
    type             TEXT NOT NULL,
    description      TEXT NOT NULL DEFAULT '',
    mention_span_ids TEXT[] NOT NULL DEFAULT '{}',
    document_ids     TEXT[] NOT NULL DEFAULT '{}',
    name_block       TEXT NOT NULL,        -- blocking key: 归一化名首token + type
    embedding        vector(1024),
    PRIMARY KEY (tenant_id, entity_id)
) PARTITION BY LIST (tenant_id);

CREATE TABLE IF NOT EXISTS relations (
    relation_id      TEXT NOT NULL,
    tenant_id        TEXT NOT NULL,
    source_entity    TEXT NOT NULL,
    relation_type    TEXT NOT NULL,
    target_entity    TEXT NOT NULL,
    source_span_ids  TEXT[] NOT NULL DEFAULT '{}',
    confidence       REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (tenant_id, relation_id)
) PARTITION BY LIST (tenant_id);

CREATE TABLE IF NOT EXISTS wiki_nodes (
    node_id     TEXT NOT NULL,
    tenant_id   TEXT NOT NULL,
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    entity_id   TEXT,
    children    TEXT[] NOT NULL DEFAULT '{}',
    provenance_mix JSONB NOT NULL DEFAULT '{}',
    tier        TEXT,
    PRIMARY KEY (tenant_id, node_id)
) PARTITION BY LIST (tenant_id);

-- ============ 索引(注意:索引建在各分区上;此处给模板,分区创建时一并建) ============
-- 见 app/db/store.py:ensure_tenant_partition() 在新建租户分区时执行下列索引创建。
