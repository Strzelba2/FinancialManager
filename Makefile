build:
	UID=$$(id -u) GID=$$(id -g) docker compose -f docker-compose.yml up --build -d --remove-orphans

down:
	docker compose -f docker-compose.yml down

down-v:
	docker compose -f docker-compose.yml down -v

up:
	docker compose -f docker-compose.yml up -d --remove-orphans

recreate:
	UID=$$(id -u) GID=$$(id -g)  docker compose -f docker-compose.yml up -d --remove-orphans --force-recreate

recreate-session:
	UID=$$(id -u) GID=$$(id -g)   docker compose -f docker-compose.yml up -d --force-recreate session-auth

recreate-wallet:
	UID=$$(id -u) GID=$$(id -g)   docker compose -f docker-compose.yml up -d --force-recreate wallet

recreate-stock:
	UID=$$(id -u) GID=$$(id -g)  docker compose -f docker-compose.yml up -d --force-recreate stock

recreate-pgadmin:
	UID=$$(id -u) GID=$$(id -g)  docker compose -f docker-compose.yml up -d --force-recreate pgadmin

recreate-next-ui:
	UID=$$(id -u) GID=$$(id -g)  docker compose -f docker-compose.yml up -d --force-recreate next-ui

wallet-migrate:
	UID=$$(id -u) GID=$$(id -g) docker compose -f docker-compose.yml up -d wallet-db
	UID=$$(id -u) GID=$$(id -g) docker compose -f docker-compose.yml run --rm wallet alembic upgrade head

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
