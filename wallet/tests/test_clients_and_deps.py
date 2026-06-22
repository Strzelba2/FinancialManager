from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4
import unittest

import allure
import httpx
import pytest
from fastapi import HTTPException

from app.api.deps import get_auth_crypto, get_internal_user_id, get_stock_client
from app.clients.auth_client import AuthCryptoClient
from app.clients.stock_client import StockClient, StockInstrumentUpdateError

pytestmark = pytest.mark.unit


class _FakeAsyncHttpClient:
    def __init__(self, response: httpx.Response | None = None, exc: Exception | None = None) -> None:
        self.response = response
        self.exc = exc
        self.calls: list[dict] = []

    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        if self.exc:
            raise self.exc
        assert self.response is not None
        return self.response


def _stock_client_with(fake_http_client: _FakeAsyncHttpClient) -> StockClient:
    client = object.__new__(StockClient)
    client.client = fake_http_client
    return client


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Wallet HTTP clients handle stock and auth service boundaries deterministically")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("clients", "http", "financial-data")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Mocks service boundaries for wallet auth/stock clients. No real network calls are made; "
    "tests cover success parsing, HTTP failures, timeouts, invalid payloads, and dependency errors."
)
class WalletClientBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_auth_crypto_batch_returns_json_on_success(self) -> None:
        client = AuthCryptoClient("http://auth.local")
        client.client.post = AsyncMock(return_value=httpx.Response(200, json={"ok": True, "items": []}))
        self.addAsyncCleanup(client.aclose)

        result = await client.batch("artur", [{"id": "iban_h", "kind": "hmac"}])

        self.assertEqual(result, {"ok": True, "items": []})
        client.client.post.assert_awaited_once_with(
            "/crypto/batch",
            json={"username": "artur", "data": [{"id": "iban_h", "kind": "hmac"}]},
        )

    async def test_auth_crypto_batch_returns_none_on_error_status(self) -> None:
        client = AuthCryptoClient("http://auth.local")
        client.client.post = AsyncMock(return_value=httpx.Response(503, json={"detail": "down"}))
        self.addAsyncCleanup(client.aclose)

        self.assertIsNone(await client.batch("artur", []))

    async def test_auth_crypto_batch_retries_temporary_rate_limit_before_success(self) -> None:
        client = AuthCryptoClient("http://auth.local")
        client.client.post = AsyncMock(side_effect=[
            httpx.Response(429, json={"detail": "throttled"}),
            httpx.Response(429, json={"detail": "throttled"}),
            httpx.Response(200, json={"results": []}),
        ])
        self.addAsyncCleanup(client.aclose)

        with patch("app.clients.auth_client.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            result = await client.batch("artur", [{"id": "acc_h", "kind": "hmac"}])

        self.assertEqual(result, {"results": []})
        self.assertEqual(client.client.post.await_count, 3)
        sleep_mock.assert_any_await(0.4)
        sleep_mock.assert_any_await(0.8)

    async def test_stock_request_sets_json_headers_and_returns_response(self) -> None:
        fake = _FakeAsyncHttpClient(httpx.Response(200, json={"ok": True}))
        client = _stock_client_with(fake)

        result = await client._request("POST", "/stock/test", json_body={"symbol": "PKO"})

        self.assertIs(result, fake.response)
        self.assertEqual(fake.calls[0]["headers"]["Content-Type"], "application/json")
        self.assertEqual(fake.calls[0]["json"], {"symbol": "PKO"})

    async def test_stock_request_returns_none_on_timeout(self) -> None:
        client = _stock_client_with(_FakeAsyncHttpClient(exc=httpx.ReadTimeout("slow")))

        self.assertIsNone(await client._request("GET", "/stock/slow"))

    async def test_latest_quotes_short_circuits_empty_symbol_list(self) -> None:
        client = _stock_client_with(_FakeAsyncHttpClient())

        self.assertEqual(await client.get_latest_quotes_for_symbols([]), {})

    async def test_latest_quotes_parses_symbol_map(self) -> None:
        fake = _FakeAsyncHttpClient(
            httpx.Response(
                200,
                json=[
                    {
                        "symbol": "PKO",
                        "price": "55.12",
                        "currency": "PLN",
                        "change_pct": "1.20",
                    }
                ],
            )
        )
        client = _stock_client_with(fake)

        result = await client.get_latest_quotes_for_symbols(["PKO"])

        self.assertEqual(list(result), ["PKO"])
        self.assertEqual(result["PKO"].price, Decimal("55.12"))

    async def test_latest_quotes_parses_wrapped_quotes_payload(self) -> None:
        fake = _FakeAsyncHttpClient(
            httpx.Response(
                200,
                json={
                    "quotes": [
                        {
                            "symbol": "PEO",
                            "price": "235.50",
                            "currency": "PLN",
                            "change_pct": "-0.59",
                        }
                    ]
                },
            )
        )
        client = _stock_client_with(fake)

        result = await client.get_latest_quotes_for_symbols(["PEO"])

        self.assertEqual(list(result), ["PEO"])
        self.assertEqual(result["PEO"].price, Decimal("235.50"))

    async def test_latest_quotes_returns_empty_dict_on_bad_status_or_payload(self) -> None:
        error_client = _stock_client_with(_FakeAsyncHttpClient(httpx.Response(500, text="boom")))
        bad_payload_client = _stock_client_with(_FakeAsyncHttpClient(httpx.Response(200, json={"bad": "shape"})))

        self.assertEqual(await error_client.get_latest_quotes_for_symbols(["PKO"]), {})
        self.assertEqual(await bad_payload_client.get_latest_quotes_for_symbols(["PKO"]), {})

    async def test_sync_daily_candles_serializes_aliases_and_parses_response(self) -> None:
        instrument_id = uuid4()
        fake = _FakeAsyncHttpClient(
            httpx.Response(
                201,
                json={
                    "sync": {
                        "symbol": "PKO",
                        "name": "PKO BP",
                        "instrument_id": str(instrument_id),
                        "requested_url": "http://stock.local",
                        "fetched_rows": 3,
                        "upserted_rows": 2,
                        "sync_start": "2026-05-01",
                        "sync_end": "2026-05-03",
                    },
                    "items_included": False,
                    "returned_count": 0,
                    "items": None,
                },
            )
        )
        client = _stock_client_with(fake)

        result = await client.sync_daily_candles(
            "PKO",
            date_from=date(2026, 5, 1),
            date_to=date(2026, 5, 3),
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.sync.symbol, "PKO")
        self.assertEqual(fake.calls[0]["url"], "/stock/instruments/PKO/candles/daily/sync")
        self.assertEqual(fake.calls[0]["json"]["from"], "2026-05-01")
        self.assertEqual(fake.calls[0]["json"]["to"], "2026-05-03")

    async def test_sync_daily_candles_returns_none_for_unavailable_stock_service(self) -> None:
        client = _stock_client_with(_FakeAsyncHttpClient(exc=httpx.ConnectTimeout("down")))

        self.assertIsNone(await client.sync_daily_candles("PKO"))

    async def test_resolve_instrument_normalizes_input_and_parses_payload(self) -> None:
        fake = _FakeAsyncHttpClient(
            httpx.Response(
                200,
                json={
                    "mic": "XWAR",
                    "symbol": "PKO",
                    "shortname": "PKO",
                    "name": "PKO BP",
                    "currency": "PLN",
                    "type": "stock",
                    "status": "active",
                },
            )
        )
        client = _stock_client_with(fake)

        result = await client.resolve_instrument(" xwar ", " pko ")

        self.assertEqual(result.symbol, "PKO")
        self.assertEqual(fake.calls[0]["params"], {"mic": "XWAR", "symbol": "PKO"})

    async def test_resolve_instrument_distinguishes_not_found_and_service_errors(self) -> None:
        not_found_client = _stock_client_with(_FakeAsyncHttpClient(httpx.Response(404, json={"detail": "missing"})))
        error_client = _stock_client_with(_FakeAsyncHttpClient(httpx.Response(503, text="down")))
        unavailable_client = _stock_client_with(_FakeAsyncHttpClient(exc=httpx.ReadTimeout("slow")))
        invalid_client = _stock_client_with(_FakeAsyncHttpClient(httpx.Response(200, json={"symbol": "PKO"})))

        with self.assertRaisesRegex(ValueError, "Instrument not found"):
            await not_found_client.resolve_instrument("XWAR", "PKO")
        with self.assertRaisesRegex(RuntimeError, "503"):
            await error_client.resolve_instrument("XWAR", "PKO")
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            await unavailable_client.resolve_instrument("XWAR", "PKO")
        with self.assertRaisesRegex(ValueError, "Invalid instrument payload"):
            await invalid_client.resolve_instrument("XWAR", "PKO")

    async def test_update_instrument_shortname_sends_conditional_patch(self) -> None:
        fake = _FakeAsyncHttpClient(
            httpx.Response(
                200,
                json={
                    "mic": "XWAR",
                    "symbol": "PKO",
                    "shortname": "PKO BP SA",
                    "name": "POWSZECHNA KASA",
                    "currency": "PLN",
                    "type": "STOCK",
                    "status": "ACTIVE",
                },
            )
        )
        client = _stock_client_with(fake)

        result = await client.update_instrument_shortname("xwar", "pko", "PKO BP SA", "PKO")

        self.assertEqual(result.shortname, "PKO BP SA")
        self.assertEqual(fake.calls[0]["method"], "PATCH")
        self.assertEqual(fake.calls[0]["url"], "/stock/instruments/PKO/shortname")
        self.assertEqual(fake.calls[0]["params"], {"mic": "XWAR"})
        self.assertEqual(
            fake.calls[0]["json"],
            {"shortname": "PKO BP SA", "expected_shortname": "PKO"},
        )

    async def test_update_instrument_shortname_preserves_stock_error_status(self) -> None:
        client = _stock_client_with(
            _FakeAsyncHttpClient(httpx.Response(409, json={"detail": "concurrent update"}))
        )

        with self.assertRaises(StockInstrumentUpdateError) as captured:
            await client.update_instrument_shortname("XWAR", "PKO", "NEW", "OLD")

        self.assertEqual(captured.exception.status_code, 409)
        self.assertEqual(captured.exception.detail, "concurrent update")


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Wallet dependencies validate internal user identity headers")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("auth", "api-contract")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class WalletDependencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_internal_user_id_accepts_valid_uuid(self) -> None:
        user_id = uuid4()

        self.assertEqual(await get_internal_user_id(str(user_id)), user_id)

    async def test_internal_user_id_rejects_invalid_uuid(self) -> None:
        with self.assertRaises(HTTPException) as captured:
            await get_internal_user_id("not-a-uuid")

        self.assertEqual(captured.exception.status_code, 400)
        self.assertEqual(captured.exception.detail, "Invalid X-User-Id")

    async def test_app_state_dependencies_return_configured_clients(self) -> None:
        auth_client = object()
        stock_client = object()
        request = type(
            "Request",
            (),
            {"app": type("App", (), {"state": type("State", (), {})()})()},
        )()
        request.app.state.auth_client = auth_client
        request.app.state.stock_httpx = stock_client

        self.assertIs(get_auth_crypto(request), auth_client)
        self.assertIs(get_stock_client(request), stock_client)
