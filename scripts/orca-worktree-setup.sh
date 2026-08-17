#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

# A linked worktree only gets tracked files; gitignored ones live in the primary checkout.
primary="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"

if [ "$primary" = "$PWD" ]; then
  echo "orca-setup: primary checkout — nothing to seed"
elif [ -f .env ]; then
  echo "orca-setup: .env already present, leaving it alone"
elif [ -f "$primary/.env" ]; then
  cp "$primary/.env" .env
  echo "orca-setup: copied .env from $primary"
else
  echo "orca-setup: no .env in $primary — copy .env.example and fill it in" >&2
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "orca-setup: uv not on PATH; cannot install backend deps" >&2
  exit 1
fi
# The dev tools are an extra, and `uv sync` prunes anything outside what it is told to install.
(cd backend && uv sync --extra dev)

if [ -f frontend/package.json ]; then
  (cd frontend && npm ci)
fi

# Postgres and Redis are shared: the compose services bind fixed host ports, so
# every worktree talks to the one stack started from the primary checkout.
echo "orca-setup: done — data services come from 'docker compose up -d database redis' in $primary"
