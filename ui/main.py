from pythonjsonlogger import jsonlogger
import logging
import os
from fastapi import Request
from fastapi.responses import Response

import pages.home
import pages.login
import pages.logout
import pages.register
import pages.home
import pages.wallet.user_wallet
import pages.wallet.transactions
import pages.error

from middleware.middleware import ClientDataMiddleware
from exceptions import UnauthorizedError, BadRequestError, InternalServerError
from storage.session_storage import SessionStorage

from nicegui import ui, app
from nicegui.client import Client
from nicegui.page import page

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__)))

log_file = os.path.join(ROOT_DIR, 'logs', 'ui.json')

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

app.add_middleware(ClientDataMiddleware)

app.storage = SessionStorage()
      
        
@app.exception_handler(Exception)
async def _exception_handler(request: Request, exception: Exception) -> Response:
    logger.info(f"exception_handler: {exception}/{type(exception)}")
    status = 500
    with Client(page(''), request=request) as client:
        if isinstance(exception, InternalServerError):
            pages.error.error_page(status, str(exception))
        elif isinstance(exception, BadRequestError):
            status = 400
            pages.error.error_page(status, str(exception))
        elif isinstance(exception, UnauthorizedError):
            status = 401
            pages.error.error_page(status, str(exception))
     
        pages.error.error_page(status, str(exception))       
    return client.build_response(request, status)
    
    
@app.on_page_exception
def handle_page_error(exception: Exception) -> None:
    logger.exception(f'Unhandled page exception: {type(exception)}', 
                     exc_info=(type(exception), exception, exception.__traceback__))

    if isinstance(exception, NameError) or isinstance(exception, TypeError):
        raise InternalServerError("Unexpected error occurred on the page.")
    if isinstance(exception, AttributeError):
        raise InternalServerError("Unexpected error occurred on the page.")
    if isinstance(exception, RuntimeError):
        raise InternalServerError("Unexpected error occurred on the page.")
  
    
SECRET_KEY = os.environ.get("SECRET_KEY")


if __name__ in {"__main__", "__mp_main__"}:
    
    ui.run(host="0.0.0.0", port=8501, title="FinansowaEg – Twój partner w finansach", storage_secret=SECRET_KEY)
