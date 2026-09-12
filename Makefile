.PHONY: install dev-api dev-web test lint typecheck build benchmark docker-up
install:
	python -m pip install -e ".[dev,analysis]"
	cd apps/web && npm install

dev-api:
	uvicorn changetrace_api.main:app --app-dir apps/api --reload

dev-web:
	cd apps/web && npm run dev

test:
	pytest --cov --cov-report=term-missing

lint:
	ruff check .

typecheck:
	mypy packages/schemas/changetrace_schemas services workers/analysis apps/api/changetrace_api
	cd apps/web && npx tsc --noEmit

build:
	cd apps/web && npm run build

benchmark:
	pytest tests/evaluation/test_benchmark.py -m evaluation -vv
	python tests/evaluation/benchmark/run.py

e2e:
	cd apps/web && npm run test:e2e

docker-up:
	docker compose up --build
