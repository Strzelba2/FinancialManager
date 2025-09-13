FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    procps \
    && rm -rf /var/lib/apt/lists/*

ARG APP_HOME=/session_auth
ARG APP_USER=sessionUser
ARG APP_GROUP=session

WORKDIR ${APP_HOME}

RUN groupadd -r ${APP_GROUP} && \
  useradd -r -g ${APP_GROUP} -d ${APP_HOME} -m ${APP_USER}


COPY --chown=${APP_USER}:${APP_GROUP}  . ${APP_HOME}/

RUN pip install --upgrade pip \
    && pip install -r requirements/requirements.txt

RUN sed -i 's/\r$//g' docker/session/start.sh && \
    chmod +x docker/session/start.sh

RUN mkdir -p ${APP_HOME}/logs && \
  chown -R ${APP_USER}:${APP_GROUP} ${APP_HOME}/logs && \
  chmod 775 ${APP_HOME}/logs

USER ${APP_USER}
