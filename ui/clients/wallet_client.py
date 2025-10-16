import httpx
import logging
import json
from pydantic import ValidationError
from schemas.wallet import (
    ClientWalletSyncResponse, WalletCreationResponse, AccountCreationResponse
)
from typing import Optional, Dict
from nicegui import app
import uuid

logger = logging.getLogger(__name__)


class WalletClient:
    """
    Thin async client for the Wallet service.
    """
    def __init__(self) -> None:
        """Bind to a shared AsyncClient stored in app.state."""
        self.client: httpx.AsyncClient = app.state.wallet_httpx
        
    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> httpx.Response | None:
        """
        Perform an HTTP request to the Wallet service.

        Args:
            method: HTTP method (e.g., "GET", "POST", "DELETE").
            url: Path or absolute URL. If path-like, the client's base_url is used.
            headers: Extra headers (merged into the request).
            json_body: JSON-serializable body to send (sets Content-Type automatically).

        Returns:
            httpx.Response on success, or None if a timeout/HTTP error/other exception occurred.
        """
        hdrs: Dict[str, str] = {}
        if json_body is not None:
            hdrs["Content-Type"] = "application/json"
        if headers:
            hdrs.update({k: str(v) for k, v in headers.items()})

        try:
            resp = await self.client.request(method, url, headers=hdrs, json=json_body)
        except (httpx.ConnectTimeout, httpx.ReadTimeout):
            logger.warning(f"Wallet service timeout {url}")
            return None
        except httpx.HTTPError:
            logger.error(f"Wallet service HTTP error {url}")
            return None
        except Exception:
            logger.exception(f"Wallet service unexpected error {url}")
            return None

        return resp

    async def sync_user(self, payload: dict) -> Optional[ClientWalletSyncResponse]:
        """
        POST /wallet/sync/user

        Sync a user (and related wallet metadata) from the caller into the Wallet service.

        Args:
            payload: JSON body expected by the Wallet service.

        Returns:
            A validated `ClientWalletSyncResponse` on success, otherwise `None`.
        """
        logger.debug("Calling wallet-service POST /wallet/sync/user")
        
        resp = await self._request("POST", "/wallet/sync/user", json_body=payload)
        if not resp or not resp.is_success:
            logger.warning("sync_user failed: HTTP %s", resp.status_code)
            return None
        try:
            data = resp.json()
            result = ClientWalletSyncResponse.model_validate(data)
            logger.debug("sync_user validated response")
            return result
        except (ValueError, ValidationError) as e:
            logger.error(f"Wallet service invalid JSON/Schema (sync_user): {e}")
            return None
        
    async def create_wallet(self, name: str, user_id: uuid.UUID) -> Optional[WalletCreationResponse]:
        """
        POST /wallet/create/wallet

        Create a wallet with a given name for a user.

        Args:
            name: Wallet display name.
            user_id: Owner's UUID (sent via `X-User-Id`).

        Returns:
            `WalletCreationResponse` on success, otherwise `None`.
        """
        headers = {'X-User-Id': str(user_id)}
        payload = {'name': name}
        
        logger.debug("Calling wallet-service POST /wallet/create/wallet")
        resp = await self._request("POST", "/wallet/create/wallet", headers=headers, json_body=payload)
        if not resp or not resp.is_success:
            logger.warning("create_wallet failed: HTTP %s", resp.status_code)
            return None
        try:
            data = resp.json()
            result = WalletCreationResponse.model_validate(data)
            logger.debug("create_wallet validated response ")
            return result
        except (ValueError, ValidationError):
            logger.error("Wallet service invalid JSON/Schema (create_wallet): ")
            return None
        
    async def delete_wallet(self, wallet_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """
        DELETE /wallet/delete/{wallet_id}
        
        Sends X-User-Id header for simple ownership auth (temporary).
        Args:
            wallet_id: ID of the wallet to delete.
            user_id: ID of the requesting user.

        Returns:
            True on 204/200, False otherwise (including network errors).
        """
        url = f"/wallet/delete/{wallet_id}"
        headers = {"X-User-Id": str(user_id)}

        logger.debug("Calling wallet-service DELETE")
        resp = await self._request("DELETE", url, headers=headers)
        if resp is None:
            return False

        if resp.status_code in (204, 200):
            logger.info("Wallet deleted")
            return True

        if resp.status_code == 404:
            logger.info("Wallet not found: %s", wallet_id)
        elif resp.status_code == 403:
            logger.info("Forbidden deleting wallet %s for user %s", wallet_id, user_id)
        elif resp.status_code == 409:
            logger.info("Cannot delete wallet %s due to related data constraints", wallet_id)
        else:
            logger.warning("Delete wallet %s -> HTTP %s", wallet_id, resp.status_code)

        return False
    
    async def create_account(self, user_id: uuid.UUID, wallet_id: uuid.UUID, payload: dict) -> Optional[AccountCreationResponse]:
        """
        POST /wallet/{wallet_id}/account/create

        Create a new account within a wallet.

        Args:
            user_id: Requesting user's UUID (sent via `X-User-Id` header).
            wallet_id: Target wallet UUID.
            payload: JSON body expected by the Wallet service.

        Returns:
            - `AccountCreationResponse` on success
            - On conflict (409), returns the server-provided `detail` string (if present)
            - `None` on other failures or schema issues
        """
        headers = {'X-User-Id': str(user_id)}
        
        logger.debug("Calling wallet-service POST")
        
        resp = await self._request("POST", f"/wallet/{wallet_id}/account/create", headers=headers, json_body=payload)
        if not resp:
            return None
        
        if not resp.is_success:
            if resp.status_code == 409:
                try:
                    detail = resp.json().get("detail")
                except json.JSONDecodeError:
                    detail = None
                logger.info("create_account conflict (wallet_id=%s): %r", wallet_id, detail)
                return detail
            logger.warning("create_account failed: HTTP %s | body=%s", resp.status_code, _safe_body(resp))
            return None
        
        try:
            data = resp.json()
            logger.info(data)
            result = AccountCreationResponse.model_validate(data)
            logger.info("Account created in wallet ")
            return result
        except (ValueError, ValidationError):
            logger.error("Wallet service invalid JSON/Schema (create_wallet): ")
            return None
        
    async def create_transaction(self, user_id: uuid.UUID,  payload: dict) -> bool:
        """
        POST /wallet/transactions/create

        Create a new transaction for the user.

        Args:
            user_id: Requesting user's UUID (sent via `X-User-Id`).
            payload: JSON body describing the transaction.

        Returns:
            True on HTTP 201/200, False on any other status or error.
        """
        headers = {'X-User-Id': str(user_id)}
        
        logger.debug("Calling wallet-service POST")
        
        resp = await self._request("POST", "/wallet/transactions/create", headers=headers, json_body=payload)
        if not resp:
            return False
        
        if resp.status_code in (201, 200):
            logger.info("Transaction created for user")
            return True
        
        if resp.status_code == 404:
            logger.info("Account not found when creating transaction")
        
        return False
   