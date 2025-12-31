from fastapi import Header, HTTPException, status, Request
from uuid import UUID
import logging

from app.clients.auth_client import AuthCryptoClient
from app.clients.stock_client import StockClient

logger = logging.getLogger(__name__)


async def get_internal_user_id(x_user_id: str = Header(...)) -> UUID:
    """
    Dependency function to extract and validate the `X-User-Id` header as a UUID.

    Args:
        x_user_id (str): Value from the `X-User-Id` HTTP header.

    Returns:
        UUID: Parsed UUID object.

    Raises:
        HTTPException: If the header is missing or not a valid UUID.
    """
    logger.debug(f"Received X-User-Id header: {x_user_id}")
    try:
        return UUID(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid X-User-Id"
        )
   
        
def get_auth_crypto(request: Request) -> AuthCryptoClient:
    """
    Retrieve the `AuthCryptoClient` from the FastAPI app instance.

    Args:
        request (Request): FastAPI request object.

    Returns:
        AuthCryptoClient: The initialized authentication crypto client.
    """
    logger.debug("Retrieving AuthCryptoClient from request.app")
    return request.app.state.auth_client


def get_stock_client(request: Request) -> StockClient:
    """
    Retrieve the StockClient instance stored in the Starlette/FastAPI app state.

    This is a small dependency/helper used to access the shared HTTPX-based client:
        request.app.state.stock_httpx

    Args:
        request: Current incoming request object.

    Returns:
        StockClient instance from application state.
    """
    logger.debug("get_stock_client: resolved StockClient from app.state")
    return request.app.state.stock_httpx
