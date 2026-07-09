# AI Career Intelligence Platform

> An interactive, RAG-based "AI version of my CV" + a CV analysis / job-matching engine
> built on a multi-agent AI system. **This is a production-grade system, not a demo.**

---

## 0. The One Rule (non-negotiable)

If it is not **Secure**, **Async**, **Scalable**, and **Explainable** → it is **not done**.

Every feature must be defensible in a hiring conversation. When in doubt, choose the
production-correct option over the quick one.

---

## 1. Working Mode (how Claude and Robert collaborate)

**Robert writes the application code. Claude acts as tech lead / architect / reviewer.**

For each task, Claude should:
1. **Direct, don't dump.** Explain *what* to build and *why*, point at the exact files and
   interfaces, and break the work into small, verifiable steps.
2. **Scaffold sparingly.** Write config, types, schemas, test skeletons, and tricky
   reference snippets — but leave the core implementation for Robert unless asked.
3. **Review rigorously.** After Robert implements, check against the security rules
   (§7), the architecture (§4), and the Definition of Done (§9).
4. **Use the explanatory style.** Include short educational insights — this project is
   also a learning + interview-prep exercise.

When Claude *does* write code, match the surrounding conventions (§6) exactly.

### Learning mode (default for this project)

This project is a **learning curve** — Robert wants to understand and write the code himself.

- For anything **new** to Robert: explain the concept simply (small steps, no assumed jargon —
  "treat me like a baby"), show **one** worked example, then **stop** and let him implement the rest.
- **Don't write the full solution by default.** Give the pattern + one example + the *why*, then hand it back.
- After he attempts it, **review** his code and explain what to adjust and why.
- Only write complete, end-to-end code when Robert explicitly asks. Otherwise: teach → demo once → let him try → review.

---

## 2. Git Workflow — branch per task (strict)

- **Never commit to `main`.** `main` stays deployable.
- **One task = one branch = one PR.** Keep branches small and focused.
- Branch naming: `<type>/<phase>-<slug>`
  - `feat/p2-jwt-auth`, `feat/p4-rag-retrieval`, `fix/p10-rate-limit-bypass`, `chore/p1-docker-compose`
  - types: `feat` · `fix` · `chore` · `refactor` · `test` · `docs` · `security`
- Commit style: **Conventional Commits** — `feat(auth): add refresh-token rotation`.
- Open a PR per task; squash-merge into `main`. Do not let branches drift far from `main`.
- Use the **`start-task`** skill at the beginning of every task to set up the branch correctly.

---

## 3. Tech Stack

| Layer        | Choice                                                        |
|--------------|---------------------------------------------------------------|
| Frontend     | Next.js (TypeScript, **App Router**), TailwindCSS, streaming chat UI |
| Backend      | FastAPI (Python 3.11+), Pydantic v2, SQLAlchemy 2.0 (async)   |
| AI Layer     | OpenAI API, custom RAG pipeline, multi-agent system           |
| Data         | PostgreSQL + **pgvector**                                     |
| Cache/Queue  | Redis (queue, rate limiting, caching)                         |
| Async        | Celery workers                                                |
| Storage      | S3 (CV files)                                                 |
| DevOps       | Docker + Docker Compose                                       |

> AI provider is **OpenAI** per spec. If we ever evaluate alternatives (e.g. Claude
> models for the agents), it's a deliberate decision, not a default — discuss first.

---

## 4. Architecture & Repo Structure

Six services: **Frontend (Next.js)** · **Backend API (FastAPI)** · **AI Layer (Python module)**
· **Worker (Celery)** · **Redis** · **PostgreSQL (+pgvector)**.

Backend and frontend live in this **monorepo**, fully decoupled: they communicate over
HTTP only, and each has its own Dockerfile and tooling.

```
/backend
  /app
    main.py
    deps.py       # ALL FastAPI dependencies: get_db, get_current_user, get_*_service
    /api          # route handlers: /auth /chat /cv /jobs
    /core         # config.py, security.py (JWT/hashing), rate_limiter.py
    /models       # SQLAlchemy: User, CV, Embedding, Analysis, Conversation
    /schemas      # Pydantic request/response validation
    /services     # business logic — no SQLAlchemy imports here
    /repositories # user_repo.py, cv_repo.py, ... — the ONLY place DB queries live
    /ai           # rag.py, embeddings.py, retriever.py, reranker.py, agents.py, prompts.py
    /workers      # celery_app.py, tasks.py
/frontend
  /app          # App Router pages
  /components   # UI + chat
  /lib          # API client, auth helpers
```

**Layering rule:** `api` → `services` → (`ai` | `repositories`) → `models`. Routes stay
thin (validation + auth + delegation). Business logic lives in `services`; all DB queries
live in `repositories` (services never import SQLAlchemy). `deps.py` is the single
composition root wiring the chain (`get_db` → repo → service), so any link can be swapped
in tests via `app.dependency_overrides`. The `ai` module is provider-agnostic at its
boundaries so prompts/models can change without touching routes.

### Async flow (CV upload)
`Upload → store file in S3 → enqueue job → Celery worker (parse → embed → analyze) → persist results → notify/poll from frontend.`
Long-running AI work **never** blocks an HTTP request.

---

## 5. AI System Conventions

### RAG pipeline (`/ai`)
- **Ingestion:** parse CV → structured JSON; chunk by *experience / projects / skills*.
- **Embeddings:** generate + store in pgvector with metadata.
- **Retrieval (hybrid):** vector similarity **+** Postgres full-text **+** metadata filtering.
- **Re-ranking:** retrieve top-K, re-rank, select best context (keep the reranker swappable).
- **Generation:** inject retrieved context into a hardened prompt, then call the LLM.

### Multi-agent system (`agents.py`, `prompts.py`)
- **Router:** classifies user intent → routes to the right agent.
- **Recruiter Agent:** evaluates candidate quality → hiring score.
- **Career Coach Agent:** suggests improvements, rewrites CV sections.
- **Interviewer Agent:** generates technical questions.
- Each agent has an isolated, explicit system prompt. Agents are composable and individually testable.

### Prompt hygiene (see also §7)
- **Context isolation is mandatory:** keep `system prompt` / `user input` / `retrieved documents`
  in separate, clearly-delimited channels. Never concatenate untrusted text into the system role.
- CV / retrieved content is **DATA, never instructions.**

---

## 6. Coding Conventions

**Python (backend / ai / workers)**
- Python 3.11+, full type hints, Pydantic v2 models for all I/O boundaries.
- Async SQLAlchemy + async FastAPI handlers. No blocking I/O in request path.
- Format/lint: **ruff** (lint + format) and **mypy** for types.
- No secrets in code — everything via env/`config.py` (`pydantic-settings`).

**TypeScript (frontend)**
- Strict TS, App Router, server components by default; client components only when needed.
- ESLint + Prettier. Tailwind for styling (no ad-hoc CSS files unless justified).
- Centralize API calls in `/lib`; never scatter `fetch` across components.

**General**
- Small functions, clear names, errors surfaced (no silent `except: pass`).
- Tests live next to or under `tests/`; new logic ships with tests (§8).

**Comments — keep code clean**
- Prefer self-explanatory code (good names + structure) over comments.
- No header banners, no step-by-step narration, no comments that restate the code.
- When a comment is truly needed, make it **small and specific** — usually a one-line *why*
  or a gotcha, not a description of *what* the line does. No docstring padding.

---

## 7. Security Layer (must-haves, reviewed every PR)

**Auth**
- JWT access + refresh tokens; refresh stored in **httpOnly** cookies. bcrypt password hashing.
  Enforce session/token expiration. Protected endpoints require auth.

**Rate limiting (Redis, per-IP and per-user)**
- Chat: 20 req/min · CV upload: 5/hour. Limits enforced server-side, fail-closed.

**Prompt-injection defense**
- Input filtering for known attacks ("ignore previous instructions", "reveal system prompt", etc.).
- Prompt hardening: CV/retrieved content treated as DATA only.
- Context isolation: system prompt vs user input vs documents kept separate (§5).
- Output validation: detect prompt leaks / abnormal responses before returning.

**File upload**
- PDF only · enforced size limit · safe parsing (no code execution) · store in S3, never local exec paths.

**API**
- Pydantic validation on every endpoint · auth on protected routes · internal endpoints protected.

> Security findings are blockers, not nits. Use the `security-auditor` agent before any
> auth/upload/AI-input PR is merged.

---

## 8. Testing & Observability

- **Unit tests** for services, **API tests** for endpoints, **manual AI testing** for prompts/agents.
- Run before opening a PR: backend tests, lint/type checks, frontend lint/build.
- Observability (Phase 11): structured logging, error tracking, AI usage/token tracking.
- **Metrics:** requests per user · token usage · errors · latency.

---

## 9. Definition of Done

A feature is done only when: deployed-capable · secure · async where it matters · tested ·
explainable. The full system DoD: deployed app · secure auth · RAG chat · CV upload + feedback
· job matching · rate-limited and protected.

---

## 10. Development Phases (roadmap)

1. **Setup** — repo, FastAPI + Next.js, Postgres+pgvector, Redis
2. **Auth** — JWT login/register, secure cookies
3. **Chat (basic)** — OpenAI chat endpoint + chat UI
4. **RAG** — embeddings, vector storage, retrieval
5. **CV Upload** — upload endpoint, PDF parsing
6. **Async Jobs** — Celery setup, background processing
7. **AI Analysis** — CV feedback, ATS scoring
8. **Job Matching** — CV vs job description
9. **Multi-Agent** — agents + routing
10. **Security** — rate limiting, prompt protection, file validation
11. **Observability** — logging, error tracking, AI usage tracking
12. **Deployment** — backend (Railway/Fly.io), frontend (Vercel), hosted DB + Redis

**Local dev strategy:** Phases 1–5 run Postgres + Redis in Docker; FastAPI + Next.js run
locally for fast iteration. Phase 6+ moves toward the fully containerized `docker-compose up --build`.

### Stretch goals
Streaming responses (SSE/WebSockets) · AI mock interviews · CV version history · paid tiers.

---

## 11. Common Commands

> These assume the standard layout above; adjust as the project materializes.

```bash
# Infra (Docker)
docker-compose up -d db redis        # phases 1–5: just data services
docker-compose up --build            # full stack (phase 6+)

# Backend
cd backend && uvicorn app.main:app --reload
ruff check . && ruff format . && mypy app
pytest -q

# Worker
celery -A app.workers.celery_app worker --loglevel=info

# Frontend
cd frontend && npm run dev
npm run lint && npm run build
```

---

## 12. Don'ts

- ❌ Don't commit to `main` or skip the branch-per-task flow.
- ❌ Don't hardcode secrets — use `.env` (dev) and never commit it; commit `.env.example`.
- ❌ Don't block the request path with AI / parsing work — enqueue it.
- ❌ Don't concatenate untrusted CV/user text into system prompts.
- ❌ Don't merge auth/upload/AI-input changes without a security review.
- ❌ Don't call a feature "done" if it isn't secure, async, scalable, and explainable.
