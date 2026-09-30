PY := .venv/bin/python
COMPOSE := docker compose --env-file .env -f infra/docker-compose.yml
.PHONY: setup seed up infra simulator demo demo-queryflux test integration integration-queryflux verify-dual-engine lint frontend-build benchmark down queryflux api processor sql-evidence browser-test routed-api up-queryflux monitoring monitoring-down monitoring-test
setup:
	python3 scripts/setup_env.py
	python3 -m venv .venv
	$(PY) -m pip install -r requirements.lock
	cd frontend && npm ci
	$(PY) -m scripts.queryflux_config --compose
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
demo-queryflux:
	$(PY) -m scripts.queryflux_config --compose
	ANALYTICS_ROUTE=queryflux $(COMPOSE) --profile queryflux --profile demo up --build -d
test:
	$(PY) -m pytest -q
integration:
	RUN_INTEGRATION=1 $(PY) -m pytest -q
integration-queryflux:
	docker compose exec -T -e RUN_INTEGRATION=1 -e EXPECT_QUERYFLUX=1 backend python -m pytest tests/integration -q
verify-dual-engine:
	docker compose exec -T backend python -m scripts.verify_dual_engine
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
up-queryflux:
	$(PY) -m scripts.queryflux_config --compose
	ANALYTICS_ROUTE=queryflux $(COMPOSE) --profile queryflux up --build -d
routed-api:
	ANALYTICS_ROUTE=queryflux $(COMPOSE) up -d --no-deps --force-recreate backend
api:
	$(PY) -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
processor:
	$(PY) -m processor.consumer
browser-test:
	cd frontend && node scripts/smoke.mjs
monitoring:
	$(COMPOSE) --profile monitoring up --build -d --wait metrics-exporter prometheus grafana
monitoring-down:
	$(COMPOSE) --profile monitoring stop grafana prometheus metrics-exporter
monitoring-test:
	$(PY) -m scripts.verify_monitoring
down:
	$(COMPOSE) --profile demo --profile queryflux --profile monitoring --profile iceberg down
.PHONY: iceberg iceberg-down iceberg-status iceberg-test iceberg-integration
iceberg:
	$(COMPOSE) --profile iceberg up --build -d --wait iceberg
iceberg-down:
	$(COMPOSE) --profile iceberg stop iceberg
iceberg-status:
	$(COMPOSE) exec -T iceberg python -m archive.cli status
iceberg-test:
	$(PY) -m pytest tests/unit/test_iceberg.py -q
iceberg-integration:
	$(COMPOSE) exec -T -e RUN_ICEBERG_INTEGRATION=1 iceberg python -m pytest tests/integration/test_iceberg_stack.py -q
