.DEFAULT_GOAL := build

COMPOSE = env UID=$$(id -u) GID=$$(id -g) docker compose -f docker-compose.yml
TEST_COMPOSE_PROJECT_NAME ?= financialmanager_tests
TEST_COMPOSE = env TEST_COMPOSE_PROJECT_NAME=$(TEST_COMPOSE_PROJECT_NAME) UID=$$(id -u) GID=$$(id -g) docker compose -p $(TEST_COMPOSE_PROJECT_NAME) -f docker-compose.yml -f tests/docker-compose.tests.yml
COVERAGE_CHANGED_LINES_FILE ?= /tmp/financialmanager-coverage-changed-lines.json
TEST_ALL_REPORT_TARGET ?= allure-up
LOGIN_CAPACITY_STEPS ?= 250,500,1000
LOGIN_CAPACITY_MAX_USERS ?= 1000
LOGIN_CAPACITY_MIN_PASS_USERS ?= 500
LOGIN_CAPACITY_PATHS ?= /wallet,/transactions
LOGIN_CAPACITY_REQUEST_TIMEOUT_SECONDS ?= 30
LOGIN_CAPACITY_STOP_ON_FAILURE ?= 1
LOGIN_CAPACITY_SESSION_ENV_TYPE ?= prod
LOGIN_CAPACITY_SESSION_GUNICORN_WORKERS ?= 3
LOGIN_CAPACITY_SESSION_GUNICORN_TIMEOUT ?= 60
LOGIN_CAPACITY_SESSION_GUNICORN_LOG_LEVEL ?= info
LOGIN_CAPACITY_SESSION_ALLOWED_HOSTS ?= wallet.localhost,localhost,127.0.0.1,session-auth,session-auth.localhost,next.localhost

.PHONY: \
	network-create \
	build down down-v up recreate recreate-session recreate-wallet recreate-stock recreate-pgadmin recreate-next-ui \
	session-makemigrations makemigrations session-migrate migrate wallet-migrate stock-migrate \
	smoke-test functional-test component-test integration-test \
	security-fuzz-test security-load-test login-stress-test login-capacity-test dast-plan-test login-dast-test login-security-test \
	unit-test unit-test-stock unit-test-wallet unit-test-session unit-test-next-ui \
	coverage-unit coverage-unit-stock coverage-unit-wallet coverage-unit-session coverage-unit-next-ui \
	quality-test quality-test-python quality-test-next-ui \
	test-all allure-report allure-up allure-down ci-allure-up \
	bash env superuser \
	db-backup db-backup-session db-backup-stock db-backup-wallet \
	db-restore-session-latest db-restore-stock-latest db-restore-wallet-latest db-restore-all-latest \
	db-restore-session db-restore-stock db-restore-wallet db-restore-all db-list-backups

build: network-create
	$(COMPOSE) up --build -d --remove-orphans

down:
	$(COMPOSE) down

down-v:
	@if [ "$(CONFIRM)" != "1" ]; then \
		echo "Refusing to remove Docker volumes without CONFIRM=1."; \
		echo "This command deletes local database data stored in Docker volumes."; \
		echo "Use: make down-v CONFIRM=1"; \
		exit 1; \
	fi
	$(COMPOSE) down -v

up: network-create
	$(COMPOSE) up -d --remove-orphans

recreate: network-create
	$(COMPOSE) up -d --remove-orphans --force-recreate

recreate-session: network-create
	$(COMPOSE) up -d --force-recreate session-auth

recreate-wallet: network-create
	$(COMPOSE) up -d --force-recreate wallet

recreate-stock: network-create
	$(COMPOSE) up -d --force-recreate stock

recreate-pgadmin: network-create
	$(COMPOSE) up -d --force-recreate pgadmin

recreate-next-ui: network-create
	$(COMPOSE) up -d --force-recreate next-ui

network-create:
	bash scripts/ensure-docker-network.sh financial_manager

wallet-migrate: network-create
	$(COMPOSE) up -d wallet-db
	$(COMPOSE) run --rm wallet alembic upgrade head

stock-migrate: network-create
	$(COMPOSE) up -d stock-db
	$(COMPOSE) run --rm stock alembic upgrade head

smoke-test:
	bash tests/docker/run_with_test_runtime.sh bash tests/docker/run_robot_smoke.sh

functional-test:
	bash tests/docker/run_with_test_runtime.sh bash tests/docker/run_robot_functional.sh

component-test:
	bash tests/docker/run_with_test_runtime.sh bash tests/docker/run_pytest_group.sh component_tests

integration-test:
	bash tests/docker/run_with_test_runtime.sh bash tests/docker/run_pytest_group.sh integration_tests

security-fuzz-test:
	bash tests/docker/run_with_test_runtime.sh bash tests/docker/run_pytest_group.sh security_tests

security-load-test:
	bash tests/docker/run_with_test_runtime.sh bash tests/docker/run_pytest_group.sh performance_tests

login-stress-test:
	bash tests/docker/run_with_test_runtime.sh bash tests/docker/run_pytest_group.sh load_tests -m "not capacity"

login-capacity-test:
	SESSION_AUTH_ENV_TYPE="$(LOGIN_CAPACITY_SESSION_ENV_TYPE)" \
	SESSION_AUTH_GUNICORN_WORKERS="$(LOGIN_CAPACITY_SESSION_GUNICORN_WORKERS)" \
	SESSION_AUTH_GUNICORN_TIMEOUT="$(LOGIN_CAPACITY_SESSION_GUNICORN_TIMEOUT)" \
	SESSION_AUTH_GUNICORN_LOG_LEVEL="$(LOGIN_CAPACITY_SESSION_GUNICORN_LOG_LEVEL)" \
	SESSION_AUTH_ALLOWED_HOSTS="$(LOGIN_CAPACITY_SESSION_ALLOWED_HOSTS)" \
	bash tests/docker/run_with_test_runtime.sh env \
		LOGIN_CAPACITY_ENABLED=1 \
		LOGIN_CAPACITY_STEPS="$(LOGIN_CAPACITY_STEPS)" \
		LOGIN_CAPACITY_MAX_USERS="$(LOGIN_CAPACITY_MAX_USERS)" \
		LOGIN_CAPACITY_MIN_PASS_USERS="$(LOGIN_CAPACITY_MIN_PASS_USERS)" \
		LOGIN_CAPACITY_PATHS="$(LOGIN_CAPACITY_PATHS)" \
		LOGIN_CAPACITY_REQUEST_TIMEOUT_SECONDS="$(LOGIN_CAPACITY_REQUEST_TIMEOUT_SECONDS)" \
		LOGIN_CAPACITY_STOP_ON_FAILURE="$(LOGIN_CAPACITY_STOP_ON_FAILURE)" \
		SESSION_AUTH_ENV_TYPE="$(LOGIN_CAPACITY_SESSION_ENV_TYPE)" \
		SESSION_AUTH_GUNICORN_WORKERS="$(LOGIN_CAPACITY_SESSION_GUNICORN_WORKERS)" \
		SESSION_AUTH_GUNICORN_TIMEOUT="$(LOGIN_CAPACITY_SESSION_GUNICORN_TIMEOUT)" \
		SESSION_AUTH_GUNICORN_LOG_LEVEL="$(LOGIN_CAPACITY_SESSION_GUNICORN_LOG_LEVEL)" \
		SESSION_AUTH_ALLOWED_HOSTS="$(LOGIN_CAPACITY_SESSION_ALLOWED_HOSTS)" \
		bash tests/docker/run_login_capacity_probe.sh

dast-plan-test:
	bash tests/docker/run_with_test_runtime.sh bash tests/docker/run_pytest_group.sh dast_tests

login-dast-test:
	bash tests/docker/run_zap_login_dast.sh

login-security-test: network-create
	MAKE="$(MAKE)" REPORT_TARGET="allure-report" bash tests/run_make_batch.sh security-fuzz-test security-load-test dast-plan-test

unit-test: network-create
	MAKE="$(MAKE)" REPORT_TARGET="allure-report" bash tests/run_make_batch.sh unit-test-stock unit-test-wallet unit-test-session unit-test-next-ui

unit-test-stock: network-create
	rm -rf stock/tests/artifacts/allure-results
	mkdir -p stock/tests/artifacts/allure-results
	$(COMPOSE) run --rm --no-deps stock python -m pytest -c pytest.ini tests --alluredir tests/artifacts/allure-results

unit-test-wallet: network-create
	rm -rf wallet/tests/artifacts/allure-results
	mkdir -p wallet/tests/artifacts/allure-results
	$(COMPOSE) run --rm --no-deps wallet python -m pytest -c pytest.ini tests --alluredir tests/artifacts/allure-results

unit-test-session: network-create
	rm -rf session/tests/artifacts/allure-results
	mkdir -p session/tests/artifacts/allure-results
	$(COMPOSE) run --rm --no-deps session-auth python -m pytest -c pytest.ini tests --alluredir tests/artifacts/allure-results

unit-test-next-ui: network-create
	$(COMPOSE) run --rm --no-deps --user 0:0 next-ui sh -c 'rm -rf tests/artifacts/allure-results'
	mkdir -p next-ui/tests/artifacts/allure-results
	$(COMPOSE) run --rm --no-deps next-ui npm install
	$(COMPOSE) run --rm --no-deps next-ui npm run test:unit
	$(COMPOSE) run --rm --no-deps --user 0:0 next-ui sh -c 'chown -R $(shell id -u):$(shell id -g) tests/artifacts'

coverage-unit: network-create
	MAKE="$(MAKE)" REPORT_TARGET="allure-report" bash tests/run_make_batch.sh coverage-unit-stock coverage-unit-wallet coverage-unit-session coverage-unit-next-ui

coverage-unit-stock: network-create
	rm -rf stock/tests/artifacts/allure-results stock/tests/artifacts/coverage.xml stock/tests/artifacts/coverage-html
	mkdir -p stock/tests/artifacts/allure-results
	$(COMPOSE) run --rm --no-deps stock python -m pytest -c pytest.ini tests --alluredir tests/artifacts/allure-results --cov --cov-config=.coveragerc --cov-branch --cov-report=term-missing --cov-report=xml:tests/artifacts/coverage.xml --cov-report=html:tests/artifacts/coverage-html --cov-fail-under=55

coverage-unit-wallet: network-create
	rm -rf wallet/tests/artifacts/allure-results wallet/tests/artifacts/coverage.xml wallet/tests/artifacts/coverage-html
	mkdir -p wallet/tests/artifacts/allure-results
	$(COMPOSE) run --rm --no-deps wallet python -m pytest -c pytest.ini tests --alluredir tests/artifacts/allure-results --cov --cov-config=.coveragerc --cov-branch --cov-report=term-missing --cov-report=xml:tests/artifacts/coverage.xml --cov-report=html:tests/artifacts/coverage-html --cov-fail-under=8

coverage-unit-session: network-create
	rm -rf session/tests/artifacts/allure-results session/tests/artifacts/coverage.xml session/tests/artifacts/coverage-html
	mkdir -p session/tests/artifacts/allure-results
	$(COMPOSE) run --rm --no-deps session-auth python -m pytest -c pytest.ini tests --alluredir tests/artifacts/allure-results --cov --cov-config=.coveragerc --cov-branch --cov-report=term-missing --cov-report=xml:tests/artifacts/coverage.xml --cov-report=html:tests/artifacts/coverage-html --cov-fail-under=25

coverage-unit-next-ui: network-create
	$(COMPOSE) run --rm --no-deps --user 0:0 next-ui sh -c 'rm -rf tests/artifacts/allure-results tests/artifacts/coverage-html'
	mkdir -p next-ui/tests/artifacts/allure-results
	$(COMPOSE) run --rm --no-deps next-ui npm install
	$(COMPOSE) run --rm --no-deps next-ui npm run test:coverage
	$(COMPOSE) run --rm --no-deps next-ui sh -c 'npm audit --json > tests/artifacts/npm-audit.json 2>/dev/null; exit 0'
	$(COMPOSE) run --rm --no-deps --user 0:0 next-ui sh -c 'chown -R $(shell id -u):$(shell id -g) tests/artifacts'

quality-test: network-create
	MAKE="$(MAKE)" bash tests/run_make_batch.sh quality-test-python quality-test-next-ui

quality-test-python: network-create
	$(COMPOSE) run --rm --no-deps stock python -m compileall -q app tests
	$(COMPOSE) run --rm --no-deps wallet python -m compileall -q app tests
	$(COMPOSE) run --rm --no-deps session-auth python -m compileall -q userauth utils tests

quality-test-next-ui: network-create
	$(COMPOSE) run --rm --no-deps next-ui npm install
	$(COMPOSE) run --rm --no-deps next-ui npm run test:quality

test-all: network-create
	MAKE="$(MAKE)" REPORT_TARGET="$(TEST_ALL_REPORT_TARGET)" bash tests/run_make_batch.sh coverage-unit-stock coverage-unit-wallet coverage-unit-session coverage-unit-next-ui smoke-test functional-test component-test integration-test security-fuzz-test security-load-test login-stress-test dast-plan-test

allure-report:
	python3 tests/docker/collect_changed_lines.py --output "$(COVERAGE_CHANGED_LINES_FILE)"
	GIT_COMMIT=$$(git rev-parse --short HEAD 2>/dev/null || echo "unknown") \
	GIT_BRANCH=$$(git branch --show-current 2>/dev/null || echo "unknown") \
	GIT_STATUS=$$(git diff --quiet && git diff --cached --quiet && echo "clean" || echo "has local changes") \
	$(TEST_COMPOSE) run --rm --no-deps \
		-e GIT_COMMIT -e GIT_BRANCH -e GIT_STATUS \
		-v "$(COVERAGE_CHANGED_LINES_FILE):/tmp/coverage-changed-lines.json:ro" \
		test-runner bash tests/docker/generate_allure_report.sh

allure-up: allure-report
	$(TEST_COMPOSE) up -d --force-recreate allure-ui

allure-down:
	-$(TEST_COMPOSE) stop allure-ui
	-$(TEST_COMPOSE) rm -f allure-ui

ci-allure-up:
	bash scripts/download-ci-allure.sh

session-makemigrations: network-create
	$(COMPOSE) run --rm session-auth python manage.py makemigrations

makemigrations: session-makemigrations

session-migrate: network-create
	$(COMPOSE) run --rm session-auth python manage.py migrate

migrate: session-migrate

bash: network-create
	$(COMPOSE) run --rm session-auth /bin/bash

env: network-create
	$(COMPOSE) run --rm session-auth printenv

superuser: network-create
	$(COMPOSE) run --rm session-auth python3 manage.py createsuperuser

db-backup:
	bash scripts/db-backup.sh all

db-backup-session:
	bash scripts/db-backup.sh session

db-backup-stock:
	bash scripts/db-backup.sh stock

db-backup-wallet:
	bash scripts/db-backup.sh wallet

db-restore-session-latest:
	bash scripts/db-restore.sh session latest

db-restore-stock-latest:
	bash scripts/db-restore.sh stock latest

db-restore-wallet-latest:
	bash scripts/db-restore.sh wallet latest

db-restore-all-latest:
	bash scripts/db-restore.sh all latest

db-restore-session:
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make db-restore-session FILE=backups/db/<timestamp>/session.sql.gz"; \
		exit 1; \
	fi
	bash scripts/db-restore.sh session "$(FILE)"

db-restore-stock:
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make db-restore-stock FILE=backups/db/<timestamp>/stock.sql.gz"; \
		exit 1; \
	fi
	bash scripts/db-restore.sh stock "$(FILE)"

db-restore-wallet:
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make db-restore-wallet FILE=backups/db/<timestamp>/wallet.sql.gz"; \
		exit 1; \
	fi
	bash scripts/db-restore.sh wallet "$(FILE)"

db-restore-all:
	@if [ -z "$(DIR)" ]; then \
		echo "Usage: make db-restore-all DIR=backups/db/<timestamp>"; \
		exit 1; \
	fi
	bash scripts/db-restore.sh all "$(DIR)"

db-list-backups:
	@find backups/db -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort || true
