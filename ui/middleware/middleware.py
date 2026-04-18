from fastapi import Request

from starlette.middleware.base import BaseHTTPMiddleware
import logging
import contextvars

current_request = contextvars.ContextVar("current_request")

logger = logging.getLogger(__name__)


class ClientDataMiddleware(BaseHTTPMiddleware):
    
    async def dispatch(self, request: Request, call_next):

        logger.debug(f"request.client: {request.client}")
        logger.debug(f"request.app: {request.app}")
        logger.debug(f"request.base_url: {request.base_url}")
        logger.debug(f"request.json: {request.json}")
        logger.debug(f"request.method: {request.method}")
        logger.debug(f"request.url: {request.url}")

        logger.debug(f"request.headers:{request.headers}")
        logger.debug(f"type request.headers:{type(request.headers)}")
        logger.debug(f"request.cookies:{request.cookies}")

        response = await call_next(request)
        return response
