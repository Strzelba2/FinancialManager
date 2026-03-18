FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

ARG APP_HOME=/app
WORKDIR ${APP_HOME}

FROM base AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/requirements.txt ${APP_HOME}/requirements/requirements.txt

RUN pip install --upgrade pip \
    && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements/requirements.txt


FROM base AS dev

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="$JAVA_HOME/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jre-headless \
    build-essential \
    libpq-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG APP_HOME=/app
ARG APP_USER=uiUser
ARG APP_GROUP=nice-ui
ARG UID=1000
ARG GID=1000

RUN groupadd -g ${GID} -r ${APP_GROUP} && \
    useradd -u ${UID} -r -g ${APP_GROUP} -d ${APP_HOME} -m ${APP_USER}

RUN ls -la ${APP_HOME}

COPY --chown=${APP_USER}:${APP_GROUP} . ${APP_HOME}/

RUN pip install --upgrade pip \
    && pip install -r ${APP_HOME}/requirements/requirements.txt

RUN mkdir -p ${APP_HOME}/logs && \
  chown -R ${APP_USER}:${APP_GROUP} ${APP_HOME}/logs && \
  chmod 775 ${APP_HOME}/logs

USER ${APP_USER}

CMD ["python", "main.py"]

FROM base AS prod

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="$JAVA_HOME/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jre-headless \
    libpq5 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG APP_HOME=/app
ARG APP_USER=uiUser
ARG APP_GROUP=nice-ui

RUN groupadd -r ${APP_GROUP} && \
    useradd -r -g ${APP_GROUP} -d ${APP_HOME} -m ${APP_USER}

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

COPY --chown=${APP_USER}:${APP_GROUP} . ${APP_HOME}/

USER ${APP_USER}