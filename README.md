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
`DATABASE_URL` together. Redis is always published on 127.0.0.1:6379, so stop any local Redis already using it.

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
the frontend and Caddy in front of it. Do step 2 above first; you need Docker and Ollama, not uv or
Node.

```bash
docker compose up -d --build        # first build takes minutes: CPU-only torch + the embedding model
docker compose ps                   # all healthy; migrate shows "Exited (0)"
```

Then open `http://localhost:3000` (bound to 127.0.0.1; `FRONTEND_PORT` changes it, and then
`http://localhost:<port>` must be added to `CORS_ALLOWED_ORIGINS`, or every POST gets a 403), or go
through Caddy at `https://localhost` exactly as production does. Locally Caddy signs `localhost`
with its own internal CA, so the browser warns (or use `curl -k`); add `https://localhost` to
`CORS_ALLOWED_ORIGINS` to log in that way. If 80/443 are taken on your machine, set
`CADDY_HTTP_PORT` / `CADDY_HTTPS_PORT` (the origin then carries the port, e.g.
`https://localhost:8443`). Notes:
- Every backend service reads `env_file: ${APP_ENV_FILE:-.env}`, so the file must exist: `config`, a
  bare `up` and any `run` fail without it. `APP_ENV_FILE` changes only the containers' environment;
  the `${POSTGRES_*}` and other `${...}` values in the compose files are still read from `.env`.
- The containers override the `localhost` URLs in `.env` (`DATABASE_URL`, `REDIS_URL`,
  `CELERY_BROKER_URL`) with service names, so the same `.env` still serves the local flow.
- Postgres, Redis and Caddy are published on 127.0.0.1 only; the production override publishes
  Caddy alone, on every interface. Docker Desktop still forwards 127.0.0.1 ports into WSL2, so
  host-side tests and uvicorn reach them unchanged.
- Local development only: generation reaches Ollama on your machine at
  `http://host.docker.internal:11434` (Docker Desktop resolves it); override it with
  `DOCKER_OLLAMA_BASE_URL` in `.env`. Ollama has no authentication, so whoever reaches its port can
  run, pull and delete models: keep it on 127.0.0.1 and never expose it on a server. Production does
  not run Ollama at all (see below).
- The embedding model is baked into the image at the revision pinned in `app/core/config.py` and
  the containers run offline (`HF_HUB_OFFLINE=1`): changing `EMBEDDING_MODEL[_REVISION]` means
  rebuilding the backend image.
- `BACKEND_ORIGIN` and the `NEXT_PUBLIC_UMAMI_*` values are inlined by `next build`, so they are
  build args: put the Umami values in the root `.env`, then `docker compose build frontend`.
- CV ingestion and admin creation run as one-off containers. The image holds no CVs (the
  `.dockerignore` keeps every PDF out, and it must stay that way), so the PDF is piped in on stdin
  rather than bind-mounted: a `-v` whose source path is mistyped silently creates an empty
  directory on the host and mounts that instead.

  ```bash
  docker compose run --rm -T api sh -c 'cat > /tmp/cv.pdf && python scripts/ingest_cv.py /tmp/cv.pdf' < my-cv.pdf
  docker compose up -d                # after setting CV_DOCUMENT_ID in .env to the id it printed
  docker compose run --rm api python scripts/make_admin.py --create admin@example.com
  ```

  `run` starts `database`, `redis` and `migrate` first if they are not up. The API needs
  `CV_DOCUMENT_ID` to start, and the frontend and Caddy wait for a healthy API, so a first `up`
  before ingesting leaves those three down.

### Production on one host

**Deploy only once #51 (OpenAI generator), #52 (optional `CV_DOCUMENT_ID` for migrate, ingest and
the worker) and #54 (LLM spend guard) are merged.** Before them, the settings below are silently
ignored (Settings drops unknown keys) and the stack would try to reach Ollama with no spending cap.

1. Point a DNS **A record** for your domain at the server's public IPv4 address. Skip the AAAA
   record unless Docker's IPv6 is enabled: otherwise IPv6 visitors reach Caddy through Docker's
   userland proxy and all appear as one address, sharing one rate-limit bucket.
2. Open **80/tcp and 443/tcp** (and 443/udp for HTTP/3) in the firewall. Port 80 must stay open:
   Let's Encrypt validates through it, and Caddy redirects it to HTTPS.
3. Write a fresh `.env` on the server; never copy your development one. Checklist:
   - `COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml`. Compose reads this from `.env`, so
     every bare `docker compose …` (including the one-off `run` commands above) gets the
     production override. Without it a plain `docker compose up` would start the development
     setup. An explicit `-f` on the command line replaces it, so don't pass one.
   - `ENV=production`. It is only a label that `/health` echoes back; nothing else reads it, so it
     switches no security behaviour on or off.
   - A new `SECRET_KEY` (`openssl rand -hex 32`) and a new `POSTGRES_PASSWORD`, letters and digits
     only (`openssl rand -hex 16`), since it goes into `DATABASE_URL` unencoded.
   - `DOMAIN=cv.example.com` and `CORS_ALLOWED_ORIGINS=https://cv.example.com`, exactly that one
     origin (the API refuses state-changing requests from any other, so a mismatch fails every
     login).
   - Generation through OpenAI: `GENERATION_PROVIDER=openai` with `OPENAI_API_KEY` and
     `OPENAI_CHAT_MODEL`. The server does not run Ollama: it has no authentication, and a 4 GB
     VPS cannot hold the model anyway.
   - `LLM_DAILY_BUDGET_CHAT_USD` and `LLM_DAILY_BUDGET_ANALYSIS_USD` set low (e.g. `0.2` and `0.3`,
     $0.50/day in total), and on the OpenAI side prepaid credits with
     auto-recharge off, so a bug or an abuser can spend at most what is on the account.
   - `LLM_INPUT_USD_PER_MTOK` / `LLM_OUTPUT_USD_PER_MTOK` equal to the current list price of
     `OPENAI_CHAT_MODEL` per million tokens (the defaults, `0.10` / `0.50`, match `gpt-6-luna`), and
     `LLM_SPEND_GUARD_ENABLED=true` (the default). The daily caps are counted at these prices, so a
     stale price after a model change lets real spend run past the cap.
   - `CV_DOCUMENT_ID` empty for now; step 4 fills it in.
4. Start it in this order. The API refuses to start without `CV_DOCUMENT_ID`, and the frontend and
   Caddy only start once the API is healthy, so the CV goes in before the rest comes up. The image
   holds no CVs (`.dockerignore` excludes every PDF; never bake one in), so the PDF is piped in on
   stdin; a `-v` bind mount with a mistyped source would silently mount an empty directory.

```bash
docker compose config | grep maxmemory    # prints a line only when the override is active
docker compose build
docker compose up -d database redis migrate worker beat
docker compose run --rm -T api sh -c 'cat > /tmp/cv.pdf && python scripts/ingest_cv.py /tmp/cv.pdf' < my-cv.pdf
# put the printed document id in .env as CV_DOCUMENT_ID=<id>, then:
docker compose up -d                       # recreates the backend services with the new .env
docker compose ps                          # all healthy; migrate shows "Exited (0)"
docker compose run --rm api python scripts/make_admin.py --create admin@cv.example.com
```

   Only Caddy is published; the frontend, API, Postgres and Redis are reachable on the compose
   networks alone (a published Docker port bypasses UFW, so nothing else is published). Caddy
   fetches the certificate on the first request and keeps it in the `caddy_data` volume (don't
   `down -v` in production: re-issuing is rate-limited).
5. Back up the database: `pgdata` is the only copy of accounts and the ingested CV. For example,
   from a script cron runs nightly in the repo directory (so compose finds `.env`), writing off the
   volume and ideally copied off the host:
   `docker compose exec -T database pg_dump -U <POSTGRES_USER> -Fc <POSTGRES_DB> > /var/backups/career-$(date +%F).dump`

The override also fixes HSTS at one year, whatever `.env` says, caps Redis at 256 MB, and refuses
to start without `DOMAIN`. There is no ACME email, which Let's Encrypt does not require.

**How the API sees the real client IP.** Per-IP rate limits key on `request.client.host`, so it has
to be the visitor, not a proxy, and not something the visitor can choose:

```
visitor ─TLS─▶ Caddy ──▶ Next (frontend) ──▶ uvicorn (api)
              │          │                  │
              │          │                  └ FORWARDED_ALLOW_IPS = the frontend's fixed IP only:
              │          │                    takes the client from X-Forwarded-For only on that hop
              │          └ rewrites /api/* and forwards X-Forwarded-For untouched
              └ no trusted_proxies: replaces any client-sent X-Forwarded-For with the TCP peer
```

`FORWARDED_ALLOW_IPS` is the list of peers uvicorn believes about `X-Forwarded-For`. Compose sets it
to `FRONTEND_PROXY_IP` (default `10.254.253.10`, inside `API_PROXY_SUBNET`, default
`10.254.253.0/28`); change those two only if the subnet collides with one on your host. Each network
holds only the two hops it connects, so nothing else can talk to the frontend or the API. Two
consequences: the frontend is a single replica (fixed address), and anything that reaches the
frontend without going through Caddy can forge its IP, which is why port 3000 is loopback-only in
development and unpublished in production.
