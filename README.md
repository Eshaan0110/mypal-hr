# My Pal — HR Policy Chatbot (prototype)

A retrieval-augmented (RAG) chatbot that answers employee HR policy questions from HR-approved policy documents, with source citations and a referral to HR when the evidence is insufficient. This is a **prototype** for one business unit, not a production system.

## Status

| Phase | Scope | State |
|---|---|---|
| 0 | Repository inspection and architecture | Done |
| 1 | Backend foundation (FastAPI, settings, health, errors, logging, tests) | Awaiting review |
| 2–9 | Database, ingestion, RAG, retrieval, chat UI, HR admin, security/evaluation, packaging | Not started |

## Repository layout

| Path | Contents |
|---|---|
| `backend/` | Python 3.11 FastAPI service, managed with uv — see [backend/README.md](backend/README.md) |

## Quick start

Prerequisite: [uv](https://docs.astral.sh/uv/getting-started/installation/). uv downloads Python 3.11 itself if needed.

```bash
cd backend
uv sync
uv run pytest
uv run uvicorn mypal.main:create_app --factory --reload
```

Then open <http://127.0.0.1:8000/api/health>.
