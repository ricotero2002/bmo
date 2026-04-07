# [Test Data Registry]

This document tracks all recognized test user IDs and documents created during test executions to facilitate debugging and data isolation.

## Registered Test Users

| User ID | Usage / Context | Location/Tests |
| :--- | :--- | :--- |
| `eval_golden_user` | Golden Dataset evaluations (RAG precision) | `src/tests/agente/test_rag_agentic.py`, `src/evals/seed_eval_data.py` |
| `test_user_cloud` | End-to-end cloud integration tests | `src/tests/integration/test_all_endpoints_cloud.py` |
| `test_user` | Standard unit and local integration tests | `src/tests/unit/test_api.py`, `src/tests/unit/test_delete.py`, etc. |
| `eval_user` | Alternative evaluation user | `src/tests/agente/test_agent_tools.py` |
| `test_user_1` | Scenario testing | Various integration tests |
| `anonymous` | Fallback for non-authenticated sessions | `src/api/endpoints.py` (ask_agent_stream) |

## Document Registry (Test Traces)

Recent documents created during integration or automated testing:

| Document Filename | User ID | Source (Doc ID) | Status/Notes |
| :--- | :--- | :--- | :--- |
| `test_cloud_05653209.txt` | `test_user_cloud` | `4be6a1d5-177f-4653...` | Succeeded in worker, failed in test poll due to ID collision. |
| `test_pinecone_upsert.md` | `None` / `test_user` | Dynamic | Used for unit testing Pinecone metadata cleaning. |
| `Evaluaciones_0.txt` | `eval_golden_user` | `eval_doc_fixed_0` | Part of the Golden Dataset seeded for RAG tests. |

## Pinecone Metadata Mapping

All documents in Pinecone should follow this strict metadata schema (no `null` allowed):
- `source`: String (doc_id)
- `user_id`: String (optional, omitted if missing)
- `filename`: String
- `created_at`: Unix Timestamp (Float)
- `chunk_index`: Integer
