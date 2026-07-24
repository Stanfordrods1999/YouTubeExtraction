.PHONY: install test lint dev db-reset

# Pipeline tooling (the legacy scraper has its own Makefile in legacy/).

install:
	uv sync

test:
	uv run pytest tests/ -q

lint:
	uv run ruff check .

dev:
	uv run langgraph dev

db-reset:
	supabase db reset
