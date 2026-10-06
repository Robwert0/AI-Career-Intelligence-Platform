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
- Follow-up questions: the client sends up to three completed exchanges (6 messages, 2,000 chars
  each, 6,000 total; user/assistant roles only). The model rewrites the follow-up into a
  standalone question, which is what retrieval and the refusal gate see; the history reaches the
  answer prompt only as escaped data, never as an assistant turn, and is not stored anywhere.
  `scripts/eval_chat_followups.py` measures it against the real CV and model

**Job Match Analyzer**
- A public sample report at `/match/sample` (fictional candidate and job, no account, no AI call)
  shows the real report before sign-up; `backend/tests/test_sample_report.py` proves its score,
  breakdown and coverage are exactly what the scoring code computes from its statuses
- A reload resumes a running analysis or reopens its report: the tab keeps only the analysis id
  (session storage, cleared on sign-out or when another account signs in), and the page shows the
  record's real remaining lifetime from `expires_in_seconds`; recovery never extends the TTL
- Add a job posting (a URL our server fetches, or pasted text) and a CV (PDF/DOCX upload, or
  pasted text) and/or a public GitHub profile; review and edit the extracted requirements before
  analysing
- Async pipeline on Celery: read the job → read the CV / GitHub evidence → match evidence to
  requirements → assess each requirement → score → recommend, with live queue position and stage
  progress in the UI
- A transparent, code-computed score (the model never picks the number): a weighted breakdown by
  category, per-requirement status with cited evidence, immediate/longer-term recommendations, and
  grounded CV rewrite suggestions
- The model can refuse to score (no relevant evidence) rather than guess, and personal
  characteristics / work-authorization requirements are always excluded from scoring, re-checked
  server-side regardless of client input
- Recoverable failures at every stage (bad job URL, unreadable CV, GitHub rate limits, one active
  job/analysis per user) each resolve to a specific recovery action in the UI, not a dead end
- State (job/analysis records, CV blobs, the GitHub cache) lives in Redis with a short TTL, never
  written to disk; dedicated per-user/IP rate limits for job intake and analysis submission

**Security and operations**
- Redis token-bucket rate limiting per IP and per user (e.g. chat: 20 req/min per user), fail-closed
- Structured backend logging with noisy third-party loggers kept quiet
- Background jobs run on a Celery worker; job records live in Redis with a 1-hour TTL and Redis
  persistence is off, so job data is never written to disk
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
| 5 | CV upload endpoint | 🟡 Partial: CV upload (PDF/DOCX, magic-byte + macro validation) ships as part of the Job Match Analyzer, backed by Redis with a TTL, not S3 |
| 6 | Async jobs (Celery workers) | ✅ Done: job intake and analysis both run as Celery tasks with queue position, stage progress and stale-queue handling |
| 7 | AI analysis: CV feedback, ATS scoring | 🟡 Partial: grounded CV rewrite suggestions and gap analysis ship as part of the Job Match Analyzer; no separate standalone ATS-scoring endpoint |
| 8 | Job matching: CV vs job description | ✅ Done: the Job Match Analyzer (job intake, CV + GitHub evidence, hybrid retrieval, multi-stage LLM assessment, transparent scoring). The per-source similarity gates (CV 0.605, GitHub 0.583) are calibrated against one real CV and one GitHub profile; the eval quality gate (`scripts/eval_match.py`) has not yet passed against hand-labelled postings |
| 9 | Multi-agent system: router, recruiter, career coach, interviewer | ⏳ Planned |
| 10 | Security hardening | 🟡 Partial: rate limiting, prompt-injection defense and file-upload validation done for chat and the Job Match Analyzer; queue/worker-concurrency hardening (a global cap of 20 waiting analyses and separate intake/analysis queues exist; stale-queue edge cases remain) still open |
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
                                  PostgreSQL + pgvector   Redis (rate limits, job/analysis state,
                                                                  CV blobs, GitHub cache)
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
uv run celery -A app.workers.celery_app worker --loglevel=info   # background jobs (separate terminal); consumes every queue

cd ../frontend
npm ci
npm run dev
```

Job Match Analyzer env lines worth calling out (see `.env.example` for the rest):
- `MATCH_PRESELECT_MIN_SIMILARITY=0.605` (CV) and `MATCH_PRESELECT_MIN_SIMILARITY_GITHUB=0.583` —
  the refusal gate is per source and both have committed defaults. The statistic is each source's
  mean, over the posting's requirements, of that requirement's best evidence match ("relatedness").
  The defaults were measured on one CV and one GitHub profile; re-measure against your own with
  `uv run python scripts/eval_match.py calibrate`. **Existing setups: remove an old
  `MATCH_PRESELECT_MIN_SIMILARITY=0.681` line from `.env`** -- it overrides the new CV gate.
- `MAX_UPLOAD_MB=5` — the CV upload size limit (1-20). The frontend reads the effective limit from
  `GET /match/config` (falling back to 5 MB), so there is nothing to keep in sync.
- `GITHUB_TOKEN` — optional. Without it, every user of this deployment shares GitHub's
  unauthenticated ~60 requests/hour (about 2 new profiles).

Two Celery queues exist: `intake` (job extraction) and `analysis` (the long CV/GitHub analysis). The
plain worker command above consumes both. To keep job intake responsive behind a long analysis, run
two workers instead:

```bash
uv run celery -A app.workers.celery_app worker -Q intake,celery -n intake@%h
uv run celery -A app.workers.celery_app worker -Q analysis -n analysis@%h
```

### Checks

```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -q
cd frontend && npm run lint && npm run test && npm run build
```

The suite has 1377 backend tests (pytest) and 412 frontend tests (Vitest).
