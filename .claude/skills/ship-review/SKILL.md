---
name: ship-review
description: Use when an implementation task on this project is complete (code written, working locally) and it's time to get it onto main — or when the user says "ship it", "make the PR", or "review and merge".
---

# Ship & Review (senior-engineer gate)

Take a finished implementation from working-locally to squash-merged, with a real
review in between. The PR is not the goal; the reviewed PR is.

## The shape of a shipment

Run these six stages in order. Each produces evidence; no stage is skipped because
the change "is small".

### 1. Gate locally — evidence, not vibes

```bash
# backend changes
cd backend && pytest -q && ruff check . && ruff format --check . && mypy .
# frontend changes
cd frontend && npm run lint && npm run build
```

All green before anything else. Paste/state the actual results.

### 2. Commit & push (Robert pushes; git push is deny-listed for Claude)

Conventional Commit on a `<type>/<phase>-<slug>` branch (GIT_RULES.md). Suggest the
`! git push -u origin <branch>` command.

### 3. Open the PR

Use `gh-axi pr create --title "..." --body-file <path>` (Robert's standing rule:
prefer `gh-axi` for all GitHub operations — token-efficient). If it hits the
Projects-classic GraphQL bug that breaks `gh pr create`, fall back to
`gh api -X POST repos/{owner}/{repo}/pulls`. Body follows `.github/pull_request_template.md`:
**Description** (prose: what, why, phase, verification evidence), **Key points**
(decisions + trade-offs a reviewer would question), **Changes** (one line per commit).

### 4. Senior review of the full diff — two passes, always

**Pass A — domain agents (launch in parallel where independent):**
- `pr-review-toolkit:code-reviewer` on the diff vs `main` — always.
- `security-auditor` — REQUIRED if the diff touches auth, file upload, rate
  limiting, or anything feeding user/CV content into an LLM (CLAUDE.md §7).
  Security findings are blockers, never nits.

**Pass B — architecture check against CLAUDE.md (the agents don't know it's a teaching project):**
- Layering respected: `routes → services → (ai | repositories) → models`; routes thin.
- Async correctness: no blocking I/O in request paths; long AI work enqueued.
- §0 test: is this Secure, Async, Scalable, Explainable? One sentence each.
- Learning-mode check: if Robert wrote it, findings are explained (what + why),
  not silently fixed.

### 5. Verdict, stated explicitly

Rank findings: **Blockers** (bugs, security, layering violations) → **Should-fix**
(would embarrass in an interview) → **Nits**. End with one line:
`VERDICT: merge` or `VERDICT: fix blockers first`. Blockers get fixed on the same
branch and re-gated (stage 1) before proceeding.

### 6. Merge only on green

Wait for CI checks on the PR to complete (`gh-axi pr view <n>` shows check status;
poll until settled). All green + verdict is merge → **squash-merge**
(`gh-axi pr merge <n> --squash`; fallback `gh api -X PUT .../merge` with
`"merge_method": "squash"`), then clean up: `git checkout main && git pull --ff-only
&& git fetch --prune && git branch -D <branch>`.

## Common mistakes

- Reviewing the PR description instead of the diff — always review `git diff main...HEAD`.
- Skipping stage 4 because CI is green — CI checks style and tests, not design.
- Fixing review findings directly in learning mode — explain first (CLAUDE.md §1).
- Merging with a red or still-running check because "it's unrelated".
