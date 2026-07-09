# Repo & Backend Structure Design

**Date:** 2026-07-09
**Status:** Approved
**Scope:** Repository layout and backend layering. No application code — this spec updates CLAUDE.md §4 and guides all future scaffolding.

## Decision 1: Monorepo

Backend and frontend live in this single repository:

```
/backend        # FastAPI — own Dockerfile, pyproject.toml
/frontend       # Next.js — own Dockerfile, package.json
docker-compose.yml
CLAUDE.md, .env.example, README.md
```

**Why:** solo project — one PR flow, one docker-compose, one set of project rules.
The two apps stay fully decoupled (HTTP-only communication, independent tooling and
Dockerfiles), so extracting them into separate repos later is cheap if ever needed.

**Rejected alternatives:** GitHub org with backend/frontend/infra repos (doubles
PR/CI/compose overhead for no benefit at this scale); two repos under the personal
account (same overhead, less discoverable).

## Decision 2: Backend layering — routes → services → repositories

```
/backend/app
  main.py
  deps.py           # ALL FastAPI dependencies: get_db, get_current_user, get_*_service
  /api              # route handlers: auth.py, chat.py, cv.py, jobs.py — thin
  /services         # business logic — no SQLAlchemy imports
  /repositories     # user_repo.py, cv_repo.py, ... — the ONLY place DB queries live
  /models           # SQLAlchemy tables
  /schemas          # Pydantic request/response validation
  /core             # config.py, security.py, rate_limiter.py
  /ai               # rag.py, embeddings.py, retriever.py, reranker.py, agents.py, prompts.py
  /workers          # celery_app.py, tasks.py
```

**Layering rule:** `api → services → repositories → models`. Routes never touch
repositories or models directly; services never import SQLAlchemy. `deps.py` is the
single composition root that wires the chain (`get_db` → repo → service) so any link
can be overridden in tests via `app.dependency_overrides`.

**Trade-off accepted:** the repository layer adds per-entity boilerplate, in exchange
for testability (mock repos, not the DB) and a clean, defensible architecture story.

## Not in scope

- Scaffolding the folders — happens when the phase-1 backend task starts, no empty
  placeholder dirs committed now.
- docker-compose.yml — separate task, Robert implements it (learning mode).
