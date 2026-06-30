---
name: start-task
description: >
  Use at the START of any new piece of work on the AI Career Intelligence Platform. Enforces the
  branch-per-task workflow: confirm scope, branch off an up-to-date main with the correct name,
  break the task into small verifiable steps, and identify which files/services it touches.
  Invoke before writing any code for a task.
---

# Starting a task (branch-per-task discipline)

Follow these steps in order. Do not start editing on `main`.

## 1. Confirm scope
- Restate the task in one sentence and which **phase** (1–12, CLAUDE.md §10) it belongs to.
- Confirm it's small enough to be one PR. If it spans multiple concerns, split it into
  separate tasks/branches and do them one at a time.

## 2. Create the branch
```bash
git checkout main
git pull --ff-only            # ensure main is current (skip if offline / no remote yet)
git switch -c <type>/<phase>-<slug>
```
- `type` ∈ `feat | fix | chore | refactor | test | docs | security`
- Examples: `feat/p2-jwt-auth`, `feat/p4-rag-retrieval`, `security/p10-prompt-injection-filter`
- Verify with `git status` that you are on the new branch before touching files.

## 3. Plan the work
- List the files/services this task touches (api / core / models / schemas / services / ai /
  workers / frontend).
- Break implementation into small steps; write the test(s) first where it makes sense (TDD).
- Note the relevant **Security Layer** items (CLAUDE.md §7) up front if the task touches auth,
  upload, rate limiting, or LLM input.

## 4. Implement (Robert codes, Claude directs/reviews)
- Keep routes thin; business logic in services; AI logic behind the `/ai` interfaces.
- Run checks as you go: `ruff check`, `mypy`, `pytest` (backend); `npm run lint`/`build` (frontend).

## 5. Before opening the PR
- All tests + lint + types pass (state the evidence, don't assume).
- If the task touches auth / upload / rate limiting / LLM input → run the **security-auditor** agent.
- Conventional Commits message; open a PR per task; squash-merge into `main`.

## Definition of done reminder
Not done unless it is **secure, async (where it matters), scalable, and explainable** (CLAUDE.md §0, §9).
