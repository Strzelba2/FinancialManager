from django.http import HttpRequest, HttpResponse
from typing import Callable
import logging

logger = logging.getLogger("request")


class RequestLoggingMiddleware:
    """
    Middleware that logs each HTTP request/response pair
 
    """
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """
        Initialize the middleware .
        """
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """
        Time the request, call the downstream handler

        Args:
            request: The incoming Django HttpRequest.

        Returns:
            HttpResponse: The response produced by the downstream view/middleware.
        """
        response = self.get_response(request)
        logger.info(
            f"{request.method} {request.get_full_path()} {response.status_code}"
        )
        return response
    
