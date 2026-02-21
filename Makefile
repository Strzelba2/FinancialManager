build:
	UID=$$(id -u) GID=$$(id -g) docker compose -f docker-compose.yml up --build -d --remove-orphans

down:
	docker compose -f docker-compose.yml down

down-v:
	docker compose -f docker-compose.yml down -v

up:
	docker compose -f docker-compose.yml up -d --remove-orphans

recreate:
	docker compose -f docker-compose.yml up -d --remove-orphans --force-recreate

recreate-session:
	docker compose -f docker-compose.yml up -d --force-recreate session-auth

recreate-wallet:
	docker compose -f docker-compose.yml up -d --force-recreate wallet-service

recreate-stock:
	docker compose -f docker-compose.yml up -d --force-recreate stock-service

recreate-pgadmin:
	UID=$$(id -u) GID=$$(id -g)  docker compose -f docker-compose.yml up -d --force-recreate pgadmin

makemigrations:
	docker compose -f docker-compose.yml run --rm session-auth python manage.py makemigrations

migrate:
	docker compose -f docker-compose.yml run --rm session-auth python manage.py migrate

bash:
	docker compose -f docker-compose.yml run --rm session-auth /bin/bash

env:
	docker compose -f docker-compose.yml run --rm session-auth printenv

superuser:
	docker compose -f docker-compose.yml run --rm session-auth python3 manage.py createsuperuser