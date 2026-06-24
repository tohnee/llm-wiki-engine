# Source Capability Crosscheck

This inventory maps the two reference streams requested by product review to concrete source modules.

## obsidian-wiki absorbed capabilities

| Capability | Source implementation | Status | Gap closed in this pass |
|---|---|---|---|
| Epistemic provenance states | `app/models/schema.py` `Provenance`; `app/compile/contradiction.py` | Implemented | Compile failure now records observable document error state instead of print-only fallback. |
| Contradiction detection and supersession | `app/compile/orchestrator.py`, `app/memory/quality.py` | Implemented | Failure status is persisted for D1/D2 errors. |
| Knowledge lint / hub-weighted repair priority | `app/maintain/lint.py` | Implemented | No code gap found in offline smoke coverage. |
| Tier-0 summaries and importance tiers | `app/evidence/tiered.py`, `chunks.summary`, `chunks.tier` | Implemented | Stable chunk IDs make summary/manifest reuse meaningful. |
| Evidence-first citations | `spans`, `/read_span`, `/expand`, verify pass | Implemented | Query Gateway now returns citations and claim verification details. |

## LLM-Wiki v2 absorbed capabilities

| Capability | Source implementation | Status | Gap closed in this pass |
|---|---|---|---|
| Memory lifecycle: confidence, reinforcement, decay | `Fact.source_count`, `retention`, `superseded_by`; `app/memory/lifecycle.py` | Implemented | Compile lifecycle errors are now stored on `documents`. |
| Typed KG entities and relations | `entities`, `relations`, L2/L3 workers | Implemented | Worker and inline compile now share manifest-enabled orchestrator semantics. |
| Hybrid retrieval: BM25 + vectors + graph + RRF | `app/evidence/retrieval.py` | Implemented | Added pg_trgm fallback stream for Chinese/mixed text when simple tsvector misses. |
| Event automation hooks | `app/core/hooks.py`, `app/core/hook_handlers.py` | Partial | Not expanded in this pass; documented as existing partial implementation. |
| Quality controls and self-correction | `app/query/verify.py`, `app/maintain/lint.py` | Implemented | API now surfaces verify claims to clients for review. |
| Privacy/governance | `app/core/governance.py`, `security_guard.py` | Partial | Added SQL migration runner foundation for auditable schema evolution. |
| Crystallization | `app/memory/crystallize.py`, query hook | Partial | No behavioral change in this pass. |
| Output formats beyond markdown | `app/generation/*`, frontend generate view | Implemented | No gap found in smoke coverage. |
| Schema-driven knowledge work | `app/core/schema_layer.py`, admin schema API | Implemented | No gap found in smoke coverage. |

## Remaining non-trivial gaps

1. Mesh sync / multi-agent work coordination is not a first-class product surface yet.
2. Full audit trail for every operation should be added as an `audit_log` table plus write hooks.
3. True remote reranker API support is still absent; code now documents the fallback honestly.
4. MinerU page/bbox fidelity depends on callers passing `page_map`; bbox extraction still needs MinerU coordinates.
