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
| 6 | Employee chat interface (React), feedback, identity endpoints | Done |
| 7 | HR administration portal (upload, preview, review, approve, publish, replace, restore) | Done |
| 8 | Security tests by threat, whole-answer evaluation harness, documented limitations | Done |
| 9 | Packaging (whole prototype in Docker Compose, one-command demo data), operations runbook, handover | Awaiting review |

Policies are uploaded, reviewed, approved, published and rolled back in the HR admin portal (HR administrators only); the command-line tools in [backend/README.md](backend/README.md) remain for development and recovery.

Everything in this repository uses **fictional** sample policies, companies and users. No real policy, employee data or credential is included. Start with [docs/handover.md](docs/handover.md), which links every other document. [docs/My_Pal_Technical_Design.docx](docs/My_Pal_Technical_Design.docx) is the design document written for IT before phases 7–9. Security controls, test evidence, evaluation results and known limitations are in [docs/security-and-evaluation.md](docs/security-and-evaluation.md). How to run, back up, update and roll back the prototype is in [docs/operations.md](docs/operations.md). What is still open with HR and IT, the operational risks and the production-hardening plan are in the handover.

## Repository layout

| Path | Contents |
|---|---|
| `backend/` | Python 3.11 FastAPI service, managed with uv — see [backend/README.md](backend/README.md) |
| `frontend/` | React + TypeScript employee chat interface and HR admin portal — see [frontend/README.md](frontend/README.md) |
| `docker-compose.yml`, `docker/` | PostgreSQL 16 (development and test databases) and Qdrant; with the `app` profile, also the backend and frontend containers |
| `sample_data/` | **Fictional** sample policies for development — not real policies |
| `docs/` | Operations runbook, handover, security and evaluation report, technical design document |

## Quick start

Prerequisites: Docker Desktop and [Ollama](https://ollama.com) with the `qwen3.5:9b` model (`ollama pull qwen3.5:9b`). For development you also need [uv](https://docs.astral.sh/uv/getting-started/installation/) (it downloads Python 3.11 itself) and Node.js 22+.

**Run the whole prototype in Docker.** Copy the settings file, then replace each `CHANGE_ME` in `.env` with your own random value (letters and digits):

```bash
cp .env.example .env
```

```bash
docker compose --profile app up -d --build
```

```bash
docker compose exec backend mypal-ingest load-demo --folder /sample_data/policies
```

Open <http://127.0.0.1:8080> and choose a user in the "Dev login" picker. The last command loads the **fictional** sample policies through the normal review-and-publish lifecycle. On Git Bash for Windows, prefix it with `MSYS_NO_PATHCONV=1`.

**Develop** with the backend and frontend running on your machine (reloading on every change), and run the tests: see [docs/operations.md](docs/operations.md#b-development-mode).
