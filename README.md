# My Pal — HR Policy Chatbot (prototype)

A retrieval-augmented (RAG) chatbot that answers employee HR policy questions from HR-approved policy documents, with source citations and a referral to HR when the evidence is insufficient. This is a **prototype** for one business unit, not a production system.

## Status

| Phase | Scope | State |
|---|---|---|
| 0 | Repository inspection and architecture | Done |
| 1 | Backend foundation (FastAPI, settings, health, errors, logging, tests) | Done |
| 2 | Database foundation (PostgreSQL, schema, migrations) | Done |
| 3 | Document ingestion (PDF/DOCX parsing, quality checks, chunking, drafts) | Done |
| 4 | Basic RAG (embeddings, Qdrant, scope gate, grounded cited answers, HR referral) | Done |
| 5 | Retrieval improvements (BM25 + dense hybrid, RRF, reranker, measured evaluation) | Awaiting review |
| 6–9 | Chat UI, HR admin, security/evaluation, packaging | Not started |

## Repository layout

| Path | Contents |
|---|---|
| `backend/` | Python 3.11 FastAPI service, managed with uv — see [backend/README.md](backend/README.md) |
| `docker-compose.yml`, `docker/` | Local PostgreSQL 16 (development and test databases) and Qdrant (vector search) |
| `sample_data/` | **Fictional** sample policies for development — not real policies |

## Quick start

Prerequisites: [uv](https://docs.astral.sh/uv/getting-started/installation/) (it downloads Python 3.11 itself if needed), Docker Desktop, and [Ollama](https://ollama.com) with the `qwen3.5:9b` model for answering questions.

```bash
cp .env.example .env            # then set your own MYPAL_DB_PASSWORD and MYPAL_QDRANT_API_KEY
docker compose up -d
cd backend
uv sync
cp .env.example .env            # then use the same password and Qdrant key here
uv run alembic upgrade head
uv run pytest
uv run uvicorn mypal.main:create_app --factory --reload
```

Then open <http://127.0.0.1:8000/api/health>.
