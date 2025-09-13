build:
	docker compose -f docker-compose.yml up --build -d --remove-orphans

down:
	docker compose -f docker-compose.yml down

down-v:
	docker compose -f docker-compose.yml down -v

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