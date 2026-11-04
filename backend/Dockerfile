# My Pal backend image. Built by docker-compose.yml (profile "app"); see docs/operations.md.
# Dependencies come only from uv.lock, so the image has exactly the versions the tests ran with.

FROM python:3.11.14-slim-bookworm

# uv itself, pinned to the version used in development.
COPY --from=ghcr.io/astral-sh/uv:0.10.7 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# 1. Dependencies only (no project code yet), so this slow layer is reused until uv.lock changes.
#    --locked fails the build if uv.lock does not match pyproject.toml; --no-dev leaves out
#    pytest, ruff and the other development tools.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

# 2. The application and its migrations.
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
RUN uv sync --locked --no-dev --no-editable

# Run as an unprivileged user. data/models holds the downloaded embedding and reranker models
# (a named volume in docker-compose.yml, so they are downloaded once, not on every start).
RUN useradd --system --uid 10001 --no-create-home mypal \
    && mkdir -p /app/data/models \
    && chown -R mypal /app/data
USER mypal
# The model downloader keeps its own cache and logs. The user has no home directory, so they go
# into the writable models volume too.
ENV HF_HOME=/app/data/models/huggingface \
    HF_HUB_DISABLE_TELEMETRY=1

EXPOSE 8000
CMD ["uvicorn", "mypal.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
