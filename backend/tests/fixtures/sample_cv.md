# Ada Lovelace

## Summary

Backend engineer with eight years building async Python services. Focused on data-heavy
systems, retrieval, and the unglamorous parts of making them reliable in production.

## Work Experience

### Senior Backend Engineer — Difference Engine Ltd (2022–present)

Owned the ingestion pipeline that processes roughly two million documents a day. Rewrote the
scheduler from a cron-based design to a Celery topology with idempotent tasks, which cut
duplicate processing from 4% to under 0.1%. Introduced pgvector-backed semantic search and
tuned the HNSW parameters against a hand-labelled relevance set.

Mentored two juniors through their first on-call rotations and wrote the runbooks the team
still uses.

### Backend Engineer — Analytical Systems (2019–2022)

Built and maintained a FastAPI service handling authentication for eleven internal tools.
Migrated it from synchronous SQLAlchemy to the 2.0 async API without downtime, using a
dual-write period and a shadow-read comparison to prove equivalence before cutover.

## Projects

### Notes Engine

A self-hosted RAG system over personal notes. Hybrid retrieval combining pgvector cosine
similarity with Postgres full-text search, then a cross-encoder re-ranking pass.

### Punch Card

A tiny CLI for tracking focus time, written to learn Rust properly.

## Technical Skills

Python, Rust, SQL, TypeScript. FastAPI, SQLAlchemy, Celery, Alembic. PostgreSQL with
pgvector, Redis, S3. Docker, GitHub Actions, Terraform.

## Education

BSc Mathematics, University of London (2015–2018). Dissertation on numerical methods for
differential equations.

## Certifications

AWS Certified Solutions Architect — Associate (2023).

## Languages

English (native), French (professional working proficiency).
