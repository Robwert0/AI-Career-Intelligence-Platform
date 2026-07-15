.PHONY: migrations migrate downgrade current lint fix test check
MAKEFLAGS += --no-print-directory

migrations:
	@test -n "$(m)" || (echo 'usage: make migrations m="describe the change"' && exit 1)
	@uv run alembic revision --autogenerate -m "$(m)"

migrate:
	@uv run alembic upgrade head

downgrade:
	@uv run alembic downgrade -1

current:
	@uv run alembic current

lint:
	@uv run ruff check . && uv run ruff format --check . && uv run mypy app

fix:
	@uv run ruff check --fix . && uv run ruff format .

test:
	@uv run pytest -q

check:
	@$(MAKE) lint || ($(MAKE) fix && $(MAKE) lint)
