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
| 5 | Retrieval improvements (BM25 + dense hybrid, RRF, reranker, measured evaluation) | Done |
| 6 | Employee chat interface (React), feedback, identity endpoints | Awaiting review |
| 7–9 | HR admin, security/evaluation, packaging | Not started |

## Repository layout

| Path | Contents |
|---|---|
| `backend/` | Python 3.11 FastAPI service, managed with uv — see [backend/README.md](backend/README.md) |
| `frontend/` | React + TypeScript employee chat interface — see [frontend/README.md](frontend/README.md) |
| `docker-compose.yml`, `docker/` | Local PostgreSQL 16 (development and test databases) and Qdrant (vector search) |
| `sample_data/` | **Fictional** sample policies for development — not real policies |

## Quick start

Prerequisites: [uv](https://docs.astral.sh/uv/getting-started/installation/) (it downloads Python 3.11 itself if needed), Docker Desktop, Node.js 22+, and [Ollama](https://ollama.com) with the `qwen3.5:9b` model for answering questions.

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

Then, in a second terminal, start the chat interface and open <http://localhost:5173>:

```bash
cd frontend
npm install
npm run dev
```
