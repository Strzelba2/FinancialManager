FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

ARG APP_HOME=/session_auth
WORKDIR ${APP_HOME}


FROM base AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/requirements.txt ${APP_HOME}/requirements/requirements.txt

RUN pip install --upgrade pip \
    && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements/requirements.txt

FROM base AS dev

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    procps \
    && rm -rf /var/lib/apt/lists/*

ARG APP_HOME=/session_auth
ARG APP_USER=sessionUser
ARG APP_GROUP=session
ARG UID=1000
ARG GID=1000
RUN groupadd -g ${GID} -r ${APP_GROUP} \
 && useradd -m -u ${UID} -g ${APP_GROUP} -d ${APP_HOME} ${APP_USER}

COPY --chown=${APP_USER}:${APP_GROUP} . ${APP_HOME}/

RUN pip install --upgrade pip \
    && pip install -r requirements/requirements.txt \
    && pip install -r requirements/requirements-test.txt

RUN sed -i 's/\r$//g' docker/session/start.sh && \
    chmod +x docker/session/start.sh

RUN mkdir -p ${APP_HOME}/logs && \
  chown -R ${APP_USER}:${APP_GROUP} ${APP_HOME}/logs && \
  chmod 775 ${APP_HOME}/logs

USER ${APP_USER}


FROM base AS prod

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

ARG APP_HOME=/session_auth
ARG APP_USER=sessionUser
ARG APP_GROUP=session

RUN groupadd -r ${APP_GROUP} \
 && useradd -r -g ${APP_GROUP} -d ${APP_HOME} -m ${APP_USER}

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

COPY --chown=${APP_USER}:${APP_GROUP} . ${APP_HOME}/

RUN sed -i 's/\r$//g' docker/session/start.sh && \
    chmod +x docker/session/start.sh

RUN mkdir -p ${APP_HOME}/logs \
    && mkdir -p ${APP_HOME}/staticfiles \
    && chown -R ${APP_USER}:${APP_GROUP} ${APP_HOME}

ENV ENV_TYPE=prod

RUN python manage.py collectstatic --noinput

USER ${APP_USER}
