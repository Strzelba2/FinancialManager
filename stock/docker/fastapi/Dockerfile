FROM python:3.12-slim


ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    XDG_CACHE_HOME=/tmp/.cache 

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG APP_HOME=/stock_api
ARG APP_USER=stockUser
ARG APP_GROUP=stock
ARG UID=1000
ARG GID=1000

WORKDIR ${APP_HOME}

RUN groupadd -g ${GID} -r ${APP_GROUP} && \
    useradd -u ${UID} -r -g ${APP_GROUP} -d ${APP_HOME} -m ${APP_USER}


COPY --chown=${APP_USER}:${APP_GROUP}  . ${APP_HOME}/

RUN pip install --upgrade pip \
    && pip install -r requirements/requirements.txt \
    && pip install playwright

RUN playwright install --with-deps chromium \
    && mkdir -p /ms-playwright \
    && chown -R ${APP_USER}:${APP_GROUP} /ms-playwright

RUN sed -i 's/\r$//g' docker/fastapi/start.sh && \
    chmod +x docker/fastapi/start.sh

RUN mkdir -p ${APP_HOME}/logs && \
    chown -R ${APP_USER}:${APP_GROUP} ${APP_HOME}/logs && \
    chmod 775 ${APP_HOME}/logs

USER ${APP_USER}