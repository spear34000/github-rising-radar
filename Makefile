up:
	docker compose up --build

down:
	docker compose down

migrate:
	cd apps/api && alembic upgrade head

seed:
	radar seed-demo

test:
	pytest tests -q

test-backend:
	pytest tests/test_scoring tests/test_api -q

lint:
	ruff check packages apps && ruff format --check packages apps

typecheck:
	mypy packages apps

smoke:
	python scripts/smoke_live.py --repos torvalds/linux,anthropics/claude-code --max-calls 20
