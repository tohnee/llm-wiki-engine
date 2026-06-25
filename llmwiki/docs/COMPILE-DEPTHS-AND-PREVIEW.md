# Compile Depths and Preview Contract

LLM-Wiki now exposes a preview for every compile depth so users can inspect compiled output after upload.

| Depth | Storage artifacts | Preview mode | Graph/Wiki behavior |
|---|---|---|---|
| D0 | chunks, spans, embeddings, summaries | `draft_summary` | No KG relations and no rendered wiki nodes. It is queryable through span search. |
| D1 | D0 + facts, entities, entity resolution | `draft_summary_with_facts` | Facts/entities are visible in preview, but relation graph/wiki node rendering is not produced. |
| D2 | D1 + typed relations + wiki nodes | `rendered_wiki_nodes` | Full typed KG is exported to the graph UI and rendered wiki pages are available. |

API:

- `GET /api/ingest/compile-depths` returns the depth capability table.
- `GET /api/ingest/documents/{document_id}/preview` returns rendered D2 wiki nodes when present, otherwise a D0/D1 draft preview from sections/facts.
