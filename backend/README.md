# My Pal backend

FastAPI service for the My Pal HR policy chatbot prototype. Python 3.11, managed with [uv](https://docs.astral.sh/uv/).

## Setup (from a clean checkout)

```bash
cd backend
uv sync                      # creates .venv with Python 3.11 and installs exactly what uv.lock lists
cp .env.example .env         # optional; every setting has a default
```

## Run

```bash
uv run uvicorn mypal.main:create_app --factory --reload
```

- Health check: <http://127.0.0.1:8000/api/health>
- API docs (not in production): <http://127.0.0.1:8000/api/docs>

## Test and lint

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Layout

| Path | Responsibility |
|---|---|
| `src/mypal/main.py` | App factory: settings, logging, middleware, error handlers, routers |
| `src/mypal/config.py` | Typed settings read from `MYPAL_*` environment variables / `.env` |
| `src/mypal/errors.py` | `AppError` and the single JSON error envelope |
| `src/mypal/api/` | HTTP routers (thin) and shared dependencies |
| `src/mypal/schemas/` | Pydantic request/response contracts |
| `src/mypal/observability/` | Request IDs and structured logging |
| `tests/` | pytest suite |

## Conventions

- **Errors** always look like `{"error": {"code", "message", "request_id", "details?"}}`. Raise `AppError` for expected failures; unexpected exceptions return a generic 500 and are logged with a traceback.
- **Request IDs**: every response has `X-Request-ID`, and every log line made while handling it carries the same ID. A well-formed incoming `X-Request-ID` is reused.
- **Settings** are only read in `config.py`; routes receive them through `SettingsDep`.
- **Logs** never include query strings, request bodies, or validation input values.
