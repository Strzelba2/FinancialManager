from fastapi import Request

from starlette.middleware.base import BaseHTTPMiddleware
import logging
import contextvars

current_request = contextvars.ContextVar("current_request")

logger = logging.getLogger(__name__)


class ClientDataMiddleware(BaseHTTPMiddleware):
    
    async def dispatch(self, request: Request, call_next):

        logger.info(f"request.client: {request.client}")
        logger.info(f"request.app: {request.app}")
        logger.info(f"request.base_url: {request.base_url}")
        logger.info(f"request.json: {request.json}")
        logger.info(f"request.method: {request.method}")
        logger.info(f"request.url: {request.url}")

        logger.info(f"request.headers:{request.headers}")
        logger.info(f"type request.headers:{type(request.headers)}")
        logger.info(f"request.cookies:{request.cookies}")

        response = await call_next(request)
        return response
