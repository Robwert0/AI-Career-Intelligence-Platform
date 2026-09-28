# AI Career Intelligence Platform

An interactive, RAG-based "AI version of my CV": a portfolio site where visitors can read my CV and
projects, then ask a chat assistant questions answered from the CV itself. The longer-term goal is
a CV analysis and job-matching engine built on a multi-agent system.

It is built as a production-grade system, not a demo: every feature has to be **secure, async,
scalable and explainable** before it counts as done.

## What works today

**Portfolio frontend (Next.js App Router, TypeScript, Tailwind)**
- Landing page with hero, selected work, experience, skills and contact sections
- A detail page for every project (statically generated), and a printable `/cv` page
- Dark/light theme toggle with no flash of the wrong theme on load
- Register / login UI and a chat interface, plus an always-present chat bubble on the landing page

**Authentication (FastAPI, async SQLAlchemy, PostgreSQL)**
- Register and login with bcrypt password hashing
- Short-lived JWT access tokens + refresh tokens in an `httpOnly`, `SameSite=Strict` cookie
- Refresh-token rotation with reuse detection (a replayed token revokes the whole token family)
- CORS allowlist and origin-based CSRF defense

**RAG chat over the CV**
- Ingestion: PDF parsing → section-aware chunking (experience / projects / skills) → phone-number
  redaction → local embeddings (`bge-small-en-v1.5`) → pgvector
- Hybrid retrieval: pgvector cosine similarity (HNSW index) + Postgres full-text search, with a
  similarity threshold calibrated against the real CV
- Generation through a provider-agnostic boundary; the current adapter is a local
  [Ollama](https://ollama.com) model (`qwen3:8b`)
- Prompt-injection defense: an input guard, strict isolation of system prompt / user input /
  retrieved documents, special-token escaping, and an output guard that blocks prompt leaks

**Security and operations**
- Redis token-bucket rate limiting per IP and per user (e.g. chat: 20 req/min per user), fail-closed
- Structured backend logging with noisy third-party loggers kept quiet
- CI on every PR: ruff, mypy, pytest against real Postgres + pgvector, model/migration parity
  check, and frontend lint, format, tests and build
- Backend dependencies are installed from `uv.lock`, so CI tests exactly what runs locally

## Roadmap

| Phase | Area | Status |
|---|---|---|
| 1 | Setup: monorepo, FastAPI, Next.js, Postgres + pgvector, Redis, CI | ✅ Done |
| 2 | Auth: JWT, refresh rotation, secure cookies | ✅ Done |
| 3 | Frontend: portfolio, auth UI, chat UI | ✅ Done |
| 4 | RAG: ingestion, embeddings, hybrid retrieval, chat endpoint | ✅ Done |
| 5 | CV upload endpoint (S3) | ⏳ Planned |
| 6 | Async jobs (Celery workers) | ⏳ Planned |
| 7 | AI analysis: CV feedback, ATS scoring | ⏳ Planned |
| 8 | Job matching: CV vs job description | ⏳ Planned |
| 9 | Multi-agent system: router, recruiter, career coach, interviewer | ⏳ Planned |
| 10 | Security hardening | 🟡 Partial: rate limiting and prompt-injection defense done; upload validation pending |
| 11 | Observability | 🟡 Partial: logging done; error tracking and token usage pending |
| 12 | Deployment | ⏳ Planned |

RAG was deliberately built before the frontend, so the chat had a real backend to talk to.

## Architecture

```
Browser ──► Next.js (/api/* proxied) ──► FastAPI
                                           ├─ routes        thin: validation, auth, delegation
                                           ├─ services      business logic
                                           ├─ ai            chunking, embeddings, retrieval, prompts, guards
                                           ├─ repositories  the only place DB queries live
                                           └─ models        SQLAlchemy
                                  PostgreSQL + pgvector   Redis (rate limits)
```

The frontend proxies `/api/*` to the backend, so the browser only ever talks to one origin. That is
what lets the refresh cookie be `SameSite=Strict`.

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | Next.js (App Router), TypeScript (strict), TailwindCSS, Vitest |
| Backend | FastAPI, Python 3.14, Pydantic v2, SQLAlchemy 2.0 (async), Alembic |
| AI | sentence-transformers (`bge-small-en-v1.5`), Ollama for generation |
| Data | PostgreSQL 18 + pgvector |
| Cache / limits | Redis |
| Tooling | uv, ruff, mypy, ESLint, Prettier, Docker Compose, GitHub Actions |

## Running locally

Prerequisites: Docker, [uv](https://docs.astral.sh/uv/), Node 24, and [Ollama](https://ollama.com)
with the `qwen3:8b` model pulled.

```bash
cp .env.example .env                  # then fill in SECRET_KEY etc.
cp frontend/.env.example frontend/.env.local

docker compose up -d database redis   # Postgres + Redis

cd backend
uv sync --extra dev
uv run alembic upgrade head
uv run python scripts/ingest_cv.py path/to/cv.pdf   # load a CV into the chunks table
uv run uvicorn app.main:app --reload

cd ../frontend
npm ci
npm run dev
```

### Checks

```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -q
cd frontend && npm run lint && npm run test && npm run build
```

The suite has 447 backend tests (pytest) and 95 frontend tests (Vitest).
