-- 001_compile_lifecycle.sql
-- Adds observable compile lifecycle fields and a trigram fallback index for CJK/exact-term retrieval.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS compile_error TEXT NOT NULL DEFAULT '';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
-- Partition-local trigram indexes are created by Store.ensure_tenant_partition for new tenants.
