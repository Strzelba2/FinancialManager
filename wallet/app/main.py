from contextlib import asynccontextmanager

from pythonjsonlogger import jsonlogger
import logging
import os

from app.api.main import api_router
from app.core.config import settings
from app.db.session import db
from app.core.app import App
from app.clients.auth_client import AuthCryptoClient
from app.clients.stock_client import StockClient


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

log_file = os.path.join(ROOT_DIR, 'logs', 'wallet.json')

logger = logging.getLogger()
logHandler = logging.FileHandler(log_file, encoding='utf-8')

log_format = (
    '%(levelname)s %(name)-12s %(asctime)s %(module)s %(process)d %(thread)d %(message)s'
)

formatter = jsonlogger.JsonFormatter(log_format)
logHandler.setFormatter(formatter)

if logger.hasHandlers():
    logger.handlers.clear()

logger.addHandler(logHandler)
logger.setLevel(logging.DEBUG)


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: App):
    logger.info("Startup App")
    await db.init_db()
    await app.startup()
    app.state.auth_client = AuthCryptoClient(settings.AUTH_URL)
    app.state.stock_httpx = StockClient()
    try:
        yield
    finally:
        logger.info("Shutdown App")
        await app.state.auth_client.aclose()
        await app.state.stock_httpx.aclose()
        await app.shutdown()

app = App(
    debug=True,
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    lifespan=lifespan,
)

app.include_router(api_router)
