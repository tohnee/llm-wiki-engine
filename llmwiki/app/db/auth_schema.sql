-- 鉴权与管理的全局表(非 tenant 分区——它们是租户/用户注册表本身)。
-- 与 app/db/schema.sql 一起加载。

CREATE TABLE IF NOT EXISTS tenants (
    tenant_id   TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active',   -- active | suspended
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    user_id      TEXT NOT NULL,
    tenant_id    TEXT NOT NULL REFERENCES tenants(tenant_id),
    email        TEXT NOT NULL,
    password_hash TEXT NOT NULL,                  -- pbkdf2$iterations$salt$hash
    role         TEXT NOT NULL DEFAULT 'member',  -- admin | member | viewer
    status       TEXT NOT NULL DEFAULT 'active',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, user_id),
    UNIQUE (email)
);

-- 会话记忆的持久副本(热副本在 Redis;此表用于跨重启恢复与审计)。
-- 严格按 (tenant_id, user_id, session_id) 三元组隔离。
CREATE TABLE IF NOT EXISTS conversations (
    tenant_id   TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    turns       JSONB NOT NULL DEFAULT '[]',       -- [{role, content, ts}]
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, user_id, session_id)
);
CREATE INDEX IF NOT EXISTS conversations_tenant ON conversations (tenant_id, user_id);

-- 审计日志(治理层:每个操作留痕,可追溯)。
CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    user_id     TEXT NOT NULL DEFAULT 'system',
    action      TEXT NOT NULL,          -- ingest|edit|delete|query|supersede|crystallize|decay
    target      TEXT NOT NULL DEFAULT '',
    detail      JSONB NOT NULL DEFAULT '{}',
    ts          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS audit_tenant_ts ON audit_log (tenant_id, ts DESC);

-- 观察/情景记忆(consolidation tiers:working→episodic→semantic→procedural)。
CREATE TABLE IF NOT EXISTS observations (
    obs_id       TEXT NOT NULL,
    tenant_id    TEXT NOT NULL,
    user_id      TEXT NOT NULL DEFAULT 'system',
    session_id   TEXT NOT NULL DEFAULT '',
    tier         TEXT NOT NULL DEFAULT 'working',  -- working|episodic|semantic|procedural
    content      TEXT NOT NULL,
    confidence   REAL NOT NULL DEFAULT 0.5,
    retention    REAL NOT NULL DEFAULT 1.0,
    access_count INT NOT NULL DEFAULT 0,
    created_at   DOUBLE PRECISION NOT NULL DEFAULT 0,
    last_access  DOUBLE PRECISION NOT NULL DEFAULT 0,
    promoted_to  TEXT,
    PRIMARY KEY (tenant_id, obs_id)
);
CREATE INDEX IF NOT EXISTS obs_tier ON observations (tenant_id, tier);
