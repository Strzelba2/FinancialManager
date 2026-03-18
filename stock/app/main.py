from contextlib import asynccontextmanager
from fastapi import Response

from pythonjsonlogger import jsonlogger
from app.api.main import api_router
from app.core.config import settings
from app.db.session import db
from app.core.app import App


import logging
import os

env_type = os.getenv("ENV_TYPE", "local")
log_to_stdout = env_type == "prod"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO" if env_type == "prod" else "DEBUG")

logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)

if logger.hasHandlers():
    logger.handlers.clear()


log_format = (
    '%(levelname)s %(name)-12s %(asctime)s %(module)s %(process)d %(thread)d %(message)s'
)
formatter = jsonlogger.JsonFormatter(log_format)

if log_to_stdout:
    logHandler = logging.StreamHandler()
else:
    ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    log_file = os.path.join(ROOT_DIR, 'logs', 'stock.json')
    logHandler = logging.FileHandler(log_file, encoding='utf-8')

logHandler.setFormatter(formatter)

logger.addHandler(logHandler)


@asynccontextmanager
async def lifespan(app: App):
    logger.info("Startup App")
    await db.init_db()
    await app.startup()
    try:
        yield
    finally:
        logger.info("Shutdown App")
        await app.shutdown()

app = App(
    debug=True,
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    lifespan=lifespan,
)


@app.get("/healthz", include_in_schema=False)
def healthz() -> Response:
    return Response(status_code=200)


app.include_router(api_router)
