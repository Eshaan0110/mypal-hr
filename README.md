# My Pal — HR Policy Chatbot (prototype)

A retrieval-augmented (RAG) chatbot that answers employee HR policy questions from HR-approved policy documents, with source citations and a referral to HR when the evidence is insufficient. This is a **prototype** for one business unit, not a production system.

## Status

| Phase | Scope | State |
|---|---|---|
| 0 | Repository inspection and architecture | Done |
| 1 | Backend foundation (FastAPI, settings, health, errors, logging, tests) | Done |
| 2 | Database foundation (PostgreSQL, schema, migrations) | Awaiting review |
| 3–9 | Ingestion, RAG, retrieval, chat UI, HR admin, security/evaluation, packaging | Not started |

## Repository layout

| Path | Contents |
|---|---|
| `backend/` | Python 3.11 FastAPI service, managed with uv — see [backend/README.md](backend/README.md) |
| `docker-compose.yml`, `docker/` | Local PostgreSQL 16 (development and test databases) |

## Quick start

Prerequisites: [uv](https://docs.astral.sh/uv/getting-started/installation/) (it downloads Python 3.11 itself if needed) and Docker Desktop.

```bash
docker compose up -d
cd backend
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run pytest
uv run uvicorn mypal.main:create_app --factory --reload
```

Then open <http://127.0.0.1:8000/api/health>.
