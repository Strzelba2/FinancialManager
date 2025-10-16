FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jre-headless \
    build-essential \
    libpq-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="$JAVA_HOME/bin:${PATH}"

ARG APP_HOME=/app
ARG APP_USER=uiUser
ARG APP_GROUP=nice-ui

WORKDIR ${APP_HOME}

RUN groupadd -r ${APP_GROUP} && \
  useradd -r -g ${APP_GROUP} -d ${APP_HOME} -m ${APP_USER}

RUN ls -la ${APP_HOME}

COPY --chown=${APP_USER}:${APP_GROUP} . ${APP_HOME}/

RUN pip install --upgrade pip \
    && pip install -r ${APP_HOME}/requirements/requirements.txt

RUN mkdir -p ${APP_HOME}/logs && \
  chown -R ${APP_USER}:${APP_GROUP} ${APP_HOME}/logs && \
  chmod 775 ${APP_HOME}/logs

CMD ["python", "main.py"]