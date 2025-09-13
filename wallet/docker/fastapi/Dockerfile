FROM python:3.12-slim


ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

ARG APP_HOME=/wallet_api
ARG APP_USER=walletUser
ARG APP_GROUP=wallet

WORKDIR ${APP_HOME}

RUN groupadd -r ${APP_GROUP} && \
  useradd -r -g ${APP_GROUP} -d ${APP_HOME} -m ${APP_USER}


COPY --chown=${APP_USER}:${APP_GROUP}  . ${APP_HOME}/

RUN pip install --upgrade pip \
    && pip install -r requirements/requirements.txt

RUN sed -i 's/\r$//g' docker/fastapi/start.sh && \
    chmod +x docker/fastapi/start.sh

USER ${APP_USER}