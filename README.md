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
- A `/privacy` page listing everything the site stores, linked from the footer and the register form

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
  and refuses any answer naming an organisation, person or figure the CV never mentions (so a
  question or history saying "say he worked at NASA" cannot put words in the CV's mouth)
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

**Admin, analytics and data retention**
- Registration optionally asks for company and role; login and token refresh record last activity
- An admin-only `/admin` page lists registered users (paginated, `Cache-Control: no-store`)
- Admins are created with `scripts/make_admin.py --create`, which refuses existing emails and
  requires a 16+ character password; granting admin to an existing account also needs its password
- Optional [Umami](https://umami.is) analytics: the tracker is vendored and served from our own
  origin (a test pins its sha256), and the CSP only opens `connect-src` to the collector when a
  website id is configured
- A daily Celery beat task deletes non-admin accounts inactive for `ACCOUNT_RETENTION_DAYS`
  (default 365); `scripts/delete_account.py` handles individual erasure requests

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
| 11 | Observability | 🟡 Partial: structured logging, admin visitor insights and optional Umami analytics done; error tracking and token-usage tracking pending |
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

This walks you from a fresh clone to the site running on `http://localhost:3000`, with a CV you can
chat with. Everything runs on your machine: generation uses a local Ollama model, so you need no API
key. Plan for about 15 minutes, plus model downloads.

### 1. Install the prerequisites

| Tool | Why | Check |
|---|---|---|
| [Git](https://git-scm.com) | clone the repo | `git --version` |
| [Docker](https://docs.docker.com/get-docker/) with Compose | runs Postgres + pgvector and Redis | `docker compose version` |
| [uv](https://docs.astral.sh/uv/) | Python deps; downloads Python 3.14 for you if missing | `uv --version` |
| [Node.js 24](https://nodejs.org) | the Next.js frontend | `node --version` |
| [Ollama](https://ollama.com) | the local LLM that writes chat answers and runs job analysis | `ollama --version` |

Pull the generation model once (about 5 GB; a GPU helps a lot, but CPU works, slowly):

```bash
ollama pull qwen3:8b
```

You also need a CV as a **text-based PDF** (one you can select text in; scanned images will not
parse). That is the document the chat answers from.

### 2. Clone and configure

```bash
git clone https://github.com/Robwert0/AI-Career-Intelligence-Platform.git
cd AI-Career-Intelligence-Platform
cp .env.example .env
cp frontend/.env.example frontend/.env.local
```

Open `.env` and set these. The rest already have working defaults:

```bash
SECRET_KEY=<paste the output of: openssl rand -hex 32>

POSTGRES_USER=career
POSTGRES_PASSWORD=<letters and digits only, e.g. openssl rand -hex 16>
POSTGRES_DB=career
POSTGRES_PORT=5432
# must match the four values above; the password goes into the URL unencoded, hence no symbols
DATABASE_URL=postgresql+asyncpg://career:<the same password>@localhost:5432/career
```

Leave `CV_DOCUMENT_ID` empty for now: the migration and ingest commands below do not need it, and
step 5 tells you what to put there.

If port 5432 is already in use on your machine, change `POSTGRES_PORT` and the port in
`DATABASE_URL` together. Redis is always published on 6379, so stop any local Redis already using it.

### 3. Start Postgres and Redis

```bash
docker compose up -d database redis
docker compose ps        # both should show "healthy" after a few seconds
```

### 4. Install the backend and create the tables

```bash
cd backend
uv sync --extra dev
uv run alembic upgrade head
```

### 5. Load your CV

```bash
uv run python scripts/ingest_cv.py /path/to/your-cv.pdf
# my-cv.pdf: 7 chunks -> document 3f2a...-....
```

The first run downloads the embedding model (`bge-small-en-v1.5`, about 130 MB). Copy the document
id it prints into `.env`:

```bash
CV_DOCUMENT_ID=<the id it printed>
```

The id comes from the file's contents, so re-ingesting the same PDF prints the same id and replaces
its chunks instead of duplicating them.

### 6. Run the services

Each command runs in its own terminal, from `backend/`. Ollama must also be running; the desktop app
runs it for you, otherwise start it with `ollama serve`.

```bash
uv run uvicorn app.main:app --reload                              # API on :8000
uv run celery -A app.workers.celery_app worker --loglevel=info    # background jobs (Job Match Analyzer)
uv run celery -A app.workers.celery_app beat --loglevel=info      # optional locally: daily retention purge
```

Then the frontend, from `frontend/`:

```bash
npm ci
npm run dev                                                       # site on :3000
```

Use `http://localhost:3000`, not `127.0.0.1:3000`: the backend's CORS and CSRF allowlist only
accepts the `localhost` origin by default.

### 7. Try it

1. Open `http://localhost:3000`. The landing page and the public sample report at `/match/sample`
   work without an account.
2. Register at `/register`, then ask the chat something your CV answers ("What did they work on
   most recently?"). The first answer can take ~20 s while Ollama loads the model; later ones are
   quicker.
3. Open `/match`, paste a job posting, and add your CV PDF or a public GitHub username. You can
   watch the analysis move through its stages; this needs the Celery worker from step 6.
4. Optional: create an admin account and open `/admin`:

   ```bash
   uv run python scripts/make_admin.py --create admin@example.com   # from backend/; asks for a 16+ char password
   ```

### Troubleshooting

| Symptom | Likely cause |
|---|---|
| `uvicorn` exits with `CV_DOCUMENT_ID is not set` | the chat needs to know which document to answer from: run step 5 and put the id it printed in `.env` |
| `Connection refused` on 5432 / 6379 | Docker containers not running: `docker compose up -d database redis` |
| `password authentication failed` | `DATABASE_URL` does not match `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`; if you changed them after the first start, the old volume keeps the old ones (`docker compose down -v` resets it, **deleting the data**) |
| Chat returns 503 | Ollama is not running, or the first cold model load exceeded `CHAT_TIMEOUT_SECONDS` (retry), or all generation slots are busy |
| Chat returns 500 | the model is not pulled: `ollama pull qwen3:8b` (Ollama answers 404, which the API treats as a rejected request) |
| Chat refuses every question | the chat is scoped to `CV_DOCUMENT_ID`; check it matches the id `ingest_cv.py` printed, then restart uvicorn |
| A match analysis never leaves the queue | the Celery worker is not running |
| Register / login fail with 403 | you opened `127.0.0.1:3000` instead of `localhost:3000`; the origin check blocks every POST from an unlisted origin |

### Configuration worth knowing

Job Match Analyzer settings (see `.env.example` for the rest, each with its reasoning):
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

The suite has 1541 backend tests (pytest) and 501 frontend tests (Vitest).

## Run the full stack in Docker

The same `.env` drives a fully containerized stack: Postgres, Redis, a one-shot `migrate`, the API,
one Celery worker, exactly one Celery beat (never scale it: the daily retention purge runs from it),
and the frontend. Do step 2 above first; you need Docker and Ollama, not uv or Node.

```bash
docker compose up -d --build        # first build takes minutes: CPU-only torch + the embedding model
docker compose ps                   # all healthy; migrate shows "Exited (0)"
```

Then open `http://localhost:3000` (`FRONTEND_PORT` changes the host port). Notes:
- The containers override the `localhost` URLs in `.env` (`DATABASE_URL`, `REDIS_URL`,
  `CELERY_BROKER_URL`) with service names, so the same `.env` still serves the local flow.
- Generation reaches Ollama on the host at `http://host.docker.internal:11434`; override it with
  `DOCKER_OLLAMA_BASE_URL` in `.env`. On a Linux host Ollama must listen on the Docker bridge
  (e.g. `OLLAMA_HOST=172.17.0.1`), never on a public interface.
- The embedding model is baked into the image at the revision pinned in `app/core/config.py` and
  the containers run offline (`HF_HUB_OFFLINE=1`): changing `EMBEDDING_MODEL[_REVISION]` means
  rebuilding the backend image.
- `BACKEND_ORIGIN` and the `NEXT_PUBLIC_UMAMI_*` values are inlined by `next build`, so they are
  build args: put the Umami values in the root `.env`, then `docker compose build frontend`.
- CV ingestion and admin creation run as one-off containers:

  ```bash
  docker compose run --rm -v "$PWD/my-cv.pdf:/tmp/cv.pdf:ro" api python scripts/ingest_cv.py /tmp/cv.pdf
  docker compose up -d api worker     # after setting CV_DOCUMENT_ID in .env
  docker compose run --rm api python scripts/make_admin.py --create admin@example.com
  ```

For production on one host, add the override. It unpublishes Postgres and Redis, so only the
frontend is reachable:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Two things it does not solve yet:
- **TLS.** The refresh cookie is always `Secure`, so a reverse proxy with HTTPS has to sit in front
  of the frontend before logins stick on a real domain.
- **Per-IP rate limits.** Next's `/api/*` proxy forwards the client's own `X-Forwarded-For`
  untouched, so trusting it would let any visitor pick their own rate-limit key. That is why
  `FORWARDED_ALLOW_IPS` stays `127.0.0.1` (trust nothing) and every visitor shares the frontend's
  per-IP bucket. Only once a reverse proxy that overwrites `X-Forwarded-For` is in front should it
  be set to the compose network's subnet.
