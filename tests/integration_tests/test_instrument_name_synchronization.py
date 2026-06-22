from datetime import datetime, timezone
from uuid import uuid4

import allure
import httpx
import psycopg
import pytest


def _stock_db_connect():
    return psycopg.connect(
        host="stock-db",
        port=5432,
        dbname="stock_test",
        user="myuser",
        password="mypassword",
    )


def _wallet_db_connect():
    return psycopg.connect(
        host="wallet-db",
        port=5432,
        dbname="Wallet_test",
        user="myuser",
        password="mypassword",
    )


@pytest.mark.integration
@pytest.mark.db
@pytest.mark.contract
@allure.epic("System Tests")
@allure.feature("Integration")
@allure.story("Instrument display names stay identical in stock quotes and wallet mirrors")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("stock", "wallet", "instruments", "financial-data", "api-contract")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Creates a quoted stock instrument without a wallet mirror, synchronizes its display "
    "name through wallet, and verifies both persisted databases plus the quote response."
)
class TestInstrumentNameSynchronization:
    def test_wallet_creates_mirror_and_updates_stock_quote_name(
        self,
        wallet_url: str,
        stock_url: str,
    ) -> None:
        suffix = uuid4().hex[:4].upper()
        mic = suffix
        symbol = f"N{suffix}"
        old_name = f"OLD {suffix}"
        new_name = f"NEW {suffix}"
        full_name = f"FULL LEGAL NAME {suffix}"

        market_response = httpx.post(
            f"{stock_url}/stock/markets",
            json={
                "mic": mic,
                "name": f"Name Sync Market {suffix}",
                "country": "PL",
                "timezone": "Europe/Warsaw",
                "active": True,
                "currency": "PLN",
            },
            timeout=10.0,
        )
        assert market_response.status_code == 201, market_response.text

        instrument_response = httpx.post(
            f"{stock_url}/stock/instruments",
            json={
                "market_mic": mic,
                "symbol": symbol,
                "shortname": old_name,
                "name": full_name,
                "type": "STOCK",
                "status": "ACTIVE",
                "currency": "PLN",
                "isin": None,
                "historical_source": None,
                "quote_source": None,
                "popularity": 0,
                "last_seen_at": None,
            },
            timeout=10.0,
        )
        assert instrument_response.status_code == 201, instrument_response.text

        with _stock_db_connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM instrument WHERE symbol = %s", (symbol,))
                instrument_id = cursor.fetchone()[0]
                now = datetime.now(timezone.utc)
                cursor.execute(
                    """
                    INSERT INTO quote_latest (
                        instrument_id, last_price, change_pct, volume,
                        last_trade_at, provider, href, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (instrument_id, "10.000", "1.00", 100, now, None, None, now),
                )

        user_response = httpx.post(
            f"{wallet_url}/wallet/sync/user",
            json={
                "username": f"ns{suffix}"[:12],
                "email": f"name-sync-{suffix.lower()}@example.com",
                "first_name": "Integration",
            },
            timeout=10.0,
        )
        assert user_response.status_code == 200, user_response.text
        user_id = user_response.json()["user_id"]

        sync_response = httpx.put(
            f"{wallet_url}/wallet/instruments/{symbol}/name",
            headers={"X-User-Id": user_id},
            json={"mic": mic, "name": new_name.lower()},
            timeout=10.0,
        )
        assert sync_response.status_code == 200, sync_response.text
        assert sync_response.json() == {
            "symbol": symbol,
            "mic": mic,
            "name": new_name,
            "created": True,
        }

        resolved_response = httpx.get(
            f"{stock_url}/stock/instruments/resolve",
            params={"mic": mic, "symbol": symbol},
            timeout=10.0,
        )
        assert resolved_response.status_code == 200, resolved_response.text
        assert resolved_response.json()["shortname"] == new_name
        assert resolved_response.json()["name"] == full_name

        quote_response = httpx.get(
            f"{stock_url}/stock/quotes/latest/bulk",
            params={"mic": mic},
            timeout=10.0,
        )
        assert quote_response.status_code == 200, quote_response.text
        assert quote_response.json()[symbol]["name"] == new_name

        with _wallet_db_connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT mic, name FROM instruments WHERE symbol = %s",
                    (symbol,),
                )
                assert cursor.fetchone() == (mic, new_name)
