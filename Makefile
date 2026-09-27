PY := .venv/bin/python
COMPOSE := docker compose --env-file .env -f infra/docker-compose.yml
.PHONY: setup seed up infra simulator demo test integration lint frontend-build benchmark down queryflux api processor sql-evidence browser-test routed-api
setup:
	python3 scripts/setup_env.py
	python3 -m venv .venv
	$(PY) -m pip install -r requirements.lock
	cd frontend && npm ci
seed:
	$(PY) -m scripts.generate_vehicles
	$(PY) -m scripts.seed_metadata
up:
	$(COMPOSE) up --build -d
infra:
	$(COMPOSE) up -d --wait redpanda redis postgres clickhouse
simulator:
	$(PY) -m simulator.cli --vehicles 100000 --active-vehicles 1000 --rate 1000 --duration 0
demo:
	$(COMPOSE) --profile demo up --build -d
test:
	$(PY) -m pytest -q
integration:
	RUN_INTEGRATION=1 $(PY) -m pytest -q
lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
frontend-build:
	cd frontend && npm run build
benchmark:
	$(PY) -m scripts.benchmark
sql-evidence:
	$(PY) -m scripts.sql_optimization
queryflux:
	bash scripts/run_queryflux.sh
routed-api:
	ANALYTICS_ROUTE=queryflux $(COMPOSE) up -d --no-deps --force-recreate backend
api:
	$(PY) -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
processor:
	$(PY) -m processor.consumer
browser-test:
	cd frontend && node scripts/smoke.mjs
down:
	$(COMPOSE) --profile demo down
