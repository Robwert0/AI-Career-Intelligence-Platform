# syntax=docker/dockerfile:1
# One image, three roles chosen by command: API (default), Celery worker, Celery beat.
# Build from backend/:  docker build -t career-intel-backend backend

# Base images are pinned by digest (Dependabot bumps them); keep the two python lines identical.
FROM ghcr.io/astral-sh/uv:0.10.9@sha256:10902f58a1606787602f303954cea099626a4adb02acbac4c69920fe9d278f82 AS uv

FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app/backend

# Dependencies first, so a source-only change reuses this (torch-sized) layer.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-dev --no-install-project

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Fetch the embedding model and tokenizer exactly as the app loads them, at the revision pinned in
# app/core/config.py. Settings needs its required fields to import; these placeholders exist only
# for this RUN and are not part of the image's environment.
ENV HF_HOME=/opt/huggingface
RUN DATABASE_URL=postgresql+asyncpg://build:build@localhost/build \
    REDIS_URL=redis://localhost:6379/0 \
    SECRET_KEY=build-only-placeholder-not-a-secret-000 \
    CV_DOCUMENT_ID=00000000-0000-0000-0000-000000000000 \
    /app/.venv/bin/python -c "from app.ai.embeddings import BgeEmbedder; from app.ai.tokenizer import token_budget; BgeEmbedder(); token_budget()" \
 && DATABASE_URL=postgresql+asyncpg://build:build@localhost/build \
    REDIS_URL=redis://localhost:6379/0 \
    SECRET_KEY=build-only-placeholder-not-a-secret-000 \
    CV_DOCUMENT_ID=00000000-0000-0000-0000-000000000000 \
    HF_HUB_OFFLINE=1 \
    /app/.venv/bin/python -c "from app.ai.embeddings import BgeEmbedder; BgeEmbedder().embed_query('offline check')"


FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS runtime
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --create-home --home-dir /home/app app \
 && mkdir -p /var/lib/celerybeat \
 && chown app:app /var/lib/celerybeat

# Root-owned code and model: the app user can read and run them, never rewrite them.
COPY --from=builder /app /app
COPY --from=builder /opt/huggingface /opt/huggingface

# HF_HUB_OFFLINE: a revision override in .env that is not baked in fails at load, instead of
# pulling model code from the network at runtime.
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/opt/huggingface \
    HF_HUB_OFFLINE=1 \
    FORWARDED_ALLOW_IPS=127.0.0.1

WORKDIR /app/backend
USER app
EXPOSE 8000

# uvicorn reads FORWARDED_ALLOW_IPS from the environment; 127.0.0.1 trusts no proxy header.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
