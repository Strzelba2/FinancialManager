import httpx
import logging
import json
from decimal import Decimal
from datetime import datetime
from pydantic import ValidationError
from typing import Optional, Dict, Any, List
from nicegui import app
import uuid
from pydantic import TypeAdapter

from schemas.wallet import (
    ClientWalletSyncResponse, WalletCreationResponse, AccountCreationResponse,
    RealEstateOut, RealEstatePriceOut, MetalHoldingOut, Currency, MetalType,
    DebtOut, RecurringExpenseOut, UserNoteOut, TransactionPageOut, BatchUpdateTransactionsRequest,
    BatchUpdateTransactionsResponse, AccountOut, SellRealEstateRequest, SellMetalRequest, 
    YearGoalOut, BrokerageEventPageOut, BatchUpdateBrokerageEventsRequest, HoldingRowOut
)

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
        headers: Optional[dict] = None,
        json_body: Optional[dict] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response | None:
        """
        Perform an HTTP request to the Wallet service.

        Args:
            method: HTTP method (e.g., "GET", "POST", "DELETE").
            url: Path or absolute URL. If path-like, the client's base_url is used.
            headers: Extra headers (merged into the request).
            json_body: JSON-serializable body to send (sets Content-Type automatically).
            params: Optional Quary params

        Returns:
            httpx.Response on success, or None if a timeout/HTTP error/other exception occurred.
        """
        hdrs: Dict[str, str] = {}
        if json_body is not None:
            hdrs["Content-Type"] = "application/json"
        if headers:
            hdrs.update({k: str(v) for k, v in headers.items()})

        try:
            resp = await self.client.request(method, url, headers=hdrs, json=json_body, params=params)
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
        if resp is None:
            logger.warning("sync_user failed: request returned None (network/timeout/exception)")
            return None
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
        if resp is None:
            logger.warning("create wallet failed: request returned None (network/timeout/exception)")
            return None
        
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
                logger.info(f"create_account conflict (wallet_id={wallet_id}): {detail}")
                return detail
            logger.warning(f"create_account failed: HTTP {resp.status_code}")
            return None
        
        try:
            data = resp.json()
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
            return None, None
        
        if resp.status_code in (201, 200):
            logger.info("Transaction created for user")
            return "Pomyślnie dodano transakcjie", 'positive'
        
        if resp.status_code == 422:
            try:
                detail = resp.json().get("detail")
            except Exception:
                detail = None
            logger.error(f"Validation error 422 for /transactions/create: {detail}")
            return detail, 'negative'

        if resp.status_code == 404:
            logger.info("Account not found when creating transaction")
        
            return "Konto nie istnieje", 'negative'
        
        return "Nieoczekiwany błąd serwera", 'negative'
    
    async def create_brokerage_event(self, user_id: uuid.UUID, payload: dict) -> bool:
        """
        Create a single brokerage event for the given user.

        Args:
            user_id: ID of the user for whom the event is created.
            payload: Event payload as a dict (must match Wallet API schema).

        Returns:
            True if the event was created successfully (200 or 201),
            False otherwise (including no response / 404 / other errors).
        """
        headers = {"X-User-Id": str(user_id)}
        
        logger.info(
            f"create_brokerage_event: payload_keys={list(payload.keys())}"
        )

        resp = await self._request("POST", "/wallet/brokerage/event", headers=headers, json_body=payload)
        if not resp:
            logger.error(
                "create_brokerage_event: no response from Wallet service "
            )
            return False
        
        if resp.status_code in (200, 201):
            logger.info("Brokerevent created for user")
            return True
        if resp.status_code == 404:
            logger.info("Account not found when creating event")
            
        logger.error(
            f"create_brokerage_event: unexpected status {resp.status_code} "
        )
        return False
    
    async def import_brokerage_events(self, user_id: uuid.UUID, payload: dict) -> Optional[Dict[str, Any]]:
        """
        Import multiple brokerage events for the given user in a single call.

        Args:
            user_id: ID of the user for whom to import events.
            payload: Import payload as a dict (typically a batch of events).

        Returns:
            Parsed JSON response as a dict on success (HTTP 200),
            or None on failure / non-200 / no response / JSON decode error.
        """
        headers = {'X-User-Id': str(user_id)}
        
        logger.info(
            f"import_brokerage_events: payload_keys={list(payload.keys())}"
        )
        
        resp = await self._request(
            "POST",
            "/wallet/brokerage/events/import",
            headers=headers,
            json_body=payload,
        )
        if not resp or resp.status_code != 200:
            logger.error(f"Brokerage events import failed: {resp}")
            return None
        try:
            data: Dict[str, Any] = resp.json()
            logger.info(
                "import_brokerage_events: import succeeded"
            )
            return data
        except Exception as e:
            logger.exception(
                f"import_brokerage_events: failed to decode JSON: {e}"
            )
            return None
   
    async def create_real_estate(
        self,
        user_id: uuid.UUID,
        payload: dict
    ) -> Optional[RealEstateOut]:
        """
        Create a real estate entry for the given user.

        Sends a POST request to the wallet service and returns the created real estate model.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            payload: JSON payload for creating the real estate.

        Returns:
            A validated `RealEstateOut` on success; otherwise `None`.
        """
        
        headers = {'X-User-Id': str(user_id)}
        logger.info(f"Request: create_real_estate user_id={user_id} payload_keys={list(payload.keys())!r}")

        resp = await self._request(
            "POST",
            "/wallet/real-estates/create",
            headers=headers,
            json_body=payload,
        )
        if resp is None:
            logger.error(f"create_real_estate: no response (user_id={user_id})")
            return None
        
        if resp.status_code == 422:
            try:
                detail = resp.json().get("detail")
            except Exception:
                detail = None
            logger.error(f"Validation error 422 for /transactions/create: {detail}")
            return None
        
        if resp.status_code == 404:
            logger.info("User do not exist")
        
            return None
        
        if resp.status_code in (201, 200):
            try:
                data: Dict[str, Any] = resp.json()
                result = RealEstateOut.model_validate(data)
                logger.info(
                    "create real estate: import succeeded"
                )
                return result
            except Exception as e:
                logger.exception(
                    f"create real estate: failed to decode JSON: {e}"
                )
                return None
            
        return None
        
    async def list_real_estates(self, user_id: uuid.UUID, wallet_id: uuid.UUID) -> List[RealEstateOut]:
        """
        List real estates for a wallet.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            wallet_id: Wallet identifier.

        Returns:
            A list of `RealEstateOut` items. Returns empty list on errors.
        """
        headers = {'X-User-Id': str(user_id)}
        logger.info(f"Request: list_real_estates user_id={user_id} wallet_id={wallet_id}")
        
        resp = await self._request(
            "GET",
            f"/wallet/{wallet_id}/real-estates",
            headers=headers,
        )
        if resp is None:
            logger.error(f"list_real_estates: no response (wallet_id={wallet_id})")
            return []
        if resp.status_code != 200:
            logger.error(
                f"list_real_estates: status={resp.status_code} body={resp.text}"
            )
            return []

        try:
            data = resp.json()
            return TypeAdapter(List[RealEstateOut]).validate_python(data)
        except Exception:
            logger.exception("list_real_estates: failed to parse response")
            return []
        
    async def update_real_estate(
        self,
        user_id: uuid.UUID,
        real_estate_id: uuid.UUID,
        name: Optional[str] = None,
        country: Optional[str] = None,
        city: Optional[str] = None,
        type_: Optional[str] = None,
        area_m2: Optional[Decimal] = None,
        purchase_price: Optional[Decimal] = None,
        purchase_currency: Optional[str] = None,
    ) -> Optional[RealEstateOut]:
        """
        Update a real estate entry.

        Only non-None fields are sent to the wallet service.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            real_estate_id: Real estate identifier.
            name: Updated name.
            country: Updated country.
            city: Updated city.
            type_: Updated type (sent as "type" in payload).
            area_m2: Updated area in square meters.
            purchase_price: Updated purchase price.
            purchase_currency: Updated purchase currency code (e.g. "PLN", "EUR").

        Returns:
            Updated `RealEstateOut` on success; otherwise `None`.
        """
        headers = {'X-User-Id': str(user_id)}
        
        payload: Dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if country is not None:
            payload["country"] = country
        if city is not None:
            payload["city"] = city
        if type_ is not None:
            payload["type"] = type_
        if area_m2 is not None:
            payload["area_m2"] = str(area_m2)
        if purchase_price is not None:
            payload["purchase_price"] = str(purchase_price)
        if purchase_currency is not None:
            payload["purchase_currency"] = purchase_currency

        if not payload:
            logger.info("update_real_estate: empty payload")
            return None

        resp = await self._request(
            "PUT",
            f"/wallet/real-estates/{real_estate_id}",
            headers=headers,
            json_body=payload,
        )
        if resp is None:
            logger.error(f"update_real_estate: no response (id={real_estate_id})")
            return None
        if resp.status_code != 200:
            logger.error(
                f"update_real_estate: status={resp.status_code} body={resp.text}"
            )
            return None

        try:
            data = resp.json()
            return RealEstateOut.model_validate(data)
        except Exception:
            logger.exception("update_real_estate: failed to parse response")
            return None
        
    async def delete_real_estate(self, user_id: uuid.UUID, real_estate_id: uuid.UUID) -> bool:
        """
        Delete a real estate entry.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            real_estate_id: Real estate identifier to delete.

        Returns:
            True if deletion succeeded (HTTP 200/204), otherwise False.
        """
        headers = {'X-User-Id': str(user_id)}
        logger.info(f"Request: delete_real_estate user_id={user_id} id={real_estate_id}")
        
        resp = await self._request(
            "DELETE",
            f"/wallet/real-estates/{real_estate_id}",
            headers=headers,
        )
        return resp is not None and resp.status_code in (200, 204)
    
    async def sell_real_estate(
        self,
        user_id: uuid.UUID,
        real_estate_id: uuid.UUID,
        deposit_account_id: uuid.UUID,
        proceeds_amount: Decimal,
        proceeds_currency: str,
        occurred_at: datetime | None = None,
        create_transaction: bool = False,
    ) -> bool:
        """
        Sell a real estate asset and optionally create a transaction.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            real_estate_id: Real estate identifier to sell.
            deposit_account_id: Deposit account that receives proceeds.
            proceeds_amount: Proceeds amount from the sale.
            proceeds_currency: Proceeds currency code (e.g. "PLN", "EUR").
            occurred_at: Optional datetime of when the sale occurred.
            create_transaction: If True, the backend also creates a transaction entry.

        Returns:
            (success, message) tuple. On success returns (True, "Sold.").
            On failure returns (False, "<reason>").
        """
        headers = {"X-User-Id": str(user_id)}
        logger.info(
            "Request: sell_real_estate "
            f"user_id={user_id} real_estate_id={real_estate_id} deposit_account_id={deposit_account_id} "
        )
        req = SellRealEstateRequest(
            deposit_account_id=deposit_account_id,
            proceeds_amount=proceeds_amount,
            proceeds_currency=proceeds_currency,
            occurred_at=occurred_at,
            create_transaction=create_transaction,
        )
        resp = await self._request(
            "PATCH",
            f"/wallet/real-estates/{real_estate_id}/sell",
            headers=headers,
            json_body=req.model_dump(mode="json", exclude_none=True),
        )
        if resp.status_code == 200:
            logger.info(f"sell_real_estate: succeeded (real_estate_id={real_estate_id})")
            return True, "Sold."
        try:
            data = resp.json()
            detail = data.get("detail", data)
            if isinstance(detail, dict):
                return False, detail.get("message") or str(detail)
            return False, str(detail)
        except Exception:
            return False, resp.text or f"Request failed ({resp.status_code})."
    
    async def get_latest_real_estate_price(
        self,
        type_: str,
        currency: str,
        country: str | None = None,
        city: str | None = None,
    ) -> Optional[RealEstatePriceOut]:
        """
        Fetch the latest real estate average price per m² for given filters.

        Args:
            type_: Real estate type (e.g. "APARTMENT", "HOUSE" - depending on your API).
            currency: Currency code for the returned price (e.g. "PLN").
            country: Optional country filter.
            city: Optional city filter.

        Returns:
            `RealEstatePriceOut` if found; otherwise None.
        """
        params = {
            "type": type_,
            "currency": currency,
        }
        if country:
            params["country"] = country
        if city:
            params["city"] = city
            
        logger.info(
            "Request: get_latest_real_estate_price "
            f"type={type_!r} currency={currency!r} country={country!r} city={city!r}"
        )

        resp = await self._request(
            "GET",
            "/wallet/real-estate-prices/latest",
            params=params,
        )
        if resp is None:
            logger.error("get_latest_real_estate_price: no response")
            return None

        if resp.status_code != 200:
            body_preview = (resp.text or "")[:500]
            logger.error(
                f"get_latest_real_estate_price: status={resp.status_code} body_preview={body_preview!r}"
            )
            return None

        data = resp.json()
        if not data:
            logger.info(
                "get_latest_real_estate_price: empty response "
                f"for type={type_!r} currency={currency!r} country={country!r} city={city!r}"
            )
            return None

        return RealEstatePriceOut.model_validate(data)
    
    async def create_real_estate_price(
        self,
        country: Optional[str],
        city: Optional[str],
        type_: str,
        currency: str,
        avg_price_per_m2: Decimal,
    ) -> Optional[RealEstatePriceOut]:
        """
        Create a real estate price entry (avg price per m²) in the wallet service.

        Args:
            country: Optional country value.
            city: Optional city value.
            type_: Real estate type.
            currency: Currency code.
            avg_price_per_m2: Average price per m².

        Returns:
            Created `RealEstatePriceOut` on success; otherwise None.
        """
        payload: Dict[str, Any] = {
            "type": type_,
            "currency": currency,
            "avg_price_per_m2": str(avg_price_per_m2),
            "country": country,
            "city": city,
        }

        resp = await self._request(
            "POST",
            "/wallet/real-estate-prices/create",
            json_body=payload,
        )
        if resp is None:
            logger.error("create_real_estate_price: no response")
            return None
        if resp.status_code != 200:
            logger.error(f"create_real_estate_price: status={resp.status_code}, body={resp.text}")
            return None

        try:
            return RealEstatePriceOut.model_validate(resp.json())
        except Exception:
            logger.exception("create_real_estate_price: parse error")
            return None
        
    async def list_metal_holdings(self, user_id: uuid.UUID, wallet_id: uuid.UUID) -> List[MetalHoldingOut]:
        """
        List metal holdings for a wallet.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            wallet_id: Wallet identifier.

        Returns:
            A list of `MetalHoldingOut`. Returns empty list on errors.
        """
        headers = {'X-User-Id': str(user_id)}
        logger.info(f"Request: list_metal_holdings user_id={user_id} wallet_id={wallet_id}")
        
        resp = await self._request("GET", 
                                   f"/wallet/{wallet_id}/metal-holdings",
                                   headers=headers,
                                   )
        if resp is None or resp.status_code != 200:
            return []
        try:
            data = resp.json()
            return [MetalHoldingOut.model_validate(x) for x in data]
        except Exception:
            logger.exception("list_metal_holdings: failed to parse response")
            return []

    async def create_metal_holding(
        self,
        user_id: uuid.UUID,
        wallet_id: uuid.UUID,
        metal: MetalType,
        grams: Decimal,
        cost_basis: Decimal,
        cost_currency: Optional[Currency] = None,
    ) -> Optional[MetalHoldingOut]:
        """
        Create a metal holding for a wallet.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            wallet_id: Wallet identifier.
            metal: Metal type (e.g. GOLD/SILVER depending on your enum).
            grams: Amount of metal in grams.
            cost_basis: Total cost basis (purchase value).
            cost_currency: Optional currency of the cost basis.

        Returns:
            Created `MetalHoldingOut` on success; otherwise None.
        """
        headers = {'X-User-Id': str(user_id)}
        
        logger.info(
            "Request: create_metal_holding "
            f"user_id={user_id} wallet_id={wallet_id} metal={metal!r} grams={grams} "
            f"cost_basis={cost_basis} cost_currency={cost_currency!r}"
        )
        
        payload: Dict[str, Any] = {
            "wallet_id": str(wallet_id),
            "metal": str(metal),
            "grams": str(grams),
            "cost_basis": str(cost_basis),
            "cost_currency": str(cost_currency) if cost_currency else None,
        }
        resp = await self._request("POST", 
                                   "/wallet/metal-holdings/create", 
                                   headers=headers,
                                   json_body=payload)
        if resp is None:
            logger.error(f"create_metal_holding: no response (wallet_id={wallet_id})")
            return None

        if resp.status_code not in (200, 201):
            body_preview = (resp.text or "")[:500]
            logger.error(
                f"create_metal_holding: status={resp.status_code} wallet_id={wallet_id} body_preview={body_preview!r}"
            )
            return None
        try:
            return MetalHoldingOut.model_validate(resp.json())
        except Exception:
            logger.exception("create_metal_holding: parse failed")
            return None

    async def update_metal_holding(
        self,
        user_id: uuid.UUID,
        metal_holding_id: uuid.UUID,
        grams: Optional[Decimal] = None,
        cost_basis: Optional[Decimal] = None,
        cost_currency: Optional[Currency] = None,
    ) -> Optional[MetalHoldingOut]:
        """
        Update an existing metal holding.

        Only non-None fields are sent. (Note: if you want to support explicitly clearing
        `cost_currency`, you need a sentinel value; with `None` you cannot distinguish
        "not provided" vs "clear".)

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            metal_holding_id: Metal holding identifier.
            grams: Optional new grams value.
            cost_basis: Optional new cost basis.
            cost_currency: Optional new currency.

        Returns:
            Updated `MetalHoldingOut` on success; otherwise None.
        """
        headers = {'X-User-Id': str(user_id)}
        
        payload: Dict[str, Any] = {}
        if grams is not None:
            payload["grams"] = str(grams)
        if cost_basis is not None:
            payload["cost_basis"] = str(cost_basis)
            
        payload["cost_currency"] = str(cost_currency) if cost_currency else None
        
        logger.info(
            "Request: update_metal_holding "
            f"user_id={user_id} id={metal_holding_id} payload_keys={list(payload.keys())!r}"
        )

        resp = await self._request("PUT", 
                                   f"/wallet/metal-holdings/{metal_holding_id}", 
                                   headers=headers,
                                   json_body=payload
                                   )
        if resp is None:
            logger.error(f"update_metal_holding: no response (id={metal_holding_id})")
            return None

        if resp.status_code != 200:
            body_preview = (resp.text or "")[:500]
            logger.error(
                f"update_metal_holding: status={resp.status_code} id={metal_holding_id} body_preview={body_preview!r}"
            )
            return None
        try:
            return MetalHoldingOut.model_validate(resp.json())
        except Exception:
            logger.exception("update_metal_holding: parse failed")
            return None

    async def delete_metal_holding(self, user_id: uuid.UUID, metal_holding_id: uuid.UUID) -> bool:
        """
        Delete a metal holding.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            metal_holding_id: Metal holding identifier to delete.

        Returns:
            True if deletion succeeded (HTTP 200/204), otherwise False.
        """
        headers = {'X-User-Id': str(user_id)}
        logger.info(f"Request: delete_metal_holding user_id={user_id} id={metal_holding_id}")
        
        resp = await self._request("DELETE",
                                   f"/wallet/metal-holdings/{metal_holding_id}",
                                   headers=headers,
                                   )
        return bool(resp is not None and resp.status_code == 200)
    
    async def sell_metal_holding(
        self,
        user_id: uuid.UUID,
        metal_holding_id: uuid.UUID,
        deposit_account_id: uuid.UUID,
        grams_sold: Decimal,
        proceeds_amount: Decimal,
        proceeds_currency: str,
        occurred_at: datetime | None = None,
        create_transaction: bool = False,
    ) -> bool:
        """
        Sell part (or all) of a metal holding and optionally create a transaction.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            metal_holding_id: Metal holding identifier to sell.
            deposit_account_id: Deposit account receiving proceeds.
            grams_sold: Amount of grams sold.
            proceeds_amount: Proceeds amount received.
            proceeds_currency: Currency code of proceeds (e.g. "PLN", "EUR").
            occurred_at: Optional datetime when the sale occurred.
            create_transaction: If True, backend creates a transaction record.

        Returns:
            (success, message). On success returns (True, "Sold."). On failure returns (False, "<reason>").
        """
        headers = {"X-User-Id": str(user_id)}
        req = SellMetalRequest(
            deposit_account_id=deposit_account_id,
            grams_sold=grams_sold,
            proceeds_amount=proceeds_amount,
            proceeds_currency=proceeds_currency,
            occurred_at=occurred_at,
            create_transaction=create_transaction,
        )
        resp = await self._request(
            "PATCH",
            f"/wallet/metal-holdings/{metal_holding_id}/sell",
            headers=headers,
            json_body=req.model_dump(mode="json", exclude_none=True),
        )
        if resp is None:
            logger.error(f"sell_metal_holding: no response (id={metal_holding_id})")
            return False, "No response from wallet service."
        if resp.status_code == 200:
            return True, "Sold."
        try:
            data = resp.json()
            detail = data.get("detail", data)
            if isinstance(detail, dict):
                return False, detail.get("message") or str(detail)
            return False, str(detail)
        except Exception:
            return False, resp.text or f"Request failed ({resp.status_code})."
    
    async def list_debts(self, user_id: uuid.UUID, wallet_id: uuid.UUID) -> List[DebtOut]:
        """
        List debts for a wallet.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            wallet_id: Wallet identifier.

        Returns:
            A list of `DebtOut`. Returns empty list on errors.
        """
        headers = {'X-User-Id': str(user_id)}
        logger.info(f"Request: list_debts user_id={user_id} wallet_id={wallet_id}")
        
        resp = await self._request("GET", f"/wallet/{wallet_id}/debts", headers=headers,)
        if resp is None:
            logger.error(f"list_debts: no response (wallet_id={wallet_id})")
            return []

        if resp.status_code != 200:
            body_preview = (resp.text or "")[:500]
            logger.error(
                f"list_debts: status={resp.status_code} wallet_id={wallet_id} body_preview={body_preview!r}"
            )
            return []

        try:
            data = resp.json()
            return [DebtOut.model_validate(x) for x in data]
        except Exception:
            logger.exception("list_debts: failed to parse response")
            return []

    async def create_debt(
        self,
        user_id: uuid.UUID,
        wallet_id: uuid.UUID,
        name: str,
        lander: str,
        amount: Decimal,
        currency: str,
        interest_rate_pct: Decimal,
        monthly_payment: Decimal,
        end_date: datetime,
    ) -> Optional[DebtOut]:
        """
        Create a debt entry for a wallet.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            wallet_id: Wallet identifier.
            name: Debt name/label.
            lander: Lender name (note: your field is `lander`; keep as-is if that is the API contract).
            amount: Principal amount.
            currency: Currency code (e.g. "PLN").
            interest_rate_pct: Interest rate in percent (e.g. 7.5).
            monthly_payment: Monthly payment amount.
            end_date: Debt end date/time (sent as ISO8601 string).

        Returns:
            Created `DebtOut` on success; otherwise None.
        """
        headers = {'X-User-Id': str(user_id)}
        
        payload: Dict[str, Any] = {
            "wallet_id": str(wallet_id),
            "name": name,
            "lander": lander,
            "amount": str(amount),
            "currency": currency,
            "interest_rate_pct": str(interest_rate_pct),
            "monthly_payment": str(monthly_payment),
            "end_date": end_date.isoformat(),
        }

        resp = await self._request("POST", "/wallet/debts/create", headers=headers, json_body=payload)
        if resp is None:
            logger.error(f"create_debt: no response (wallet_id={wallet_id})")
            return None

        if resp.status_code not in (200, 201):
            body_preview = (resp.text or "")[:500]
            logger.error(
                f"create_debt: status={resp.status_code} wallet_id={wallet_id} body_preview={body_preview!r}"
            )
            return None

        try:
            return DebtOut.model_validate(resp.json())
        except Exception:
            logger.exception("create_debt: failed to parse response")
            return None

    async def update_debt(
        self,
        debt_id: uuid.UUID,
        user_id: uuid.UUID,
        name: Optional[str] = None,
        lander: Optional[str] = None,
        amount: Optional[Decimal] = None,
        currency: Optional[str] = None,
        interest_rate_pct: Optional[Decimal] = None,
        monthly_payment: Optional[Decimal] = None,
        end_date: Optional[datetime] = None,
    ) -> Optional[DebtOut]:
        """
        Update an existing debt entry.

        Only non-None fields are sent.

        Args:
            debt_id: Debt identifier to update.
            user_id: User identifier (sent via `X-User-Id` header).
            name: Optional updated debt name.
            lander: Optional updated lender name (field name as per your API contract).
            amount: Optional updated principal amount.
            currency: Optional updated currency code (e.g. "PLN").
            interest_rate_pct: Optional updated interest rate (percent).
            monthly_payment: Optional updated monthly payment amount.
            end_date: Optional updated debt end date/time.

        Returns:
            Updated `DebtOut` on success; otherwise None.
        """
        headers = {'X-User-Id': str(user_id)}
        
        payload: Dict[str, Any] = {}

        if name is not None:
            payload["name"] = name
        if lander is not None:
            payload["lander"] = lander
        if amount is not None:
            payload["amount"] = str(amount)
        if currency is not None:
            payload["currency"] = currency
        if interest_rate_pct is not None:
            payload["interest_rate_pct"] = str(interest_rate_pct)
        if monthly_payment is not None:
            payload["monthly_payment"] = str(monthly_payment)
        if end_date is not None:
            payload["end_date"] = end_date.isoformat()
            
        if not payload:
            logger.info(f"update_debt: empty payload (debt_id={debt_id})")
            return None

        logger.info(
            f"Request: update_debt user_id={user_id} debt_id={debt_id} payload_keys={list(payload.keys())!r}"
        )

        resp = await self._request("PUT", f"/wallet/debts/{debt_id}", headers=headers, json_body=payload)
        if resp is None:
            logger.error(f"update_debt: no response (debt_id={debt_id})")
            return None

        if resp.status_code != 200:
            body_preview = (resp.text or "")[:500]
            logger.error(
                f"update_debt: status={resp.status_code} debt_id={debt_id} body_preview={body_preview!r}"
            )
            return None

        try:
            return DebtOut.model_validate(resp.json())
        except Exception:
            logger.exception("update_debt: failed to parse response")
            return None

    async def delete_debt(self, user_id: uuid.UUID, debt_id: uuid.UUID) -> bool:
        """
        Delete a debt entry.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            debt_id: Debt identifier to delete.

        Returns:
            True if deletion succeeded (HTTP 200/204), otherwise False.
        """
        headers = {'X-User-Id': str(user_id)}
        logger.info(f"Request: delete_debt user_id={user_id} debt_id={debt_id}")
        
        resp = await self._request("DELETE", f"/wallet/debts/{debt_id}", headers=headers,)
        return bool(resp is not None and resp.status_code == 200)
    
    async def list_recurring_expenses(self, user_id: uuid.UUID, wallet_id: uuid.UUID) -> List[RecurringExpenseOut]:
        """
        List recurring expenses for a wallet.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            wallet_id: Wallet identifier.

        Returns:
            A list of `RecurringExpenseOut`. Returns empty list on errors.
        """
        headers = {"X-User-Id": str(user_id)}
        logger.info(f"Request: list_recurring_expenses user_id={user_id} wallet_id={wallet_id}")
        
        resp = await self._request("GET", f"/wallet/{wallet_id}/recurring-expenses", headers=headers)
        if resp is None:
            logger.error(f"list_recurring_expenses: no response (wallet_id={wallet_id})")
            return []

        if resp.status_code != 200:
            body_preview = (resp.text or "")[:500]
            logger.error(
                f"list_recurring_expenses: status={resp.status_code} wallet_id={wallet_id} body_preview={body_preview!r}"
            )
            return []
        try:
            data = resp.json()
            return [RecurringExpenseOut.model_validate(x) for x in data]
        except Exception:
            logger.exception("list_recurring_expenses: failed to parse response")
            return []

    async def create_recurring_expense(
        self,
        user_id: uuid.UUID,
        wallet_id: uuid.UUID,
        name: str,
        category: Optional[str],
        amount: Decimal,
        currency: str,
        due_day: int,
        account: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Optional[RecurringExpenseOut]:
        """
        Create a recurring expense.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            wallet_id: Wallet identifier.
            name: Expense name.
            category: Optional category label.
            amount: Expense amount.
            currency: Currency code.
            due_day: Day of month (typically 1–31; validation depends on backend).
            account: Optional account label/reference.
            note: Optional note.

        Returns:
            Created `RecurringExpenseOut` on success; otherwise None.
        """
        headers = {"X-User-Id": str(user_id)}
        payload: Dict[str, Any] = {
            "wallet_id": str(wallet_id),
            "name": name,
            "category": category,
            "amount": str(amount),
            "currency": currency,
            "due_day": int(due_day),
            "account": account,
            "note": note,
        }
        logger.info(
            "Request: create_recurring_expense "
            f"user_id={user_id} wallet_id={wallet_id} name={name!r} amount={amount} currency={currency!r} due_day={due_day}"
        )

        resp = await self._request("POST", "/wallet/recurring-expenses/create", headers=headers, json_body=payload)
        if resp is None:
            logger.error(f"create_recurring_expense: no response (wallet_id={wallet_id})")
            return None

        if resp.status_code not in (200, 201):
            body_preview = (resp.text or "")[:500]
            logger.error(
                f"create_recurring_expense: status={resp.status_code} wallet_id={wallet_id} body_preview={body_preview!r}"
            )
            return None
        try:
            return RecurringExpenseOut.model_validate(resp.json())
        except Exception:
            logger.exception("create_recurring_expense: failed to parse response")
            return None

    async def update_recurring_expense(
        self,
        user_id: uuid.UUID,
        expense_id: uuid.UUID,
        name: Optional[str] = None,
        category: Optional[str] = None,
        amount: Optional[Decimal] = None,
        currency: Optional[str] = None,
        due_day: Optional[int] = None,
        account: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Optional[RecurringExpenseOut]:
        """
        Update a recurring expense.

        Only non-None fields are sent.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            expense_id: Recurring expense identifier.
            name: Optional updated name.
            category: Optional updated category.
            amount: Optional updated amount.
            currency: Optional updated currency.
            due_day: Optional updated due day.
            account: Optional updated account reference.
            note: Optional updated note.

        Returns:
            Updated `RecurringExpenseOut` on success; otherwise None.
        """
        headers = {"X-User-Id": str(user_id)}
        payload: Dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if category is not None:
            payload["category"] = category
        if amount is not None:
            payload["amount"] = str(amount)
        if currency is not None:
            payload["currency"] = currency
        if due_day is not None:
            payload["due_day"] = int(due_day)
        if account is not None:
            payload["account"] = account
        if note is not None:
            payload["note"] = note
            
        logger.info(
            f"Request: update_recurring_expense user_id={user_id} expense_id={expense_id} payload_keys={list(payload.keys())!r}"
        )

        resp = await self._request("PUT", f"/wallet/recurring-expenses/{expense_id}", headers=headers, json_body=payload)
        if resp is None:
            logger.error(f"update_recurring_expense: no response (expense_id={expense_id})")
            return None

        if resp.status_code != 200:
            body_preview = (resp.text or "")[:500]
            logger.error(
                f"update_recurring_expense: status={resp.status_code} expense_id={expense_id} body_preview={body_preview!r}"
            )
            return None

        try:
            return RecurringExpenseOut.model_validate(resp.json())
        except Exception:
            logger.exception("update_recurring_expense: failed to parse response")
            return None

    async def delete_recurring_expense(self, user_id: uuid.UUID, expense_id: uuid.UUID) -> bool:
        """
        Delete a recurring expense.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            expense_id: Expense identifier to delete.

        Returns:
            True if deletion succeeded (HTTP 200/204), otherwise False.
        """
        headers = {"X-User-Id": str(user_id)}
        logger.info(f"Request: delete_recurring_expense user_id={user_id} expense_id={expense_id}")
        
        resp = await self._request("DELETE", f"/wallet/recurring-expenses/{expense_id}", headers=headers)
        return bool(resp is not None and resp.status_code == 200)
    
    async def get_my_note(self, user_id: uuid.UUID) -> Optional[UserNoteOut]:
        """
        Fetch the current user's note.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).

        Returns:
            `UserNoteOut` if present; otherwise None.
        """
        headers = {"X-User-Id": str(user_id)}
        logger.info(f"Request: get_my_note user_id={user_id}")
        
        resp = await self._request("GET", "/users/me/note", headers=headers)
        if resp is None or resp.status_code != 200:
            return None

        try:
            data = resp.json()
            if data is None:
                return None
            return UserNoteOut.model_validate(data)
        except Exception:
            logger.exception("get_my_note: failed to parse response")
            return None

    async def upsert_my_note(self, user_id: uuid.UUID, text: str) -> Optional[UserNoteOut]:
        """
        Create or update the current user's note.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            text: Note text (empty string allowed).

        Returns:
            Updated `UserNoteOut` on success; otherwise None.
        """
        headers = {"X-User-Id": str(user_id)}
        payload: Dict[str, Any] = {"text": text or ""}
        logger.info(f"Request: upsert_my_note user_id={user_id} text_len={len(payload['text'])}")

        resp = await self._request("PUT", "/users/me/note", headers=headers, json_body=payload)
        if resp is None:
            logger.error("upsert_my_note: no response")
            return None

        if resp.status_code != 200:
            body_preview = (resp.text or "")[:500]
            logger.error(f"upsert_my_note: status={resp.status_code} body_preview={body_preview!r}")
            return None

        try:
            return UserNoteOut.model_validate(resp.json())
        except Exception:
            logger.exception("upsert_my_note: failed to parse response")
            return None
        
    async def list_accounts_for_user(self, user_id: uuid.UUID) -> list[AccountOut]:
        """
        List accounts for the current user.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).

        Returns:
            A list of `AccountOut`. Returns empty list on errors.
        """
        headers = {"X-User-Id": str(user_id)}
        resp = await self._request("GET", "/wallet/accounts", headers=headers)
        if resp is None:
            logger.error("list_accounts_for_user: no response")
            return []

        if resp.status_code != 200:
            body_preview = (resp.text or "")[:500]
            logger.error(f"list_accounts_for_user: status={resp.status_code} body_preview={body_preview!r}")
            return []
        try:
            return TypeAdapter(List[AccountOut]).validate_python(resp.json())
        except Exception:
            logger.exception("list_accounts_for_user: parse failed")
            return []
        
    async def list_transactions_page(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        size: int = 50,
        account_ids: Optional[List[uuid.UUID]] = None,
        categories: Optional[List[str]] = None,
        statuses: Optional[List[str]] = None,
        date_from: Optional[str] = None,  
        date_to: Optional[str] = None,  
        q: Optional[str] = None,
    ) -> Optional[TransactionPageOut]:
        """
        Fetch a paginated transactions page with optional filters.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            page: Page number (1-based).
            size: Page size.
            account_ids: Optional list of account ids to filter.
            categories: Optional list of category labels to filter.
            statuses: Optional list of status strings to filter.
            date_from: Optional start date (string; backend format-dependent).
            date_to: Optional end date (string; backend format-dependent).
            q: Optional search query.

        Returns:
            `TransactionPageOut` on success; otherwise None.
        """
        headers = {"X-User-Id": str(user_id)}

        params: Dict[str, Any] = {
            "page": int(page),
            "size": int(size),
        }
        if account_ids:
            params["account_id"] = [str(x) for x in account_ids]
        if categories:
            params["category"] = [c for c in categories if c]
        if statuses:
            params["status"] = [s for s in statuses if s]
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        if q:
            params["q"] = q

        resp = await self._request("GET", "/wallet/transactions", headers=headers, params=params)
        
        if resp is None:
            logger.error("list_transactions_page: no response")
            return None

        if resp.status_code != 200:
            body_preview = (resp.text or "")[:500]
            logger.error(f"list_transactions_page: status={resp.status_code} body_preview={body_preview!r}")
            return None

        try:
            return TransactionPageOut.model_validate(resp.json())
        except Exception:
            logger.exception("list_transactions_page: failed to parse response")
            return None

    async def batch_update_transactions(
        self,
        user_id: uuid.UUID,
        req: BatchUpdateTransactionsRequest,
    ) -> Optional[BatchUpdateTransactionsResponse]:
        """
        Batch update transactions.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            req: Batch update request model.

        Returns:
            `BatchUpdateTransactionsResponse` on success; otherwise None.
        """
        headers = {"X-User-Id": str(user_id)}
        logger.info(f"Request: batch_update_transactions user_id={user_id}")

        resp = await self._request(
            "PATCH",
            "/wallet/transactions/batch",
            headers=headers,
            json_body=req.model_dump(mode="json", exclude_none=True),
        )
        if resp is None:
            logger.error("batch_update_transactions: no response")
            return None

        if resp.status_code != 200:
            body_preview = (resp.text or "")[:500]
            logger.error(f"batch_update_transactions: status={resp.status_code} body_preview={body_preview!r}")
            return None

        try:
            return BatchUpdateTransactionsResponse.model_validate(resp.json())
        except Exception:
            logger.exception("batch_update_transactions: failed to parse response")
            return None
        
    async def delete_transaction(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> bool:
        """
        Delete a transaction.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            transaction_id: Transaction identifier to delete.

        Returns:
            True if deletion succeeded (HTTP 200/204), otherwise False.
        """
        headers = {"X-User-Id": str(user_id)}
        logger.info(f"Request: delete_transaction user_id={user_id} transaction_id={transaction_id}")
        
        resp = await self._request(
            "DELETE", 
            f"/wallet/transactions/{transaction_id}",
            headers=headers,
            )
        return bool(resp is not None and resp.status_code == 200)
        
    async def get_wallet_ytd_summary(self, user_id: uuid.UUID, wallet_id: uuid.UUID, year: int) -> Dict[str, Any]:
        """
        Fetch year-to-date summary for a wallet.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            wallet_id: Wallet identifier.
            year: Year to summarize.

        Returns:
            A dict containing YTD summary (fallback default on errors).
        """
        headers = {"X-User-Id": str(user_id)}
        logger.info(f"Request: get_wallet_ytd_summary user_id={user_id} wallet_id={wallet_id} year={year}")
        
        resp = await self._request("GET", f"/wallet/{wallet_id}/ytd-summary", headers=headers, params={"year": year})
        
        default = {"year": year, "income_by_currency": {}, "expense_by_currency": {}}

        if resp is None:
            logger.error("get_wallet_ytd_summary: no response")
            return default

        if resp.status_code != 200:
            body_preview = (resp.text or "")[:500]
            logger.error(
                f"get_wallet_ytd_summary: status={resp.status_code} wallet_id={wallet_id} body_preview={body_preview!r}"
            )
            return default

        data = resp.json() or default
        logger.debug(f"get_wallet_ytd_summary: succeeded wallet_id={wallet_id} year={year}")
        return data
            
    async def get_wallet_goals(self, user_id: uuid.UUID, wallet_id: uuid.UUID, year: int) -> Optional[YearGoalOut]:
        """
        Fetch wallet goals for a given year.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            wallet_id: Wallet identifier.
            year: Goals year.

        Returns:
            `YearGoalOut` if found; otherwise None.
        """
        headers = {"X-User-Id": str(user_id)}
        logger.info(f"Request: get_wallet_goals user_id={user_id} wallet_id={wallet_id} year={year}")
        
        resp = await self._request("GET", f"/wallet/{wallet_id}/goals", headers=headers, params={"year": year})
        if resp is None:
            logger.error("get_wallet_goals: no response")
            return None

        if resp.status_code != 200:
            body_preview = (resp.text or "")[:500]
            logger.error(f"get_wallet_goals: status={resp.status_code} body_preview={body_preview!r}")
            return None
        data = resp.json()
        if not data:
            return None
        return YearGoalOut.model_validate(data)

    async def list_wallet_goals(self, user_id: uuid.UUID, wallet_id: uuid.UUID) -> List[YearGoalOut]:
        """
        List all wallet goals.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            wallet_id: Wallet identifier.

        Returns:
            List of `YearGoalOut`. Returns empty list on errors.
        """
        headers = {"X-User-Id": str(user_id)}
        logger.info(f"Request: list_wallet_goals user_id={user_id} wallet_id={wallet_id}")
        
        resp = await self._request("GET", f"/wallet/{wallet_id}/goals/all", headers=headers)
        if resp is None:
            logger.error("list_wallet_goals: no response")
            return []

        if resp.status_code != 200:
            body_preview = (resp.text or "")[:500]
            logger.error(f"list_wallet_goals: status={resp.status_code} body_preview={body_preview!r}")
            return []

        try:
            data = resp.json() or []
            items = [YearGoalOut.model_validate(x) for x in data]
            logger.debug(f"list_wallet_goals: returned items_count={len(items)} wallet_id={wallet_id}")
            return items
        except Exception:
            logger.exception("list_wallet_goals: failed to parse/validate response")
            return []

    async def upsert_wallet_goals(
        self,
        user_id: uuid.UUID,
        wallet_id: uuid.UUID,
        year: int,
        rev_target_year: Decimal,
        exp_budget_year: Decimal,
        currency: str,
    ) -> Optional[YearGoalOut]:
        """
        Upsert (create or update) wallet goals.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            wallet_id: Wallet identifier.
            year: Goals year.
            rev_target_year: Revenue target for the year.
            exp_budget_year: Expense budget for the year.
            currency: Currency code.

        Returns:
            `YearGoalOut` on success; otherwise None.
        """
        headers = {"X-User-Id": str(user_id)}
        payload: Dict[str, Any] = {
            "wallet_id": str(wallet_id),
            "year": int(year),
            "rev_target_year": str(rev_target_year),
            "exp_budget_year": str(exp_budget_year),
            "currency": currency,
        }
        logger.info(
            "Request: upsert_wallet_goals "
            f"user_id={user_id} wallet_id={wallet_id} year={year} currency={currency!r}"
        )
        
        resp = await self._request("POST", "/wallet/goals/upsert", headers=headers, json_body=payload)
        if resp is None:
            logger.error("upsert_wallet_goals: no response")
            return None

        if resp.status_code not in (200, 201):
            body_preview = (resp.text or "")[:500]
            logger.error(f"upsert_wallet_goals: status={resp.status_code} body_preview={body_preview!r}")
            return None
        try:
            result = YearGoalOut.model_validate(resp.json())
            logger.info(f"upsert_wallet_goals: succeeded (goal_id={getattr(result, 'id', None)})")
            return result
        except Exception:
            logger.exception("upsert_wallet_goals: failed to parse/validate response")
            return None

    async def update_wallet_goals(
        self,
        user_id: uuid.UUID,
        goal_id: uuid.UUID,
        rev_target_year: Optional[Decimal] = None,
        exp_budget_year: Optional[Decimal] = None,
        currency: Optional[str] = None,
    ) -> Optional[YearGoalOut]:
        """
        Update an existing goals entry.

        Only non-None fields are sent.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            goal_id: Goals identifier.
            rev_target_year: Optional new revenue target.
            exp_budget_year: Optional new expense budget.
            currency: Optional new currency code.

        Returns:
            Updated `YearGoalOut` on success; otherwise None.
        """
        headers = {"X-User-Id": str(user_id)}
        payload: Dict[str, Any] = {}
        if rev_target_year is not None:
            payload["rev_target_year"] = str(rev_target_year)
        if exp_budget_year is not None:
            payload["exp_budget_year"] = str(exp_budget_year)
        if currency is not None:
            payload["currency"] = currency

        resp = await self._request("PUT", f"/wallet/goals/{goal_id}", headers=headers, json_body=payload)
        if resp is None:
            logger.error("update_wallet_goals: no response")
            return None

        if resp.status_code != 200:
            body_preview = (resp.text or "")[:500]
            logger.error(f"update_wallet_goals: status={resp.status_code} body_preview={body_preview!r}")
            return None

        try:
            result = YearGoalOut.model_validate(resp.json())
            logger.info(f"update_wallet_goals: succeeded (goal_id={goal_id})")
            return result
        except Exception:
            logger.exception("update_wallet_goals: failed to parse/validate response")
            return None

    async def delete_wallet_goals(self, user_id: uuid.UUID, goal_id: uuid.UUID) -> bool:
        """
        Delete wallet goals entry.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            goal_id: Goals identifier to delete.

        Returns:
            True if deletion succeeded (HTTP 200/204), otherwise False.
        """
        headers = {"X-User-Id": str(user_id)}
        logger.info(f"Request: delete_wallet_goals user_id={user_id} goal_id={goal_id}")
                    
        resp = await self._request("DELETE", f"/wallet/goals/{goal_id}", headers=headers)
        return bool(resp is not None and resp.status_code == 200)
    
    async def list_brokerage_accounts_for_user(self, user_id: uuid.UUID):
        """
        List brokerage accounts for the current user.

        Note: This method returns raw JSON (dicts) because your snippet does not show a typed model.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).

        Returns:
            A list of brokerage accounts as raw dicts. Returns empty list on errors.
        """
        headers = {"X-User-Id": str(user_id)}
        logger.info(f"Request: list_brokerage_accounts_for_user user_id={user_id}")
        
        resp = await self._request("GET", "/wallet/brokerage/accounts", headers=headers)
        if resp is None:
            logger.error("list_brokerage_accounts_for_user: no response")
            return []

        if resp.status_code != 200:
            body_preview = (resp.text or "")[:500]
            logger.error(
                f"list_brokerage_accounts_for_user: status={resp.status_code} body_preview={body_preview!r}"
            )
            return []
        try:
            return resp.json()  
        except Exception:
            logger.exception("list_brokerage_accounts_for_user: parse failed")
            return []

    async def list_brokerage_events_page(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        size: int = 40,
        brokerage_account_ids: Optional[List[uuid.UUID]] = None,
        kinds: Optional[List[str]] = None,
        currencies: Optional[List[str]] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        q: Optional[str] = None,
    ) -> Optional[BrokerageEventPageOut]:
        """
        Fetch a paginated brokerage events page with optional filters.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            page: Page number (1-based).
            size: Page size.
            brokerage_account_ids: Optional list of brokerage account ids.
            kinds: Optional list of event kinds.
            currencies: Optional list of currencies.
            date_from: Optional start date filter (string; backend format-dependent).
            date_to: Optional end date filter (string; backend format-dependent).
            q: Optional search query.

        Returns:
            `BrokerageEventPageOut` on success; otherwise None.
        """
        headers = {"X-User-Id": str(user_id)}
        params: Dict[str, Any] = {"page": int(page), "size": int(size)}

        if brokerage_account_ids:
            params["brokerage_account_id"] = [str(x) for x in brokerage_account_ids]
        if kinds:
            params["kind"] = [k for k in kinds if k]
        if currencies:
            params["currency"] = [c for c in currencies if c]
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        if q:
            params["q"] = q

        resp = await self._request("GET", "/wallet/brokerage/events", headers=headers, params=params)
        if resp is None:
            logger.error("list_brokerage_events_page: no response")
            return None

        if resp.status_code != 200:
            body_preview = (resp.text or "")[:500]
            logger.error(f"list_brokerage_events_page: status={resp.status_code} body_preview={body_preview!r}")
            return None

        try:
            return BrokerageEventPageOut.model_validate(resp.json())
        except Exception:
            logger.exception("list_brokerage_events_page: failed to parse/validate response")
            return None

    async def batch_update_brokerage_events(
        self,
        user_id: uuid.UUID,
        req: BatchUpdateBrokerageEventsRequest,
    ) -> bool:
        """
        Batch update brokerage events.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            req: Batch update request model.

        Returns:
            True if backend reports success (HTTP 200/204), otherwise False.
        """
        headers = {"X-User-Id": str(user_id)}
        logger.info(f"Request: batch_update_brokerage_events user_id={user_id}")
        
        resp = await self._request(
            "PATCH", 
            "/wallet/brokerage/events/batch", 
            headers=headers, 
            json_body=req.model_dump(mode="json", exclude_none=True)
            )
        return bool(resp is not None and resp.status_code in (200, 204))
    
    async def delete_brokerage_event(self, user_id: uuid.UUID, event_id: uuid.UUID) -> bool:
        """
        Delete a brokerage event.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            event_id: Event identifier to delete.

        Returns:
            True if deletion succeeded (HTTP 200/204), otherwise False.
        """
        headers = {"X-User-Id": str(user_id)}
        logger.info(f"Request: delete_brokerage_event user_id={user_id} event_id={event_id}")
        
        resp = await self._request(
            "DELETE", 
            f"/wallet/brokerage/events/{event_id}",
            headers=headers, 
            )
        return bool(resp is not None and resp.status_code == 200)
    
    async def list_holdings_for_user(
        self,
        user_id: uuid.UUID,
        brokerage_account_ids: Optional[List[uuid.UUID]] = None,
        q: Optional[str] = None,
    ) -> list[HoldingRowOut]:
        """
        List holdings for the user, optionally filtered by brokerage accounts and search query.

        Args:
            user_id: User identifier (sent via `X-User-Id` header).
            brokerage_account_ids: Optional list of brokerage account ids.
            q: Optional search query.

        Returns:
            A list of `HoldingRowOut`. Returns empty list on errors.
        """
        headers = {"X-User-Id": str(user_id)}
        params: Dict[str, Any] = {}
        if q:
            params["q"] = q

        if brokerage_account_ids:
            params["brokerage_account_id"] = [str(x) for x in brokerage_account_ids]

        resp = await self._request(
            "GET", f"/users/{user_id}/holdings", 
            headers=headers, 
            params=params
            )
        if resp is None:
            logger.error("list_holdings_for_user: no response")
            return []

        if resp.status_code != 200:
            body_preview = (resp.text or "")[:500]
            logger.error(
                f"list_holdings_for_user: status={resp.status_code} body_preview={body_preview!r}"
            )
            return []
        try:
            return [HoldingRowOut.model_validate(x) for x in (resp.json() or [])]
        except Exception:
            logger.exception("list_holdings_for_user: failed to parse response")
            return None
    
        
    
    



