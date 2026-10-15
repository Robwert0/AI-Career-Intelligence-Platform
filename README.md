# AI Career Intelligence Platform

An interactive, RAG-based "AI version of my CV": a portfolio site where visitors can read my CV and
projects, then ask a chat assistant questions answered from the CV itself. Visitors can also match
their own CV or GitHub profile against a job posting. A multi-agent layer (recruiter, career coach, interviewer) is the next phase.

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
- Generation through a provider-agnostic boundary, chosen by `GENERATION_PROVIDER`: `openai` in
  production (`gpt-6-luna` with `reasoning_effort=none`), `ollama` (a local
  [Ollama](https://ollama.com) `qwen3:8b`) for development only. The same provider runs chat and
  the Job Match Analyzer
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
- Redis token-bucket rate limiting, fail-closed, with every policy in `backend/app/core/policies.py`:
  per IP (IPv6 keyed per /64, plus a looser /48 bucket on login and register), per user (e.g. chat:
  20 req/min and 200/day) and per-user daily caps on the Job Match Analyzer (30 job intakes,
  8 analyses)
- Login: failed attempts are also limited per account, keyed on the resolved account rather than
  the typed email; a known-device cookie gives the account owner's browser its own bucket, so
  someone else guessing cannot lock them out
- Registration ceilings across all IPs: 20 created accounts per hour (a failed registration is
  refunded) and 200 attempts per hour
- LLM spend guard (denial-of-wallet): every model call reserves its worst-case cost against a
  global daily budget in Redis, in two pools (`LLM_DAILY_BUDGET_CHAT_USD`,
  `LLM_DAILY_BUDGET_ANALYSIS_USD`) priced by `LLM_INPUT_USD_PER_MTOK` / `LLM_OUTPUT_USD_PER_MTOK`;
  an exhausted pool refuses until 00:00 UTC, and draining the analysis pool leaves chat answering
- Structured backend logging (chat logs tokens and latency per answer) with noisy third-party
  loggers kept quiet
- Background jobs run on a Celery worker; job records live in Redis with a 1-hour TTL and Redis
  persistence is off, so job data is never written to disk
- A full Docker Compose stack behind Caddy (automatic HTTPS, real client IP), with a production
  override for a single host; see [Run the full stack in Docker](#run-the-full-stack-in-docker)
- CI on every PR: ruff, mypy, pytest against real Postgres + pgvector, model/migration parity
  check, a live Celery worker smoke test, a check that CI's service images match the compose
  digests, and frontend lint, format, tests and build
- Backend dependencies are installed from `uv.lock`, so CI tests exactly what runs locally

**Admin, analytics and data retention**
- Registration optionally asks for company and role; login and token refresh record last activity
- An admin-only `/admin` page lists registered users (paginated, `Cache-Control: no-store`)
- Admins are created with `scripts/make_admin.py --create`, which refuses existing emails and
  requires a 16+ character password; granting admin to an existing account also needs its password,
  and `--revoke` removes it
- Optional [Umami](https://umami.is) analytics: the tracker is vendored and served from our own
  origin (a test pins its sha256), and the CSP only opens `connect-src` to the collector when a
  website id is configured
- A daily Celery beat task deletes non-admin accounts inactive for `ACCOUNT_RETENTION_DAYS`
  (default 365); `scripts/delete_account.py` handles individual erasure requests
- `scripts/unlock_login.py <email>` lifts one account's sign-in lockout (its account-wide failure
  bucket only) when its owner is locked out by someone else's guessing (see
  [Operations scripts](#operations-scripts))

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
| 9 | Multi-agent system: router, recruiter, career coach, interviewer | ⏳ Not built |
| 10 | Security hardening | 🟡 Mostly done: rate limiting (IPv6-aware, per-account login limits, registration ceilings), LLM spend guard, prompt-injection defense and file-upload validation for chat and the Job Match Analyzer. Open: `/docs` and `/openapi.json` are enabled in every environment (not reachable through the production proxy) |
| 11 | Observability | 🟡 Partial: structured logging, per-answer chat token/latency logs, daily spend tracking per pool, admin visitor insights and optional Umami analytics; no error tracking yet |
| 12 | Deployment | 🟡 Ready for one host: production compose override with Caddy (HTTPS), digest-pinned images, read-only containers and memory caps |

RAG was deliberately built before the frontend, so the chat had a real backend to talk to.

What's next:
- Phase 9, the multi-agent system.
- Error tracking (Phase 11).
- A heartbeat lease on running jobs before scaling past **one worker per queue**: today a job
  found already `running` is treated as a crashed worker's and failed, which is only safe while
  a single worker consumes each queue.
- Passing the Job Match Analyzer's eval gate (`scripts/eval_match.py run`) against hand-labelled
  postings.

## Architecture

```
Browser ──► Caddy (HTTPS) ──► Next.js (/api/* proxied) ──► FastAPI
                                                             ├─ routes        thin: validation, auth, delegation
                                                             ├─ services      business logic
                                                             ├─ ai            chunking, embeddings, retrieval, prompts,
                                                             │                guards, generation (Ollama | OpenAI)
                                                             ├─ integrations  CV parsing (sandboxed), job URL fetch, GitHub
                                                             ├─ repositories  the only place DB queries live
                                                             └─ models        SQLAlchemy
                                    Celery worker (job intake, analysis) · Celery beat (daily retention purge)
                                    PostgreSQL + pgvector   Redis (rate limits, spend ledger, job/analysis
                                                                   state, CV blobs, GitHub cache, Celery broker)
```

The frontend proxies `/api/*` to the backend, so the browser only ever talks to one origin. That is
what lets the refresh cookie be `SameSite=Strict`.

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | Next.js (App Router), TypeScript (strict), TailwindCSS, Vitest |
| Backend | FastAPI, Python 3.14, Pydantic v2, SQLAlchemy 2.0 (async), Alembic |
| AI | sentence-transformers (`bge-small-en-v1.5`, local embeddings); generation via OpenAI (`gpt-6-luna`) in production, Ollama in development |
| Data | PostgreSQL 18 + pgvector |
| Cache / limits / queue | Redis, Celery (worker + beat) |
| Edge | Caddy (TLS, HSTS) |
| Tooling | uv, ruff, mypy, ESLint, Prettier, Docker Compose, GitHub Actions, Dependabot |

## Running locally

This walks you from a fresh clone to the site running on `http://localhost:3000`, with a CV you can
chat with. Everything runs on your machine: generation uses a local Ollama model, so you need no API
key. Plan for about 15 minutes, plus model downloads. (To try the production model locally instead,
set `GENERATION_PROVIDER=openai` and `OPENAI_API_KEY` in `.env`; that bills OpenAI.)

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

Leave `CV_DOCUMENT_ID` empty for now: migrations, ingestion and the Celery worker do not need it
(only the API refuses to start without it), and step 5 tells you what to put there.

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
uv run celery -A app.workers.beat_app:beat_app beat --loglevel=info  # optional locally: daily retention purge
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
| Chat returns 503 | Ollama is not running, or the first cold model load exceeded `CHAT_TIMEOUT_SECONDS` (retry), or all generation slots are busy, or the day's chat spend budget (`LLM_DAILY_BUDGET_CHAT_USD`) is used up (refused until 00:00 UTC) |
| Chat returns 500 | the model is not pulled: `ollama pull qwen3:8b` (Ollama answers 404, which the API treats as a rejected request) |
| Chat refuses every question | the chat is scoped to `CV_DOCUMENT_ID`; check it matches the id `ingest_cv.py` printed, then restart uvicorn |
| A match analysis never leaves the queue | the Celery worker is not running |
| Register / login fail with 403 | you opened `127.0.0.1:3000` instead of `localhost:3000`; the origin check blocks every POST from an unlisted origin |

### Configuration worth knowing

Generation and cost (see `.env.example` for the rest, each with its reasoning):
- `GENERATION_PROVIDER=ollama` (default, uses `OLLAMA_BASE_URL` and `GENERATION_MODEL`) or
  `openai` (needs `OPENAI_API_KEY`; `OPENAI_CHAT_MODEL=gpt-6-luna` with
  `OPENAI_REASONING_EFFORT=none`, without which it rejects `temperature=0`). `gpt-4o` and
  `gpt-4.1-mini` are deprecated and shut down on 2027-01-14; any replacement must accept
  temperature, seed and strict `json_schema`.
- `LLM_SPEND_GUARD_ENABLED=true`, `LLM_DAILY_BUDGET_CHAT_USD=0.75`,
  `LLM_DAILY_BUDGET_ANALYSIS_USD=1.25` and `LLM_INPUT_USD_PER_MTOK` / `LLM_OUTPUT_USD_PER_MTOK`
  (defaults `0.10` / `0.50`, `gpt-6-luna`'s prices). With `openai` and the guard on, startup
  refuses a zero price.

Job Match Analyzer settings:
- `MATCH_PRESELECT_MIN_SIMILARITY=0.605` (CV) and `MATCH_PRESELECT_MIN_SIMILARITY_GITHUB=0.583` —
  the refusal gate is per source and both have committed defaults. The statistic is each source's
  mean, over the posting's requirements, of that requirement's best evidence match ("relatedness").
  The defaults were measured on one CV and one GitHub profile; re-measure against your own with
  `uv run python scripts/eval_match.py calibrate --cv <your-cv.pdf>`. An old
  `MATCH_PRESELECT_MIN_SIMILARITY=0.681` line in `.env` overrides the CV gate: remove it.
- `MAX_UPLOAD_MB=5` — the CV upload size limit (1-20). The frontend reads the effective limit from
  `GET /match/config` (falling back to 5 MB), so there is nothing to keep in sync.
- `GITHUB_TOKEN` — optional. Without it, every user of this deployment shares GitHub's
  unauthenticated ~60 requests/hour (about 2 new profiles).

Two Celery queues exist: `intake` (job extraction) and `analysis` (the long CV/GitHub analysis). The
plain worker command above consumes both (plus the default `celery` queue the retention purge uses).
To keep job intake responsive behind a long analysis, run two workers instead, but never more than
one per queue until running jobs get a heartbeat lease (see [What's next](#roadmap)):

```bash
uv run celery -A app.workers.celery_app worker -Q intake,celery -n intake@%h
uv run celery -A app.workers.celery_app worker -Q analysis -n analysis@%h
```

### Checks

```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -q
cd frontend && npm run lint && npm run format:check && npm run test && npm run build
```

Backend tests are pytest (they need the Postgres and Redis containers running); frontend tests are
Vitest.

### Operations scripts

All run from `backend/` (`uv run python scripts/<name>`) and read the same `.env`. In the Docker
stack, run them as one-offs: `docker compose run --rm api python scripts/<name> …`.

| Script | What it does |
|---|---|
| `ingest_cv.py <pdf>` | parse, chunk, redact, embed and store a CV; prints the document id for `CV_DOCUMENT_ID` |
| `make_admin.py --create <email>` | create a new admin (prompts for a 16+ char password); `make_admin.py <email>` grants admin to an existing account (needs its password), `--revoke` removes it |
| `delete_account.py <email>` | erasure request: delete one account (asks for the email again); admins need `--allow-admin` |
| `unlock_login.py <email>` | clear one account's sign-in failure bucket; needs the production `SECRET_KEY`, since the bucket is keyed by an HMAC of the account id |
| `eval_chat_followups.py` | manual AI test of follow-up questions against the real CV and model |
| `eval_match.py prepare \| calibrate \| run` | calibrate the Job Match Analyzer's similarity gates and run its eval gate; needs postings under `docs/eval/postings/` (never committed) and `--cv <pdf>` after `calibrate`/`run` for your own CV |
| `calibrate_threshold.py` | measure `RETRIEVAL_SIMILARITY_THRESHOLD` against the ingested CV (needs `CV_DOCUMENT_ID`; edit its question lists to match your CV first) |
| `worker_smoke.py` | check a live Celery worker completes a job (CI runs it) |

The two eval scripts use Ollama by default. `--provider openai` (optionally `--model <name>`) bills
OpenAI outside the daily spend pools, and prints the run's token usage. For `eval_match.py` the
flags go before the subcommand: `uv run python scripts/eval_match.py --provider openai run`.

## Run the full stack in Docker

The same `.env` drives a fully containerized stack: Postgres, Redis, a one-shot `migrate`, the API,
one Celery worker, exactly one Celery beat (never scale it: the daily retention purge runs from it;
it runs the slim `app.workers.beat_app:beat_app`, which never loads torch), the frontend and Caddy
in front of it. Do step 2 above first; you need Docker and Ollama, not uv or Node.

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
- The containers we build (migrate, API, worker, beat, frontend) and Caddy run with a read-only
  root filesystem. What they may write is listed in `docker-compose.yml`: a `/tmp` tmpfs for the
  backend, a tmpfs for Next's `.next/cache`, the beat schedule volume and Caddy's data/config
  volumes. A new feature that writes elsewhere fails with "Read-only file system": give it a tmpfs
  or a volume rather than dropping `read_only`.
- Base images are pinned by digest (tag kept alongside for reading); Dependabot opens weekly PRs
  that move the digests forward (`.github/dependabot.yml`).
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

Production needs OpenAI for generation (the server runs no Ollama), the LLM spend guard switched
on with real prices, and `CV_DOCUMENT_ID` filled in after the first ingest; the checklist below
covers all three. Settings drops unknown keys, so a misspelled setting is silently ignored: check
each name against `.env.example`.

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
   - Generation through OpenAI: `GENERATION_PROVIDER=openai` with a project-scoped
     `OPENAI_API_KEY`; keep `OPENAI_CHAT_MODEL=gpt-6-luna` and `OPENAI_REASONING_EFFORT=none` (the
     defaults). The server does not run Ollama: it has no authentication, and a 4 GB
     VPS cannot hold the model anyway.
   - `LLM_DAILY_BUDGET_CHAT_USD` and `LLM_DAILY_BUDGET_ANALYSIS_USD` at what you can afford to lose
     each day (the defaults, `0.75` and `1.25`, total $2/day; e.g. `0.2` and `0.3` for $0.50/day),
     and on the OpenAI side prepaid credits with
     auto-recharge off, so a bug or an abuser can spend at most what is on the account.
   - `LLM_INPUT_USD_PER_MTOK` / `LLM_OUTPUT_USD_PER_MTOK` equal to the current list price of
     `OPENAI_CHAT_MODEL` per million tokens (the defaults, `0.10` / `0.50`, match `gpt-6-luna`), and
     `LLM_SPEND_GUARD_ENABLED=true` (the default). The daily caps are counted at these prices, so a
     stale price after a model change lets real spend run past the cap.
   - `CV_DOCUMENT_ID` empty for now; step 4 fills it in.
4. Start it in this order. The API refuses to start without `CV_DOCUMENT_ID`, and the frontend and
   Caddy only start once the API is healthy, so the CV goes in before the rest comes up. The PDF
   is piped in on stdin, as in the notes above (never bake one into the image).

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

The override also fixes HSTS at one year, whatever `.env` says, caps Redis at 256 MB, refuses to
start without `DOMAIN`, and gives every long-running container a memory cap sized for a 4 GB host,
with no swap, so a runaway container is OOM-killed and restarted rather than dragging the host
down (the reasoning and the measurements are in `docker-compose.prod.yml`; revisit them before adding a
second worker or raising worker concurrency). There is no ACME email, which Let's Encrypt does not
require.

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
