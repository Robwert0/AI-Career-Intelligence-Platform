# Git Rules

> **`CLAUDE.md §2` is the source of truth for the git workflow.** This file is the detailed
> reference; if anything here ever disagrees with `CLAUDE.md §2`, `CLAUDE.md` wins.

## Branch naming — branch per task (strict)

Never commit to `main`. One task = one branch = one PR.

```text
<type>/<phase>-<slug>
```

- `type` ∈ `feat | fix | chore | refactor | test | docs | security`
- `phase` = the roadmap phase (CLAUDE.md §10), e.g. `p2`
- Examples: `feat/p2-jwt-auth`, `fix/p10-rate-limit-bypass`, `security/p10-prompt-injection-filter`

## Commit messages — Conventional Commits

Format: `type(scope): description`

| type       | use for                                   |
|------------|-------------------------------------------|
| `feat`     | a new feature                             |
| `fix`      | a bug fix                                  |
| `docs`     | documentation changes                     |
| `style`    | formatting only, no logic change          |
| `refactor` | code change that isn't a feature or fix   |
| `test`     | adding or updating tests                  |
| `chore`    | maintenance / tooling                     |

Examples:

```text
feat(auth): add refresh-token rotation
fix(rag): correct pgvector distance operator
chore(p1): add docker-compose for postgres + redis
```

## Commit footers

No attribution footers. The Co-Authored-By / session trailer is disabled via
`attribution` in `.claude/settings.json` — commit messages end at the body.

## Pull requests

Open one PR per task; squash-merge into `main`. If `.github/pull_request_template.md` exists, use it.
