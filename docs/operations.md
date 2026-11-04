# My Pal: operations runbook (prototype)

How to set up, run, load, test, back up, update and roll back the My Pal prototype. Everything here was carried out on a fresh copy of the repository on 2026-11-03 (see *Verification* at the end).

The prototype runs on **one machine, for development and demonstration**. It cannot be deployed to staging or production yet: the login is a development stand-in that refuses to start outside `development` and `test` (see [handover.md](handover.md)).

## 1. Two ways to run it

| | A. Whole prototype in Docker | B. Development mode |
|---|---|---|
| For | Demonstrations; anyone who wants it running without Python or Node | Changing the code |
| Postgres, Qdrant | Containers | Containers |
| Backend | Container (built from `uv.lock`) | `uv run uvicorn ... --reload` on the host |
| Frontend | Container (nginx serving the built app) | `npm run dev` on the host (Vite) |
| Open | <http://127.0.0.1:8080> | <http://localhost:5173> |
| Language model | Ollama on the host, or `MYPAL_LLM_BASE_URL` | Ollama on the host, or `MYPAL_LLM_BASE_URL` |

The language model is never a container. Ollama runs on the host (it needs the GPU or a lot of memory), and IT plans to provide a hosted OpenAI-compatible endpoint instead. Changing models is configuration only.

### Prerequisites

| Tool | Needed for | Check |
|---|---|---|
| Docker Desktop (Compose v2) | A and B | `docker compose version` |
| [Ollama](https://ollama.com) with `qwen3.5:9b` | Answering questions (A and B) | `ollama list` |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | B, tests, evaluation | `uv --version` |
| Node.js 22+ | B (frontend) | `node --version` |
| Internet access on first use | Downloading Docker images, Python packages and the embedding and reranker models (about 150 MB) | |

```bash
ollama pull qwen3.5:9b
```

## 2. First-time setup

From the repository root. Copy the example settings, then replace each `CHANGE_ME` with a long random value of your own (letters and digits only, because the password is also used inside a database URL):

```bash
cp .env.example .env
```

`.env` is git-ignored. Never commit it, and never put a real password in any committed file.

### A. Whole prototype in Docker

```bash
docker compose --profile app up -d --build
```

This starts Postgres and Qdrant, runs the database migrations once (`migrate`), and then starts the backend and the frontend. The backend only starts if the migrations succeeded, and the frontend only once the backend reports ready. Then load the fictional demo policies, once:

```bash
docker compose exec backend mypal-ingest load-demo --folder /sample_data/policies
```

Open <http://127.0.0.1:8080> and pick a user in the "Dev login" picker (for example `dev-employee-north`). The first question takes longer, because the embedding and reranker models are downloaded once into the `models` volume and Ollama loads the model into memory.

*Git Bash on Windows:* it rewrites `/sample_data/...` into a Windows path. Prefix the command with `MSYS_NO_PATHCONV=1`, or use PowerShell.

### B. Development mode

```bash
docker compose up -d
cd backend
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run mypal-ingest load-demo
uv run uvicorn mypal.main:create_app --factory --reload
```

- `docker compose up -d` (without the profile) starts only Postgres and Qdrant.
- In `backend/.env`, use the same database password (in both database URLs) and the same Qdrant key as in the root `.env`.
- `uv sync` installs exactly the versions in `uv.lock`, into `backend/.venv`, with Python 3.11.

In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

### What `load-demo` does

It loads the four fictional sample files from `sample_data/policies` through the **normal lifecycle**:
1. Upload as a draft by `dev-hr-admin`.
2. Submit for review.
3. Approve by `dev-hr-reviewer` (four-eyes rule).
4. Publish.
5. Restore leave-policy v1, demonstrating the rollback.

**End state:** leave v1, travel v1 and salary-advance v1 active; leave v2 superseded. This is the state the evaluation question sets expect. It refuses to run if any demo policy already exists, so it cannot create duplicates.

## 3. Configuration

All backend settings are environment variables with the `MYPAL_` prefix, read in one place (`backend/src/mypal/config.py`):
- **Development mode:** they come from `backend/.env`.
- **Docker profile:** they come from `docker-compose.yml`, which takes the secrets from the root `.env`.

| Setting | Default | Notes |
|---|---|---|
| `MYPAL_DATABASE_URL` | none (required) | The app refuses to start without it. **Secret.** |
| `MYPAL_TEST_DATABASE_URL` | none | Tests only. The database name must end in `_test`; the tests drop all its tables. |
| `MYPAL_QDRANT_URL` | `http://127.0.0.1:6333` | |
| `MYPAL_QDRANT_API_KEY` | none | **Secret.** Must match the Qdrant container's key. |
| `MYPAL_QDRANT_COLLECTION` | `policy_chunks` | Use a separate collection for a separate data set. |
| `MYPAL_LLM_BASE_URL` | `http://127.0.0.1:11434/v1` | Any OpenAI-compatible API. In Docker: `http://host.docker.internal:11434/v1`. |
| `MYPAL_LLM_MODEL` | `qwen3.5:9b` | |
| `MYPAL_LLM_API_KEY` | none | Not needed for Ollama. **Secret** for a hosted endpoint. |
| `MYPAL_LLM_TIMEOUT_SECONDS` | `180` | |
| `MYPAL_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Changing it requires `mypal-policy reindex --recreate`. |
| `MYPAL_RERANKER_MODEL` | `Xenova/ms-marco-MiniLM-L-6-v2` | Empty for none. |
| `MYPAL_RETRIEVAL_MODE` | `hybrid` | `dense` or `hybrid`. |
| `MYPAL_RETRIEVAL_MIN_SCORE` | `0.55` | Confidence gate. Re-measure on real policies. |
| `MYPAL_CHAT_MAX_CONCURRENT` | `4` | Questions answered at the same time. Others wait without holding a thread or a database connection. Raise it only if the model server answers several questions in parallel. |
| `MYPAL_CHAT_QUEUE_TIMEOUT_SECONDS` | `90` | A question that cannot start within this time gets "busy, try again" (503). Keep it plus the slowest answer under the browser's 180 s limit. |
| `MYPAL_DATABASE_POOL_SIZE`, `MYPAL_DATABASE_MAX_OVERFLOW` | `20`, `20` | Database connections. The backend runs at most this many worker threads (40), so a request never waits for a connection. Postgres allows 100 by default. |
| `MYPAL_DATABASE_POOL_TIMEOUT` | `10` | Seconds to wait for a free connection before answering "busy" (503). |
| `MYPAL_ENVIRONMENT` | `development` | `development`, `test`, `staging` or `production`. The dev login only allows the first two. |
| `MYPAL_LOG_JSON` | `true` | `false` gives readable lines in a terminal. |
| `MYPAL_LOG_LEVEL` | `INFO` | |
| `MYPAL_CORS_ORIGINS` | `[]` | Not needed when the frontend is served from the same origin (both run modes). |
| `MYPAL_DEV_USERS_FILE` | none | Path to a JSON file of development login users that **replaces** the built-in fictional ones (section 5). Development login only. |
| `MYPAL_DATA_NOTICE` | `fictional sample policies` | What the loaded policies are, shown in the banner on every screen. |

Root `.env` (Docker Compose):

| Setting | Notes |
|---|---|
| `MYPAL_DB_PASSWORD` | Required. |
| `MYPAL_QDRANT_API_KEY` | Required. |
| `MYPAL_DB_PORT`, `MYPAL_QDRANT_PORT`, `MYPAL_WEB_PORT` | Optional. Host ports, if 5432, 6333 or 8080 are taken. |
| `MYPAL_LLM_BASE_URL`, `MYPAL_LLM_MODEL`, `MYPAL_LLM_API_KEY` | Optional. The model the backend container uses. |

All published ports are bound to `127.0.0.1`, so nothing is reachable from the network. In the Docker profile, the backend has no published port at all; only the frontend's nginx reaches it.

**Secrets.** `.env` files are a development compromise. A shared environment must take the database URL, the Qdrant key and any model key from the approved secret store (for example Azure Key Vault). This decision is still open with IT.

## 4. Database migrations

Docker profile: the `migrate` service runs `alembic upgrade head` on every `up`. Development mode, from `backend/`:

| Task | Command |
|---|---|
| Apply all migrations | `uv run alembic upgrade head` |
| Show the current revision | `uv run alembic current` |
| Check models and migrations agree | `uv run alembic check` |
| Undo the last migration | `uv run alembic downgrade -1` |

**Take a backup before any migration on data you care about** (section 7). Downgrades exist, but a downgrade that drops a column also drops its data.

## 5. Loading and managing policies

- **Normal route:** the HR admin portal (HR admin tab; `dev-hr-admin` or `dev-hr-reviewer`). Upload, preview, submit; a second administrator approves and publishes. See [backend/README.md](../backend/README.md#hr-administration-phase-7).
- **Recovery route:** the same lifecycle from the command line (`mypal-policy submit | approve | reject | publish | restore`).
- **Fictional demo data:** `mypal-ingest load-demo` (section 2).

**Real policies** must not be stored in this repository or committed anywhere public. Load them through the portal into a database that is not shared. For a separate test data set, use a different database and a different `MYPAL_QDRANT_COLLECTION`.

### Running the app on a separate data set

The fictional dev users belong to the fictional company, so they see nothing in a data set with other scope codes. To use a separate set (for example real policies loaded on one machine), keep these **outside the repository**:

1. A users file, a JSON list in the same shape as the built-in users. Subjects must start with `dev-`, codes are upper case, and the only role is `hr_admin`. Include two HR administrators, so that the four-eyes rule can be used.

   ```json
   [
     {"subject": "dev-acme-employee", "company_code": "ACME", "location_code": null, "category_code": "STAFF"},
     {"subject": "dev-acme-hr-admin", "company_code": "ACME", "roles": ["hr_admin"]},
     {"subject": "dev-acme-hr-reviewer", "company_code": "ACME", "roles": ["hr_admin"]}
   ]
   ```

2. A start script that sets these and runs the backend:
   - `MYPAL_DATABASE_URL`: the other database;
   - `MYPAL_QDRANT_COLLECTION`: the other collection;
   - `MYPAL_DEV_USERS_FILE`: the users file;
   - `MYPAL_DATA_NOTICE`: what the banner should say.

   Environment variables override `backend/.env`. After loading or changing that data set, run `mypal-policy reindex --recreate` with the same variables.

An invalid users file stops the backend at startup with the reason. The data set's own HR contacts must be loaded too, or referrals fall back to "contact your designated HR contact".

In the Docker profile, run any backend command with `docker compose exec backend <command>`, for example `docker compose exec backend mypal-policy reindex`.

## 6. Testing and evaluation

From `backend/`. Postgres and Qdrant must be running; database tests are skipped, not passed, if they are not.

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

From `frontend/`:

```bash
npm test
npm run typecheck
npm run lint
npm run build
```

Evaluations: these need Ollama, and the demo policies loaded. Run them from `backend/`:

```bash
uv run mypal-eval-retrieval --rerank-model Xenova/ms-marco-MiniLM-L-6-v2
uv run mypal-eval-answers
```

Results and how to read them: [backend/eval/README.md](../backend/eval/README.md) and [security-and-evaluation.md](security-and-evaluation.md).

## 7. Backup and restore

**Postgres is the only source of truth.** It holds policies, versions, chunks, audit events, feedback and metrics. The Qdrant index can be rebuilt from it at any time.

Back up (from the repository root). The dump is written inside the container and then copied out, because shell redirection (`>`) can corrupt binary output in Windows PowerShell:

```bash
docker compose exec postgres pg_dump -U mypal -d mypal --format=custom --file=/tmp/mypal.dump
```

```bash
docker compose cp postgres:/tmp/mypal.dump ./mypal-backup.dump
```

Restore. This **replaces** every table in the `mypal` database, so check you are on the right machine first:

```bash
docker compose cp ./mypal-backup.dump postgres:/tmp/mypal.dump
```

```bash
docker compose exec postgres pg_restore -U mypal -d mypal --clean --if-exists /tmp/mypal.dump
```

Then rebuild the search index from the restored data:

```bash
docker compose exec backend mypal-policy reindex --recreate
```

Backups contain policy text and audit records. Store them as carefully as the database itself, and never in the repository.

## 8. Updating the application

1. Back up the database (section 7).
2. Get the new code (`git pull`).
3. Rebuild and restart:
   - **Docker profile:** `docker compose --profile app up -d --build`. Migrations run before the new backend starts.
   - **Development mode:** `uv sync`, `uv run alembic upgrade head`, then restart uvicorn; `npm ci` for the frontend.
4. Check:
   - <http://127.0.0.1:8080/api/health/ready> returns `ready`;
   - one question answers with a citation;
   - `docker compose logs backend` shows no errors.

## 9. Rollback

| What went wrong | What to do |
|---|---|
| A **policy version** is wrong | Restore the previous version in the HR admin portal (or `mypal-policy restore <version-id> --actor <id> --reason "..."`). It is active again at once; the reason goes into the audit trail. No code or database change is needed. |
| The **search index** is damaged or out of step | `mypal-policy reindex --recreate`. It rebuilds from Postgres; only active versions are indexed. |
| A **code update** misbehaves, no migration involved | `git checkout <previous commit or tag>`, then rebuild (section 8). |
| A **code update with a migration** misbehaves | Stop the backend. Run `uv run alembic downgrade <previous revision>` with the *new* code still checked out (the downgrade script lives there), *or* restore the backup taken before the update. Then check out the previous code and rebuild. Restoring the backup is the safer choice when the migration changed or removed data. |
| The **database is lost** | Restore the latest backup (section 7), then `reindex --recreate`. Changes made after that backup are lost. |

## 10. Logs and monitoring

- **Logs:**
  - `docker compose logs -f backend` (JSON, one object per line, each carrying the request id from the `X-Request-ID` response header);
  - `docker compose logs frontend` (nginx access log).
- **Health:**
  - `/api/health`: the process is up;
  - `/api/health/ready`: the database answers. Docker uses this to decide when the backend is ready.
- **Usage and quality:** every question writes one `query_metrics` row (outcome, timings, tokens, top score, cited versions), and feedback goes to `feedback`. Neither stores question text, answer text or user identity.

There is no dashboard or alerting; this is listed in the hardening plan.

## 11. Stopping and removing

| Command | Effect |
|---|---|
| `docker compose --profile app stop` | Stops everything; all data kept |
| `docker compose --profile app down` | Removes the containers; data kept in the volumes |
| `docker compose --profile app down -v` | **Deletes all data**: database, index and downloaded models. Back up first. |

A laptop restart stops Docker Desktop and Ollama. Start them again before running the prototype or the evaluations.

## 12. Verification

On 2026-11-03, a fresh copy of the repository's committable files was set up with only the steps in this document. It ran as a separate Compose project on different ports, so the existing development data was not touched. The results:

| Step | Result |
|---|---|
| `docker compose --profile app up -d --build` | Images built. Migrations ran on an empty database; the backend became healthy; the frontend served the app and forwarded `/api` |
| `load-demo` (inside the backend container) | 4 versions published, leave v1 restored, v2 superseded |
| A question through nginx as `dev-employee-north` | Answered from leave v1 §3.3 ("18 days", not v2's 20), with a citation |
| `uv sync --locked`, then `uv run pytest` | 244 passed; ruff clean; `uv.lock` unchanged |
| `uv run mypal-eval-answers` against the fresh stack | 41 questions: 38 pass, 3 partial, 0 fail, **0 unsafe**; right outcome 41/41, right source 30/30. The same as the phase 8 run, so `load-demo` reproduces the expected data. |
| Backup and restore (section 7), then `reindex --recreate` | Restored; 3 active versions re-indexed; the same question answered again |

For this check, `UV_NO_CONFIG=1` was set: an unrelated `pyproject.toml` in a parent folder of the temporary copy would otherwise have changed uv's settings. A normal clone does not need it.
