import httpx
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class AuthCryptoClient:
    """
    Asynchronous client for interacting with a cryptographic microservice
    that performs HMAC and encryption operations in batch mode.

    Attributes:
        client (httpx.AsyncClient): The underlying HTTP client with timeouts and HTTP/2 enabled.
    """
    def __init__(self, base_url: str):
        """
        Initialize the client with a base URL for the crypto service.

        Args:
            base_url (str): The base URL of the crypto service (e.g., "http://localhost:8000").
        """
        self.client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(5.0, read=5.0, connect=3.0),
            http2=True,  
        )
        
    async def aclose(self) -> None:
        """
        Gracefully close the underlying HTTP client.
        Should be called on shutdown to avoid warnings.
        """
        logger.debug("Closing AuthCryptoClient connection")
        await self.client.aclose()
        
    async def batch(self, username: str, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Send a batch of encryption/HMAC operations to the crypto server.

        Args:
            username (str): The user performing the operation (used for key scoping).
            data (List[Dict[str, Any]]): A list of operations, e.g.,
                [{"id": "iban_h", "kind": "hmac", "plaintext_b64": "..."}]

        Returns:
            dict | None: The parsed JSON response if successful, or None if an error occurred.
        """
        logger.info(f"Sending crypto batch request for user: {username} with {len(data)} items")
        resp = await self.client.post(
            "/crypto/batch",
            json={"username": username, "data": data},
        )
        
        if not resp.is_success:
            logger.warning(f"Crypto server got response -> {resp.status_code}")
            return None
        
        return resp.json()
