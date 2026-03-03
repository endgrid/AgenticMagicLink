.PHONY: run lint format

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port $${BACKEND_PORT:-8000}

lint:
	ruff check .

format:
	ruff format .
	black .
