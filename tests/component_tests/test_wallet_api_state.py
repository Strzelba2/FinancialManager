from __future__ import annotations

import base64
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import allure
import httpx
import psycopg
import pytest


PASSWORD = "ComponentPass123!"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _unique_user_payload(prefix: str) -> dict[str, str]:
    suffix = uuid4().hex[:8]
    return {
        "username": f"{prefix}{suffix}"[:12],
        "email": f"{prefix}.{suffix}@example.com",
        "first_name": "Component",
    }


def _sync_user(wallet_url: str, prefix: str = "u") -> dict:
    response = httpx.post(
        f"{wallet_url}/wallet/sync/user",
        json=_unique_user_payload(prefix),
        timeout=10.0,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _auth_headers(user_id: str) -> dict[str, str]:
    return {"X-User-Id": user_id}


def _register_session_crypto_user(session_url: str, fixture: dict[str, str]) -> None:
    suffix = uuid4().hex[:2]
    response = httpx.post(
        f"{session_url}/register/",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Referer": "http://next.localhost:8081/register",
            "User-Agent": BROWSER_USER_AGENT,
            "X-Original-Client-IP": f"10.221.{int(suffix, 16)}.10",
        },
        json={
            "first_name": "Component",
            "last_name": "Tester",
            "username": fixture["username"],
            "email": fixture["email"],
            "password": PASSWORD,
        },
        timeout=10.0,
    )
    assert response.status_code == 201, response.text


def _wallet_db_connect():
    return psycopg.connect(
        host="wallet-db",
        port=5432,
        dbname="Wallet_test",
        user="myuser",
        password="mypassword",
    )


def _seed_wallet_account(
    prefix: str,
    opening_balance: str = "0.00",
    currency: str = "PLN",
    account_type: str = "CURRENT",
) -> dict[str, str]:
    suffix = uuid4().hex[:8]
    username = f"{prefix}{suffix}"[:12]
    email = f"{prefix}.{suffix}@example.com"
    user_id = str(uuid4())
    wallet_id = str(uuid4())
    account_id = str(uuid4())
    now = datetime.now(timezone.utc)
    fingerprint = uuid4().bytes + uuid4().bytes

    with _wallet_db_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM banks ORDER BY name LIMIT 1")
            bank_row = cursor.fetchone()
            if bank_row is None:
                bank_id = str(uuid4())
                cursor.execute(
                    "INSERT INTO banks (id, name, shortname, bic) VALUES (%s, %s, %s, %s)",
                    (bank_id, f"Bank {suffix}", f"B{suffix[:4]}".upper(), None),
                )
            else:
                bank_id = str(bank_row[0])

            cursor.execute(
                """
                INSERT INTO users (id, created_at, updated_at, username, email, first_name)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    now,
                    now,
                    username,
                    email,
                    "Component",
                ),
            )
            cursor.execute(
                """
                INSERT INTO wallets (id, created_at, updated_at, user_id, name, currency)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (wallet_id, now, now, user_id, f"{prefix}-wallet-{suffix}", currency),
            )
            cursor.execute(
                """
                INSERT INTO deposit_accounts (
                    id, created_at, updated_at, name, account_type,
                    account_number_nonce, account_number_ct, account_number_fp,
                    iban_nonce, iban_ct, iban_fp,
                    currency, wallet_id, bank_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL, NULL, %s, %s, %s)
                """,
                (
                    account_id,
                    now,
                    now,
                    f"{prefix}-account-{suffix}",
                    account_type,
                    psycopg.Binary(b"1" * 12),
                    psycopg.Binary(f"cipher-{suffix}".encode("utf-8")),
                    psycopg.Binary(fingerprint),
                    currency,
                    wallet_id,
                    bank_id,
                ),
            )
            cursor.execute(
                """
                INSERT INTO deposit_account_balances (
                    account_id, created_at, updated_at, available, blocked
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (account_id, now, now, Decimal(opening_balance), Decimal("0.00")),
            )

    return {
        "user_id": user_id,
        "wallet_id": wallet_id,
        "account_id": account_id,
        "bank_id": bank_id,
        "currency": currency,
        "account_type": account_type,
        "username": username,
        "email": email,
    }


def _seed_brokerage_account_link(fixture: dict[str, str], currency: str = "PLN") -> str:
    brokerage_account_id = str(uuid4())
    now = datetime.now(timezone.utc)
    suffix = brokerage_account_id[:8]

    with _wallet_db_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO brokerage_accounts (
                    id, created_at, updated_at, name, wallet_id, bank_id
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    brokerage_account_id,
                    now,
                    now,
                    f"brokerage-{suffix}",
                    fixture["wallet_id"],
                    fixture["bank_id"],
                ),
            )
            cursor.execute(
                """
                INSERT INTO brokerage_deposit_links (
                    brokerage_account_id, deposit_account_id, currency
                )
                VALUES (%s, %s, %s)
                """,
                (
                    brokerage_account_id,
                    fixture["account_id"],
                    currency,
                ),
            )

    return brokerage_account_id


def _seed_brokerage_cash_account(
    fixture: dict[str, str],
    brokerage_account_id: str,
    currency: str,
    opening_balance: str = "0.00",
) -> str:
    account_id = str(uuid4())
    now = datetime.now(timezone.utc)
    suffix = account_id[:8]
    fingerprint = uuid4().bytes + uuid4().bytes

    with _wallet_db_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO deposit_accounts (
                    id, created_at, updated_at, name, account_type,
                    account_number_nonce, account_number_ct, account_number_fp,
                    iban_nonce, iban_ct, iban_fp,
                    currency, wallet_id, bank_id
                )
                VALUES (%s, %s, %s, %s, 'BROKERAGE', %s, %s, %s, NULL, NULL, NULL, %s, %s, %s)
                """,
                (
                    account_id,
                    now,
                    now,
                    f"{fixture['username']}-{currency.lower()}-{suffix}",
                    psycopg.Binary(b"2" * 12),
                    psycopg.Binary(f"cipher-{currency.lower()}-{suffix}".encode("utf-8")),
                    psycopg.Binary(fingerprint),
                    currency,
                    fixture["wallet_id"],
                    fixture["bank_id"],
                ),
            )
            cursor.execute(
                """
                INSERT INTO deposit_account_balances (
                    account_id, created_at, updated_at, available, blocked
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (account_id, now, now, Decimal(opening_balance), Decimal("0.00")),
            )
            cursor.execute(
                """
                INSERT INTO brokerage_deposit_links (
                    brokerage_account_id, deposit_account_id, currency
                )
                VALUES (%s, %s, %s)
                """,
                (brokerage_account_id, account_id, currency),
            )

    return account_id


def _transaction_row(
    date: str,
    amount: str,
    amount_after: str,
    description: str,
    capital_gain_kind: str | None = None,
) -> dict[str, str | None]:
    row = {
        "date": date,
        "amount": amount,
        "amount_after": amount_after,
        "description": description,
    }
    if capital_gain_kind is not None:
        row["capital_gain_kind"] = capital_gain_kind
    return row


def _create_transactions(
    wallet_url: str,
    user_id: str,
    account_id: str,
    rows: list[dict[str, str | None]],
) -> dict:
    response = httpx.post(
        f"{wallet_url}/wallet/transactions/create/rebalance",
        headers=_auth_headers(user_id),
        json={"account_id": account_id, "transactions": rows},
        timeout=10.0,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _get_account_balance(account_id: str) -> Decimal:
    with _wallet_db_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT available FROM deposit_account_balances WHERE account_id = %s",
                (account_id,),
            )
            row = cursor.fetchone()
            assert row is not None
            return Decimal(str(row[0]))


def _sync_existing_wallet_user(wallet_url: str, fixture: dict[str, str]) -> dict:
    response = httpx.post(
        f"{wallet_url}/wallet/sync/user",
        json={
            "username": fixture["username"],
            "email": fixture["email"],
            "first_name": "Component",
        },
        timeout=10.0,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _get_deposit_monthly_snapshot_available(account_id: str, month_key: str) -> Decimal:
    with _wallet_db_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT available
                  FROM deposit_account_monthly_snapshots
                 WHERE account_id = %s
                   AND month_key = %s
                """,
                (account_id, month_key),
            )
            row = cursor.fetchone()
            assert row is not None
            return Decimal(str(row[0]))


def _ensure_cpi_daily_candle(stock_url: str, quote_day: date, close: Decimal) -> str:
    market_response = httpx.post(
        f"{stock_url}/stock/markets",
        json={
            "mic": "MCRO",
            "name": "Macro Indicators",
            "country": "PL",
            "timezone": "Europe/Warsaw",
            "active": True,
            "currency": "PLN",
        },
        timeout=10.0,
    )
    assert market_response.status_code in {201, 409}, market_response.text

    instrument_response = httpx.post(
        f"{stock_url}/stock/instruments",
        json={
            "market_mic": "MCRO",
            "symbol": "CPIYPL.M",
            "shortname": "CPIYPL.M",
            "name": "Poland CPI YoY",
            "type": "MACRO",
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
    assert instrument_response.status_code in {201, 409}, instrument_response.text

    csv = "\n".join(
        [
            "Date,Open,High,Low,Close,Volume",
            f"{quote_day.isoformat()},{close},{close},{close},{close},0",
        ]
    )
    content = base64.b64encode(csv.encode("utf-8")).decode("ascii")
    import_response = httpx.post(
        f"{stock_url}/stock/instruments/CPIYPL.M/candles/daily/import_csv",
        json={
            "filename": "cpi-wallet-dashboard.csv",
            "content_b64": content,
            "return_all": False,
            "include_items": False,
        },
        timeout=10.0,
    )
    assert import_response.status_code == 200, import_response.text
    return quote_day.strftime("%Y-%m")


@pytest.mark.component
@pytest.mark.db
@allure.epic("System Tests")
@allure.feature("Component")
@allure.story("Wallet API persists user-owned wallets and enforces ownership")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "api-contract", "database", "ownership")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Exercises wallet public HTTP boundaries against the test database: user sync, "
    "wallet creation, duplicate-name rejection, list persistence, and cross-user denial."
)
class TestWalletApiPersistedState:
    def test_wallet_create_is_visible_in_later_user_sync_response(self, wallet_url: str) -> None:
        user_payload = _unique_user_payload("wa")
        user_response = httpx.post(
            f"{wallet_url}/wallet/sync/user",
            json=user_payload,
            timeout=10.0,
        )
        assert user_response.status_code == 200, user_response.text
        user = user_response.json()
        user_id = user["user_id"]

        create_response = httpx.post(
            f"{wallet_url}/wallet/create/wallet",
            headers=_auth_headers(user_id),
            json={"name": "  Main Component Wallet  ", "currency": "PLN"},
            timeout=10.0,
        )

        assert create_response.status_code == 200, create_response.text
        created_wallet = create_response.json()
        assert created_wallet["name"] == "Main Component Wallet"

        sync_again = httpx.post(
            f"{wallet_url}/wallet/sync/user",
            json=user_payload,
            timeout=10.0,
        )
        assert sync_again.status_code == 200, sync_again.text
        wallets = sync_again.json().get("wallets", [])

        original_user_response = httpx.get(
            f"{wallet_url}/wallet/accounts",
            headers=_auth_headers(user_id),
            timeout=10.0,
        )
        assert original_user_response.status_code == 200, original_user_response.text
        assert created_wallet["id"]
        assert any(wallet["id"] == created_wallet["id"] for wallet in wallets)

        delete_response = httpx.delete(
            f"{wallet_url}/wallet/delete/{created_wallet['id']}",
            headers=_auth_headers(user_id),
            timeout=10.0,
        )
        assert delete_response.status_code == 204, delete_response.text

    def test_duplicate_wallet_name_is_rejected_for_same_user(self, wallet_url: str) -> None:
        user = _sync_user(wallet_url, "wd")
        headers = _auth_headers(user["user_id"])
        payload = {"name": "Duplicate Wallet", "currency": "PLN"}

        first = httpx.post(f"{wallet_url}/wallet/create/wallet", headers=headers, json=payload, timeout=10.0)
        second = httpx.post(f"{wallet_url}/wallet/create/wallet", headers=headers, json=payload, timeout=10.0)

        assert first.status_code == 200, first.text
        assert second.status_code == 400
        assert "already exists" in second.text

    def test_cross_user_wallet_delete_is_denied(self, wallet_url: str) -> None:
        owner = _sync_user(wallet_url, "wo")
        other = _sync_user(wallet_url, "wx")

        create_response = httpx.post(
            f"{wallet_url}/wallet/create/wallet",
            headers=_auth_headers(owner["user_id"]),
            json={"name": "Owner Wallet", "currency": "PLN"},
            timeout=10.0,
        )
        assert create_response.status_code == 200, create_response.text

        denied = httpx.delete(
            f"{wallet_url}/wallet/delete/{create_response.json()['id']}",
            headers=_auth_headers(other["user_id"]),
            timeout=10.0,
        )

        assert denied.status_code == 404
        assert "Wallet not found" in denied.text


@pytest.mark.component
@pytest.mark.db
@allure.epic("System Tests")
@allure.feature("Component")
@allure.story("Wallet monthly snapshots feed dashboard nominal and real assets")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "snapshots", "dashboard", "cpi", "financial-data", "api-contract", "ownership")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Exercises the persisted API path from /wallet/snapshots/monthly to /wallet/sync/user. "
    "The test seeds a local CPI candle in the stock test service, stores a wallet deposit "
    "snapshot, verifies assets_8m_total and cpi_8m, and checks cross-user isolation."
)
class TestWalletMonthlySnapshotDashboardApi:
    def test_snapshot_is_persisted_and_returned_with_cpi_without_cross_user_leakage(
        self,
        wallet_url: str,
        stock_url: str,
    ) -> None:
        quote_day = datetime.now(timezone.utc).date() - timedelta(days=1)
        month_key = _ensure_cpi_daily_candle(stock_url, quote_day=quote_day, close=Decimal("3.10"))
        owner = _seed_wallet_account("snapown", opening_balance="1234.50", currency="PLN")
        other = _seed_wallet_account("snapoth", opening_balance="9999.00", currency="PLN")

        snapshot_response = httpx.post(
            f"{wallet_url}/wallet/snapshots/monthly",
            headers=_auth_headers(owner["user_id"]),
            json={"month_key": month_key, "currency_rate": {}},
            timeout=10.0,
        )

        assert snapshot_response.status_code == 200, snapshot_response.text
        snapshot = snapshot_response.json()
        assert snapshot["ok"] is True
        assert snapshot["month_key"] == month_key
        assert snapshot["dep_upserted"] == 1
        assert _get_deposit_monthly_snapshot_available(owner["account_id"], month_key) == Decimal("1234.50")

        owner_sync = _sync_existing_wallet_user(wallet_url, owner)
        assets = owner_sync["assets_8m_total"]
        assert month_key in assets["months"]
        month_idx = assets["months"].index(month_key)
        assert Decimal(str(assets["values"][month_idx])) == Decimal("1234.5")
        assert owner_sync["cpi_8m"]["index_by_month"][month_key] == pytest.approx(3.10)

        other_sync = _sync_existing_wallet_user(wallet_url, other)
        other_assets = other_sync["assets_8m_total"]
        assert month_key in other_assets["months"]
        other_month_idx = other_assets["months"].index(month_key)
        assert Decimal(str(other_assets["values"][other_month_idx])) == Decimal("0.0")


@pytest.mark.component
@pytest.mark.db
@allure.epic("System Tests")
@allure.feature("Component")
@allure.story("Wallet goals API persists annual money targets and enforces ownership")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "goals", "money", "financial-data", "api-contract", "ownership")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Exercises public wallet goal endpoints against the test database. "
    "Covers capital gain target persistence, update semantics, validation, and cross-user denial."
)
class TestWalletGoalsApi:
    @staticmethod
    def _payload(wallet_id: str, capital_gain_target_year: str = "60000.00") -> dict[str, object]:
        return {
            "wallet_id": wallet_id,
            "year": 2026,
            "rev_target_year": "200000.00",
            "exp_budget_year": "90000.00",
            "capital_gain_target_year": capital_gain_target_year,
            "currency": "PLN",
        }

    def test_upsert_persists_capital_gain_target_and_list_returns_it(self, wallet_url: str) -> None:
        fixture = _seed_wallet_account("goal", opening_balance="0.00", currency="PLN")
        headers = _auth_headers(fixture["user_id"])

        create_response = httpx.post(
            f"{wallet_url}/wallet/goals/upsert",
            headers=headers,
            json=self._payload(fixture["wallet_id"]),
            timeout=10.0,
        )

        assert create_response.status_code == 200, create_response.text
        created = create_response.json()
        assert Decimal(str(created["rev_target_year"])) == Decimal("200000.00")
        assert Decimal(str(created["exp_budget_year"])) == Decimal("90000.00")
        assert Decimal(str(created["capital_gain_target_year"])) == Decimal("60000.00")

        update_payload = self._payload(fixture["wallet_id"], capital_gain_target_year="75000.00")
        update_payload["rev_target_year"] = "210000.00"
        update_response = httpx.post(
            f"{wallet_url}/wallet/goals/upsert",
            headers=headers,
            json=update_payload,
            timeout=10.0,
        )

        assert update_response.status_code == 200, update_response.text
        updated = update_response.json()
        assert updated["id"] == created["id"]
        assert Decimal(str(updated["rev_target_year"])) == Decimal("210000.00")
        assert Decimal(str(updated["capital_gain_target_year"])) == Decimal("75000.00")

        list_response = httpx.get(
            f"{wallet_url}/wallet/{fixture['wallet_id']}/goals/all",
            headers=headers,
            timeout=10.0,
        )

        assert list_response.status_code == 200, list_response.text
        goals = list_response.json()
        assert len(goals) == 1
        assert goals[0]["id"] == created["id"]
        assert Decimal(str(goals[0]["capital_gain_target_year"])) == Decimal("75000.00")

    def test_negative_capital_gain_target_is_rejected_without_persisting(self, wallet_url: str) -> None:
        fixture = _seed_wallet_account("goalneg", opening_balance="0.00", currency="PLN")
        headers = _auth_headers(fixture["user_id"])

        rejected = httpx.post(
            f"{wallet_url}/wallet/goals/upsert",
            headers=headers,
            json=self._payload(fixture["wallet_id"], capital_gain_target_year="-1.00"),
            timeout=10.0,
        )

        assert rejected.status_code == 422, rejected.text

        list_response = httpx.get(
            f"{wallet_url}/wallet/{fixture['wallet_id']}/goals/all",
            headers=headers,
            timeout=10.0,
        )

        assert list_response.status_code == 200, list_response.text
        assert list_response.json() == []

    def test_cross_user_goal_reads_and_writes_are_denied(self, wallet_url: str) -> None:
        owner = _seed_wallet_account("goalown", opening_balance="0.00", currency="PLN")
        other = _seed_wallet_account("goaloth", opening_balance="0.00", currency="PLN")

        denied_list = httpx.get(
            f"{wallet_url}/wallet/{owner['wallet_id']}/goals/all",
            headers=_auth_headers(other["user_id"]),
            timeout=10.0,
        )
        denied_upsert = httpx.post(
            f"{wallet_url}/wallet/goals/upsert",
            headers=_auth_headers(other["user_id"]),
            json=self._payload(owner["wallet_id"]),
            timeout=10.0,
        )

        assert denied_list.status_code == 404
        assert "Wallet not found" in denied_list.text
        assert denied_upsert.status_code == 404
        assert "Wallet not found" in denied_upsert.text


@pytest.mark.component
@pytest.mark.db
@allure.epic("System Tests")
@allure.feature("Component")
@allure.story("Wallet favorites API persists lists and prevents duplicate names")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "favorites", "api-contract", "database")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class TestWalletFavoritesApi:
    def test_favorite_list_create_duplicate_rejection_list_and_delete_flow(self, wallet_url: str) -> None:
        user = _sync_user(wallet_url, "fav")
        headers = _auth_headers(user["user_id"])

        first = httpx.post(
            f"{wallet_url}/users/favorites/lists",
            headers=headers,
            json={"name": "My watchlist", "description": "Tracked instruments"},
            timeout=10.0,
        )
        duplicate = httpx.post(
            f"{wallet_url}/users/favorites/lists",
            headers=headers,
            json={"name": "My watchlist", "description": "Different description"},
            timeout=10.0,
        )
        listed = httpx.get(f"{wallet_url}/users/favorites/lists", headers=headers, timeout=10.0)

        assert first.status_code == 200, first.text
        assert duplicate.status_code == 409
        assert "already exists" in duplicate.text
        assert listed.status_code == 200, listed.text
        assert [item["name"] for item in listed.json()] == ["My watchlist"]

        deleted = httpx.delete(
            f"{wallet_url}/users/favorites/lists/{first.json()['id']}",
            headers=headers,
            timeout=10.0,
        )
        after_delete = httpx.get(f"{wallet_url}/users/favorites/lists", headers=headers, timeout=10.0)

        assert deleted.status_code == 200, deleted.text
        assert deleted.json() == {"ok": True}
        assert after_delete.status_code == 200
        assert after_delete.json() == []

    def test_cross_user_favorite_list_delete_is_denied(self, wallet_url: str) -> None:
        owner = _sync_user(wallet_url, "fao")
        other = _sync_user(wallet_url, "fax")

        created = httpx.post(
            f"{wallet_url}/users/favorites/lists",
            headers=_auth_headers(owner["user_id"]),
            json={"name": "Owner only", "description": None},
            timeout=10.0,
        )
        assert created.status_code == 200, created.text

        denied = httpx.delete(
            f"{wallet_url}/users/favorites/lists/{created.json()['id']}",
            headers=_auth_headers(other["user_id"]),
            timeout=10.0,
        )

        assert denied.status_code == 404
        assert "Favorite list not found" in denied.text


@pytest.mark.component
@pytest.mark.db
@allure.epic("System Tests")
@allure.feature("Component")
@allure.story("Wallet transaction API preserves lifecycle and financial state")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "transactions", "api-contract", "money", "financial-data", "ownership")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Exercises public wallet transaction endpoints against the isolated test database. "
    "The scenarios make opening balance, cash effect, final balance, category/status "
    "editing, filters, ownership, and rebalance behavior explicit."
)
class TestWalletTransactionApiLifecycle:
    def test_create_rebalance_persists_financial_state_without_transaction_classification(self, wallet_url: str) -> None:
        fixture = _seed_wallet_account("txcr", opening_balance="0.00", currency="PLN")

        summary = _create_transactions(
            wallet_url,
            fixture["user_id"],
            fixture["account_id"],
            [
                _transaction_row(
                    "2026-05-01T09:00:00+00:00",
                    "100.00",
                    "100.00",
                    "Salary May",
                ),
                _transaction_row(
                    "2026-05-02T09:00:00+00:00",
                    "-25.00",
                    "75.00",
                    "Grocery basket",
                ),
            ],
        )

        assert summary["created"] == 2
        assert Decimal(str(summary["final_balance"])) == Decimal("75.00")
        assert len(summary["transaction_ids"]) == 2
        assert _get_account_balance(fixture["account_id"]) == Decimal("75.00")

        listed = httpx.get(
            f"{wallet_url}/wallet/transactions",
            headers=_auth_headers(fixture["user_id"]),
            params={
                "account_id": fixture["account_id"],
                "q": "Grocery",
                "date_from": "2026-05-01",
                "date_to": "2026-05-03",
            },
            timeout=10.0,
        )

        assert listed.status_code == 200, listed.text
        page = listed.json()
        assert page["total"] == 1
        assert {ccy: Decimal(str(value)) for ccy, value in page["sum_by_ccy"].items()} == {"PLN": Decimal("-25.00")}
        row = page["items"][0]
        assert row["description"] == "Grocery basket"
        assert Decimal(str(row["amount"])) == Decimal("-25.00")
        assert Decimal(str(row["balance_before"])) == Decimal("100.00")
        assert Decimal(str(row["balance_after"])) == Decimal("75.00")
        assert row["category"] is None
        assert row["status"] is None
        assert row["ccy"] == "PLN"

    def test_create_rejects_invalid_payloads_without_persisting(self, wallet_url: str) -> None:
        fixture = _seed_wallet_account("txbad", opening_balance="10.00", currency="PLN")
        unknown_account_id = str(uuid4())

        empty_rows = httpx.post(
            f"{wallet_url}/wallet/transactions/create/rebalance",
            headers=_auth_headers(fixture["user_id"]),
            json={"account_id": fixture["account_id"], "transactions": []},
            timeout=10.0,
        )
        unknown_account = httpx.post(
            f"{wallet_url}/wallet/transactions/create/rebalance",
            headers=_auth_headers(fixture["user_id"]),
            json={
                "account_id": unknown_account_id,
                "transactions": [
                    _transaction_row(
                        "2026-05-01T09:00:00+00:00",
                        "5.00",
                        "15.00",
                        "Unknown account transaction",
                    )
                ],
            },
            timeout=10.0,
        )
        mismatch = httpx.post(
            f"{wallet_url}/wallet/transactions/create/rebalance",
            headers=_auth_headers(fixture["user_id"]),
            json={
                "account_id": fixture["account_id"],
                "transactions": [
                    _transaction_row(
                        "2026-05-01T09:00:00+00:00",
                        "5.00",
                        "99.00",
                        "Mismatch transaction",
                    )
                ],
            },
            timeout=10.0,
        )
        negative = httpx.post(
            f"{wallet_url}/wallet/transactions/create/rebalance",
            headers=_auth_headers(fixture["user_id"]),
            json={
                "account_id": fixture["account_id"],
                "transactions": [
                    _transaction_row(
                        "2026-05-02T09:00:00+00:00",
                        "-20.00",
                        "-10.00",
                        "Overdraft transaction",
                    )
                ],
            },
            timeout=10.0,
        )
        negative_then_recovered = httpx.post(
            f"{wallet_url}/wallet/transactions/create/rebalance",
            headers=_auth_headers(fixture["user_id"]),
            json={
                "account_id": fixture["account_id"],
                "transactions": [
                    _transaction_row(
                        "2026-05-03T09:00:00+00:00",
                        "-20.00",
                        "-10.00",
                        "Temporary overdraft",
                    ),
                    _transaction_row(
                        "2026-05-04T09:00:00+00:00",
                        "30.00",
                        "20.00",
                        "Recovered balance",
                    ),
                ],
            },
            timeout=10.0,
        )

        assert empty_rows.status_code == 422
        assert unknown_account.status_code == 404
        assert mismatch.status_code == 422
        assert negative.status_code == 422
        assert negative_then_recovered.status_code == 422
        assert _get_account_balance(fixture["account_id"]) == Decimal("10.00")

    def test_credit_account_create_and_delete_allow_negative_balance(self, wallet_url: str) -> None:
        fixture = _seed_wallet_account(
            "txcred",
            opening_balance="0.00",
            currency="PLN",
            account_type="CREDIT",
        )

        summary = _create_transactions(
            wallet_url,
            fixture["user_id"],
            fixture["account_id"],
            [
                _transaction_row("2026-05-03T09:00:00+00:00", "50.00", "50.00", "Credit card payment"),
                _transaction_row("2026-05-04T09:00:00+00:00", "-150.00", "-100.00", "Credit card purchase"),
            ],
        )
        payment_id, purchase_id = summary["transaction_ids"]

        assert summary["created"] == 2
        assert Decimal(str(summary["final_balance"])) == Decimal("-100.00")
        assert _get_account_balance(fixture["account_id"]) == Decimal("-100.00")

        deleted = httpx.delete(
            f"{wallet_url}/wallet/transactions/{payment_id}",
            headers=_auth_headers(fixture["user_id"]),
            timeout=10.0,
        )
        listed = httpx.get(
            f"{wallet_url}/wallet/transactions",
            headers=_auth_headers(fixture["user_id"]),
            params={"account_id": fixture["account_id"], "size": 10},
            timeout=10.0,
        )

        assert deleted.status_code == 200, deleted.text
        assert deleted.json() == {"ok": True}
        assert _get_account_balance(fixture["account_id"]) == Decimal("-150.00")

        rows_by_id = {row["id"]: row for row in listed.json()["items"]}
        assert payment_id not in rows_by_id
        assert Decimal(str(rows_by_id[purchase_id]["balance_before"])) == Decimal("0.00")
        assert Decimal(str(rows_by_id[purchase_id]["balance_after"])) == Decimal("-150.00")

    def test_same_timestamp_rows_receive_unique_ordered_datetimes(self, wallet_url: str) -> None:
        fixture = _seed_wallet_account("txsame", opening_balance="0.00", currency="PLN")

        summary = _create_transactions(
            wallet_url,
            fixture["user_id"],
            fixture["account_id"],
            [
                _transaction_row("2026-05-04T12:00:00+00:00", "10.00", "10.00", "First same-time"),
                _transaction_row("2026-05-04T12:00:00+00:00", "20.00", "30.00", "Second same-time"),
            ],
        )
        listed = httpx.get(
            f"{wallet_url}/wallet/transactions",
            headers=_auth_headers(fixture["user_id"]),
            params={"account_id": fixture["account_id"], "size": 10},
            timeout=10.0,
        )

        assert summary["created"] == 2
        assert listed.status_code == 200, listed.text
        rows = listed.json()["items"]
        assert len(rows) == 2
        assert rows[0]["date_transaction"] != rows[1]["date_transaction"]
        assert [row["description"] for row in rows] == ["Second same-time", "First same-time"]
        assert [Decimal(str(row["balance_after"])) for row in reversed(rows)] == [
            Decimal("10.00"),
            Decimal("30.00"),
        ]

    def test_create_rebalance_rejects_replayed_identical_import_without_balance_change(self, wallet_url: str) -> None:
        fixture = _seed_wallet_account("txreplay", opening_balance="0.00", currency="PLN")
        payload = {
            "account_id": fixture["account_id"],
            "transactions": [
                _transaction_row(
                    "2026-05-05T12:00:00+00:00",
                    "10.00",
                    "10.00",
                    "Replay-protected import",
                )
            ],
        }

        first = httpx.post(
            f"{wallet_url}/wallet/transactions/create/rebalance",
            headers=_auth_headers(fixture["user_id"]),
            json=payload,
            timeout=10.0,
        )
        replay = httpx.post(
            f"{wallet_url}/wallet/transactions/create/rebalance",
            headers=_auth_headers(fixture["user_id"]),
            json=payload,
            timeout=10.0,
        )
        listed = httpx.get(
            f"{wallet_url}/wallet/transactions",
            headers=_auth_headers(fixture["user_id"]),
            params={"account_id": fixture["account_id"], "size": 10},
            timeout=10.0,
        )

        assert first.status_code == 201, first.text
        assert replay.status_code == 409, replay.text
        assert listed.status_code == 200, listed.text
        assert listed.json()["total"] == 1
        assert _get_account_balance(fixture["account_id"]) == Decimal("10.00")

    def test_create_rebalance_imports_descending_velo_same_day_balance_loop(self, wallet_url: str) -> None:
        fixture = _seed_wallet_account("txvelo", opening_balance="624.79", currency="PLN")

        summary = _create_transactions(
            wallet_url,
            fixture["user_id"],
            fixture["account_id"],
            [
                _transaction_row("2025-11-25T00:00:00+00:00", "5.00", "639.79", "Newer visible row"),
                _transaction_row("2025-11-23T00:00:00+00:00", "-98000.00", "634.79", "Return later"),
                _transaction_row("2025-11-23T00:00:00+00:00", "98000.00", "98634.79", "Return earlier"),
                _transaction_row("2025-11-23T00:00:00+00:00", "-50000.00", "634.79", "Second withdrawal"),
                _transaction_row("2025-11-23T00:00:00+00:00", "-50000.00", "50634.79", "First withdrawal"),
                _transaction_row("2025-11-23T00:00:00+00:00", "100000.00", "100634.79", "Deposit"),
                _transaction_row("2025-11-20T00:00:00+00:00", "10.00", "634.79", "Older visible row"),
            ],
        )

        listed = httpx.get(
            f"{wallet_url}/wallet/transactions",
            headers=_auth_headers(fixture["user_id"]),
            params={"account_id": fixture["account_id"], "size": 10},
            timeout=10.0,
        )

        assert summary["created"] == 7
        assert Decimal(str(summary["final_balance"])) == Decimal("639.79")
        assert _get_account_balance(fixture["account_id"]) == Decimal("639.79")
        assert listed.status_code == 200, listed.text

        rows_by_description = {row["description"]: row for row in listed.json()["items"]}
        expected_balances = {
            "Older visible row": (Decimal("624.79"), Decimal("634.79")),
            "Deposit": (Decimal("634.79"), Decimal("100634.79")),
            "First withdrawal": (Decimal("100634.79"), Decimal("50634.79")),
            "Second withdrawal": (Decimal("50634.79"), Decimal("634.79")),
            "Return earlier": (Decimal("634.79"), Decimal("98634.79")),
            "Return later": (Decimal("98634.79"), Decimal("634.79")),
            "Newer visible row": (Decimal("634.79"), Decimal("639.79")),
        }
        for description, (before, after) in expected_balances.items():
            row = rows_by_description[description]
            assert Decimal(str(row["balance_before"])) == before
            assert Decimal(str(row["balance_after"])) == after

    def test_batch_update_sets_and_clears_category_status(self, wallet_url: str) -> None:
        fixture = _seed_wallet_account("txupd", opening_balance="20.00", currency="PLN")
        summary = _create_transactions(
            wallet_url,
            fixture["user_id"],
            fixture["account_id"],
            [_transaction_row("2026-05-05T09:00:00+00:00", "-12.50", "7.50", "Original update row")],
        )
        transaction_id = summary["transaction_ids"][0]

        update = httpx.patch(
            f"{wallet_url}/wallet/transactions/batch",
            headers=_auth_headers(fixture["user_id"]),
            json={
                "items": [
                    {
                        "id": transaction_id,
                        "description": "Updated groceries",
                        "category": "FOOD",
                        "status": "EXPENSE",
                    }
                ]
            },
            timeout=10.0,
        )
        after_update = httpx.get(
            f"{wallet_url}/wallet/transactions",
            headers=_auth_headers(fixture["user_id"]),
            params={"q": "Updated groceries"},
            timeout=10.0,
        )
        after_update_filtered = httpx.get(
            f"{wallet_url}/wallet/transactions",
            headers=_auth_headers(fixture["user_id"]),
            params={
                "q": "Updated groceries",
                "category": "FOOD",
                "status": "EXPENSE",
            },
            timeout=10.0,
        )
        clear = httpx.patch(
            f"{wallet_url}/wallet/transactions/batch",
            headers=_auth_headers(fixture["user_id"]),
            json={"items": [{"id": transaction_id, "category": None, "status": None}]},
            timeout=10.0,
        )
        after_clear = httpx.get(
            f"{wallet_url}/wallet/transactions",
            headers=_auth_headers(fixture["user_id"]),
            params={"q": "Updated groceries"},
            timeout=10.0,
        )

        assert update.status_code == 200, update.text
        assert update.json() == {"updated": 1, "failed": []}
        updated_row = after_update.json()["items"][0]
        assert updated_row["category"] == "FOOD"
        assert updated_row["status"] == "EXPENSE"
        assert after_update_filtered.status_code == 200, after_update_filtered.text
        assert after_update_filtered.json()["total"] == 1
        assert clear.status_code == 200, clear.text
        assert clear.json() == {"updated": 1, "failed": []}
        cleared_row = after_clear.json()["items"][0]
        assert cleared_row["category"] is None
        assert cleared_row["status"] is None

    def test_batch_update_rejects_empty_batch_and_skips_cross_user_transaction(self, wallet_url: str) -> None:
        owner = _seed_wallet_account("txown", opening_balance="0.00", currency="PLN")
        other = _seed_wallet_account("txoth", opening_balance="0.00", currency="PLN")
        summary = _create_transactions(
            wallet_url,
            owner["user_id"],
            owner["account_id"],
            [_transaction_row("2026-05-06T09:00:00+00:00", "40.00", "40.00", "Owner only row")],
        )
        transaction_id = summary["transaction_ids"][0]

        empty = httpx.patch(
            f"{wallet_url}/wallet/transactions/batch",
            headers=_auth_headers(owner["user_id"]),
            json={"items": []},
            timeout=10.0,
        )
        denied = httpx.patch(
            f"{wallet_url}/wallet/transactions/batch",
            headers=_auth_headers(other["user_id"]),
            json={"items": [{"id": transaction_id, "description": "Cross-user changed"}]},
            timeout=10.0,
        )
        owner_view = httpx.get(
            f"{wallet_url}/wallet/transactions",
            headers=_auth_headers(owner["user_id"]),
            params={"q": "Owner only row"},
            timeout=10.0,
        )

        assert empty.status_code == 422
        assert denied.status_code == 200, denied.text
        assert denied.json() == {"updated": 0, "failed": []}
        assert owner_view.status_code == 200, owner_view.text
        assert owner_view.json()["items"][0]["description"] == "Owner only row"

    def test_batch_update_processes_multiple_transactions_in_one_request(self, wallet_url: str) -> None:
        fixture = _seed_wallet_account("txmulti", opening_balance="0.00", currency="PLN")
        summary = _create_transactions(
            wallet_url,
            fixture["user_id"],
            fixture["account_id"],
            [
                _transaction_row("2026-06-25T09:00:00+00:00", "50.00", "50.00", "First tx"),
                _transaction_row("2026-06-26T09:00:00+00:00", "-20.00", "30.00", "Second tx"),
            ],
        )
        first_id, second_id = summary["transaction_ids"]

        update = httpx.patch(
            f"{wallet_url}/wallet/transactions/batch",
            headers=_auth_headers(fixture["user_id"]),
            json={
                "items": [
                    {"id": first_id, "category": "INCOME", "status": "INCOME"},
                    {"id": second_id, "category": "FOOD", "status": "EXPENSE"},
                ]
            },
            timeout=10.0,
        )
        listed = httpx.get(
            f"{wallet_url}/wallet/transactions",
            headers=_auth_headers(fixture["user_id"]),
            params={"account_id": fixture["account_id"]},
            timeout=10.0,
        )

        assert update.status_code == 200, update.text
        assert update.json() == {"updated": 2, "failed": []}
        rows_by_id = {row["id"]: row for row in listed.json()["items"]}
        assert rows_by_id[first_id]["category"] == "INCOME"
        assert rows_by_id[first_id]["status"] == "INCOME"
        assert rows_by_id[second_id]["category"] == "FOOD"
        assert rows_by_id[second_id]["status"] == "EXPENSE"

    def test_batch_update_description_without_changing_category_or_status(self, wallet_url: str) -> None:
        fixture = _seed_wallet_account("txdesc", opening_balance="50.00", currency="PLN")
        summary = _create_transactions(
            wallet_url,
            fixture["user_id"],
            fixture["account_id"],
            [_transaction_row("2026-06-27T09:00:00+00:00", "10.00", "60.00", "Original description")],
        )
        tx_id = summary["transaction_ids"][0]

        httpx.patch(
            f"{wallet_url}/wallet/transactions/batch",
            headers=_auth_headers(fixture["user_id"]),
            json={"items": [{"id": tx_id, "category": "FOOD", "status": "EXPENSE"}]},
            timeout=10.0,
        ).raise_for_status()

        desc_update = httpx.patch(
            f"{wallet_url}/wallet/transactions/batch",
            headers=_auth_headers(fixture["user_id"]),
            json={"items": [{"id": tx_id, "description": "Updated description"}]},
            timeout=10.0,
        )
        after = httpx.get(
            f"{wallet_url}/wallet/transactions",
            headers=_auth_headers(fixture["user_id"]),
            params={"account_id": fixture["account_id"]},
            timeout=10.0,
        )

        assert desc_update.status_code == 200, desc_update.text
        assert desc_update.json() == {"updated": 1, "failed": []}
        row = after.json()["items"][0]
        assert row["description"] == "Updated description"
        assert row["category"] == "FOOD"
        assert row["status"] == "EXPENSE"

    def test_batch_update_rejects_financial_field_changes_without_mutating_balance_chain(self, wallet_url: str) -> None:
        fixture = _seed_wallet_account("tximmutable", opening_balance="20.00", currency="PLN")
        summary = _create_transactions(
            wallet_url,
            fixture["user_id"],
            fixture["account_id"],
            [_transaction_row("2026-05-06T10:00:00+00:00", "-12.50", "7.50", "Immutable financial row")],
        )
        transaction_id = summary["transaction_ids"][0]

        rejected = httpx.patch(
            f"{wallet_url}/wallet/transactions/batch",
            headers=_auth_headers(fixture["user_id"]),
            json={
                "items": [
                    {
                        "id": transaction_id,
                        "amount": "-120.00",
                        "balance_before": "20.00",
                        "balance_after": "-100.00",
                    }
                ]
            },
            timeout=10.0,
        )
        listed = httpx.get(
            f"{wallet_url}/wallet/transactions",
            headers=_auth_headers(fixture["user_id"]),
            params={"account_id": fixture["account_id"], "size": 10},
            timeout=10.0,
        )

        assert rejected.status_code == 422, rejected.text
        assert _get_account_balance(fixture["account_id"]) == Decimal("7.50")
        assert listed.status_code == 200, listed.text
        row = listed.json()["items"][0]
        assert Decimal(str(row["amount"])) == Decimal("-12.50")
        assert Decimal(str(row["balance_before"])) == Decimal("20.00")
        assert Decimal(str(row["balance_after"])) == Decimal("7.50")

    def test_delete_rebalances_middle_transaction_and_denies_missing_or_cross_user_delete(self, wallet_url: str) -> None:
        owner = _seed_wallet_account("txdel", opening_balance="0.00", currency="PLN")
        other = _seed_wallet_account("txdx", opening_balance="0.00", currency="PLN")
        summary = _create_transactions(
            wallet_url,
            owner["user_id"],
            owner["account_id"],
            [
                _transaction_row("2026-05-07T09:00:00+00:00", "100.00", "100.00", "Opening transfer"),
                _transaction_row("2026-05-08T09:00:00+00:00", "-30.00", "70.00", "Middle grocery"),
                _transaction_row("2026-05-09T09:00:00+00:00", "20.00", "90.00", "Later refund"),
            ],
        )
        first_id, middle_id, last_id = summary["transaction_ids"]

        cross_user = httpx.delete(
            f"{wallet_url}/wallet/transactions/{first_id}",
            headers=_auth_headers(other["user_id"]),
            timeout=10.0,
        )
        missing = httpx.delete(
            f"{wallet_url}/wallet/transactions/{uuid4()}",
            headers=_auth_headers(owner["user_id"]),
            timeout=10.0,
        )
        deleted = httpx.delete(
            f"{wallet_url}/wallet/transactions/{middle_id}",
            headers=_auth_headers(owner["user_id"]),
            timeout=10.0,
        )
        listed = httpx.get(
            f"{wallet_url}/wallet/transactions",
            headers=_auth_headers(owner["user_id"]),
            params={"account_id": owner["account_id"], "size": 10},
            timeout=10.0,
        )

        assert cross_user.status_code == 404
        assert missing.status_code == 404
        assert deleted.status_code == 200, deleted.text
        assert deleted.json() == {"ok": True}
        assert _get_account_balance(owner["account_id"]) == Decimal("120.00")

        rows_by_id = {row["id"]: row for row in listed.json()["items"]}
        assert middle_id not in rows_by_id
        assert Decimal(str(rows_by_id[first_id]["balance_before"])) == Decimal("0.00")
        assert Decimal(str(rows_by_id[first_id]["balance_after"])) == Decimal("100.00")
        assert Decimal(str(rows_by_id[last_id]["balance_before"])) == Decimal("100.00")
        assert Decimal(str(rows_by_id[last_id]["balance_after"])) == Decimal("120.00")

    def test_delete_that_would_make_current_account_negative_returns_400(self, wallet_url: str) -> None:
        fixture = _seed_wallet_account("txdelneg", opening_balance="100.00", currency="PLN")
        summary = _create_transactions(
            wallet_url,
            fixture["user_id"],
            fixture["account_id"],
            [
                _transaction_row("2026-07-01T09:00:00+00:00", "50.00", "150.00", "Income"),
                _transaction_row("2026-07-02T09:00:00+00:00", "-120.00", "30.00", "Large expense"),
            ],
        )
        income_id, _ = summary["transaction_ids"]

        response = httpx.delete(
            f"{wallet_url}/wallet/transactions/{income_id}",
            headers=_auth_headers(fixture["user_id"]),
            timeout=10.0,
        )

        assert response.status_code == 400, response.text
        assert _get_account_balance(fixture["account_id"]) == Decimal("30.00")


@pytest.mark.component
@pytest.mark.db
@allure.epic("System Tests")
@allure.feature("Component")
@allure.story("Brokerage event APIs preserve import, correction, and ownership behavior")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "brokerage", "capital-gains", "import", "financial-data", "api-contract")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Exercises brokerage import and manual event endpoints with persisted wallet state. "
    "Covers realized PnL without linked cash transactions, duplicate retry behavior, "
    "missing holding diagnostics, split/adjustment holding updates, and ownership denial."
)
class TestWalletBrokerageEventImportApi:
    @staticmethod
    def _ensure_stock_instrument(
        stock_url: str,
        symbol: str,
        name: str,
        mic: str = "XWAR",
        currency: str = "PLN",
        instrument_type: str = "STOCK",
    ) -> None:
        response = httpx.post(
            f"{stock_url}/stock/instruments",
            json={
                "market_mic": mic,
                "symbol": symbol,
                "shortname": symbol,
                "name": name,
                "type": instrument_type,
                "status": "ACTIVE",
                "currency": currency,
                "historical_source": None,
                "quote_source": None,
                "popularity": 0,
                "last_seen_at": None,
            },
            timeout=10.0,
        )
        assert response.status_code in {201, 409}, response.text

    def _ensure_stock_instruments_for_rows(self, stock_url: str, rows: list[dict[str, str]]) -> None:
        for row in rows:
            self._ensure_stock_instrument(
                stock_url,
                symbol=row["instrument_symbol"],
                name=row.get("instrument_name") or row["instrument_symbol"],
                mic=row.get("instrument_mic", "XWAR"),
                currency=row.get("currency", "PLN"),
                instrument_type="ETF" if "." in row["instrument_symbol"] else "STOCK",
            )
            target_symbol = row.get("target_instrument_symbol")
            if target_symbol:
                self._ensure_stock_instrument(
                    stock_url,
                    symbol=target_symbol,
                    name=row.get("target_instrument_name") or target_symbol,
                    mic=row.get("target_instrument_mic", "XWAR"),
                    currency=row.get("currency", "PLN"),
                )

    @staticmethod
    def _event_row(
        kind: str,
        quantity: str,
        price: str,
        trade_at: str,
        symbol: str = "PKOBP",
        name: str = "PKO BP SA",
        split_ratio: str = "0.00",
        note: str | None = None,
    ) -> dict[str, str]:
        row = {
            "instrument_symbol": symbol,
            "instrument_mic": "XWAR",
            "instrument_name": name,
            "kind": kind,
            "quantity": quantity,
            "price": price,
            "currency": "PLN",
            "split_ratio": split_ratio,
            "trade_at": trade_at,
        }
        if note is not None:
            row["note"] = note
        return row

    def test_import_sell_realized_pnl_creates_capital_gain_without_transaction_id(self, wallet_url: str, stock_url: str) -> None:
        fixture = _seed_wallet_account("brimp", opening_balance="0.00", currency="PLN")
        brokerage_account_id = _seed_brokerage_account_link(fixture, currency="PLN")

        buy_row = self._event_row(
            kind="BUY",
            quantity="10.00",
            price="9.00",
            trade_at="2026-06-01T09:00:00+00:00",
        )
        sell_row = self._event_row(
            kind="SELL",
            quantity="4.00",
            price="12.00",
            trade_at="2026-06-02T09:00:00+00:00",
        )
        self._ensure_stock_instruments_for_rows(stock_url, [buy_row, sell_row])
        response = httpx.post(
            f"{wallet_url}/wallet/brokerage/events/import",
            headers=_auth_headers(fixture["user_id"]),
            json={
                "brokerage_account_id": brokerage_account_id,
                "events": [buy_row, sell_row],
            },
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["total"] == 2
        assert payload["created"] == 2
        assert payload["skipped_duplicates"] == 0
        assert payload["failed"] == 0
        assert payload["errors"] == []
        assert [row["status"] for row in payload["rows"]] == ["created", "created"]

        with _wallet_db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT kind, amount, currency, deposit_account_id, transaction_id
                    FROM capital_gains
                    WHERE deposit_account_id = %s
                    """,
                    (fixture["account_id"],),
                )
                gains = cursor.fetchall()

        assert len(gains) == 1
        kind, amount, currency, deposit_account_id, transaction_id = gains[0]
        assert kind == "BROKER_REALIZED_PNL"
        assert Decimal(str(amount)) == Decimal("12.00")
        assert currency == "PLN"
        assert str(deposit_account_id) == fixture["account_id"]
        assert transaction_id is None

    def test_import_retry_skips_existing_events_and_creates_missing_rows(self, wallet_url: str, stock_url: str) -> None:
        fixture = _seed_wallet_account("brretry", opening_balance="0.00", currency="PLN")
        brokerage_account_id = _seed_brokerage_account_link(fixture, currency="PLN")
        buy_row = self._event_row(
            symbol="CDR",
            name="CD Projekt SA",
            kind="BUY",
            quantity="10.00",
            price="20.00",
            trade_at="2026-06-01T09:00:00+00:00",
        )
        sell_row = self._event_row(
            symbol="CDR",
            name="CD Projekt SA",
            kind="SELL",
            quantity="4.00",
            price="25.00",
            trade_at="2026-06-02T09:00:00+00:00",
        )
        self._ensure_stock_instruments_for_rows(stock_url, [buy_row, sell_row])

        first = httpx.post(
            f"{wallet_url}/wallet/brokerage/events/import",
            headers=_auth_headers(fixture["user_id"]),
            json={"brokerage_account_id": brokerage_account_id, "events": [buy_row]},
            timeout=10.0,
        )
        retry = httpx.post(
            f"{wallet_url}/wallet/brokerage/events/import",
            headers=_auth_headers(fixture["user_id"]),
            json={"brokerage_account_id": brokerage_account_id, "events": [buy_row, sell_row]},
            timeout=10.0,
        )

        assert first.status_code == 200, first.text
        assert first.json()["created"] == 1
        assert retry.status_code == 200, retry.text
        payload = retry.json()
        assert payload["total"] == 2
        assert payload["created"] == 1
        assert payload["skipped_duplicates"] == 1
        assert payload["failed"] == 0
        assert payload["errors"] == []
        assert [row["status"] for row in payload["rows"]] == ["skipped_duplicate", "created"]

        with _wallet_db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM brokerage_events
                    WHERE brokerage_account_id = %s
                    """,
                    (brokerage_account_id,),
                )
                event_count = cursor.fetchone()[0]
                cursor.execute(
                    """
                    SELECT quantity, avg_cost
                    FROM holdings
                    WHERE account_id = %s
                    """,
                    (brokerage_account_id,),
                )
                holding = cursor.fetchone()
                cursor.execute(
                    """
                    SELECT amount, transaction_id
                    FROM capital_gains
                    WHERE deposit_account_id = %s
                    """,
                    (fixture["account_id"],),
                )
                gains = cursor.fetchall()

        assert event_count == 2
        assert holding is not None
        assert Decimal(str(holding[0])) == Decimal("6.0000000000")
        assert Decimal(str(holding[1])) == Decimal("20.0000000000")
        assert len(gains) == 1
        assert Decimal(str(gains[0][0])) == Decimal("20.00")
        assert gains[0][1] is None

    def test_import_reports_missing_holding_context_and_keeps_created_rows(self, wallet_url: str, stock_url: str) -> None:
        fixture = _seed_wallet_account("brmiss", opening_balance="0.00", currency="PLN")
        brokerage_account_id = _seed_brokerage_account_link(fixture, currency="PLN")
        buy_row = self._event_row(
            symbol="CDR",
            name="CD Projekt SA",
            kind="BUY",
            quantity="10.00",
            price="20.00",
            trade_at="2026-06-01T09:00:00+00:00",
        )
        missing_sell_row = self._event_row(
            symbol="GIGRO",
            name="GIGROUP SA",
            kind="SELL",
            quantity="1269.00",
            price="1.00",
            trade_at="2021-12-23T15:13:53+00:00",
        )
        self._ensure_stock_instruments_for_rows(stock_url, [buy_row, missing_sell_row])

        response = httpx.post(
            f"{wallet_url}/wallet/brokerage/events/import",
            headers=_auth_headers(fixture["user_id"]),
            json={"brokerage_account_id": brokerage_account_id, "events": [buy_row, missing_sell_row]},
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["total"] == 2
        assert payload["created"] == 1
        assert payload["skipped_duplicates"] == 0
        assert payload["failed"] == 1
        rows_by_symbol = {row["instrument_symbol"]: row for row in payload["rows"]}
        assert rows_by_symbol["CDR"]["status"] == "created"
        assert rows_by_symbol["GIGRO"]["status"] == "failed"

        failed = rows_by_symbol["GIGRO"]
        assert failed["reason_code"] == "holding_quantity_exceeded"
        assert failed["instrument_symbol"] == "GIGRO"
        assert failed["instrument_name"] == "GIGROUP SA"
        assert failed["kind"] == "SELL"
        assert Decimal(str(failed["quantity"])) == Decimal("1269.00")
        assert Decimal(str(failed["held_quantity"])) == Decimal("0")
        assert Decimal(str(failed["missing_quantity"])) == Decimal("1269.00")
        assert "GIGRO" in failed["message"]
        assert "2021-12-23" in failed["message"]

        with _wallet_db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM brokerage_events
                    WHERE brokerage_account_id = %s
                    """,
                    (brokerage_account_id,),
                )
                event_count = cursor.fetchone()[0]
                cursor.execute(
                    """
                    SELECT i.symbol, h.quantity, h.avg_cost
                    FROM holdings h
                    JOIN instruments i ON i.id = h.instrument_id
                    WHERE h.account_id = %s
                    ORDER BY i.symbol
                    """,
                    (brokerage_account_id,),
                )
                holdings = cursor.fetchall()

        assert event_count == 1
        assert holdings == [("CDR", Decimal("10.0000000000"), Decimal("20.0000000000"))]

    def test_bossa_history_import_rejects_missing_currency_cash_link_before_writes(self, wallet_url: str) -> None:
        fixture = _seed_wallet_account("bousd", opening_balance="0.00", currency="PLN")
        brokerage_account_id = _seed_brokerage_account_link(fixture, currency="PLN")

        response = httpx.post(
            f"{wallet_url}/wallet/brokerage/history/import",
            headers=_auth_headers(fixture["user_id"]),
            json={
                "brokerage_account_id": brokerage_account_id,
                "rows": [
                    {
                        "row_number": 2,
                        "operation_type": "TRANSFER",
                        "trade_at": "2026-06-04T10:00:00+00:00",
                        "currency": "USD",
                        "amount": "100.00",
                        "amount_after": "100.00",
                        "description": "Przelew do DM BOŚ USD",
                    }
                ],
            },
            timeout=10.0,
        )

        assert response.status_code == 422, response.text
        assert "USD" in response.text

        with _wallet_db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM transactions WHERE account_id = %s",
                    (fixture["account_id"],),
                )
                transaction_count = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT COUNT(*) FROM brokerage_events WHERE brokerage_account_id = %s",
                    (brokerage_account_id,),
                )
                event_count = cursor.fetchone()[0]

        assert transaction_count == 0
        assert event_count == 0

    def test_bossa_history_import_rejects_needs_review_before_writes(self, wallet_url: str) -> None:
        fixture = _seed_wallet_account("boneeds", opening_balance="0.00", currency="PLN")
        brokerage_account_id = _seed_brokerage_account_link(fixture, currency="PLN")

        response = httpx.post(
            f"{wallet_url}/wallet/brokerage/history/import",
            headers=_auth_headers(fixture["user_id"]),
            json={
                "brokerage_account_id": brokerage_account_id,
                "rows": [
                    {
                        "row_number": 13,
                        "operation_type": "NEEDS_REVIEW",
                        "trade_at": "2026-06-04T10:00:00+00:00",
                        "currency": "USD",
                        "amount": "-12.34",
                        "amount_after": "0.00",
                        "description": "Rozliczenie transakcji kupna WisdomTree Natural Gas",
                        "instrument_name": "WisdomTree Natural Gas",
                        "review_reason": "Nie znaleziono instrumentu WisdomTree Natural Gas (ISIN: IE00TEST0001), waluta USD.",
                    }
                ],
            },
            timeout=10.0,
        )

        assert response.status_code == 422, response.text
        assert "WisdomTree Natural Gas" in response.text

        with _wallet_db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM transactions WHERE account_id = %s",
                    (fixture["account_id"],),
                )
                transaction_count = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT COUNT(*) FROM brokerage_events WHERE brokerage_account_id = %s",
                    (brokerage_account_id,),
                )
                event_count = cursor.fetchone()[0]

        assert transaction_count == 0
        assert event_count == 0

    def test_bossa_history_import_creates_cash_transaction_with_balance_validation(self, wallet_url: str) -> None:
        fixture = _seed_wallet_account("bocash", opening_balance="0.00", currency="PLN")
        brokerage_account_id = _seed_brokerage_account_link(fixture, currency="PLN")

        response = httpx.post(
            f"{wallet_url}/wallet/brokerage/history/import",
            headers=_auth_headers(fixture["user_id"]),
            json={
                "brokerage_account_id": brokerage_account_id,
                "rows": [
                    {
                        "row_number": 2,
                        "operation_type": "TRANSFER",
                        "trade_at": "2026-06-04T10:00:00+00:00",
                        "currency": "PLN",
                        "amount": "1000.00",
                        "amount_after": "1000.00",
                        "description": "Przelew do DM BOŚ PLN",
                    }
                ],
            },
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["total"] == 1
        assert payload["created"] == 1
        assert payload["cash_transactions_created"] == 1
        assert payload["failed"] == 0
        assert payload["rows"][0]["status"] == "created"
        assert payload["rows"][0]["transaction_id"]
        assert _get_account_balance(fixture["account_id"]) == Decimal("1000.00")

    def test_bossa_history_import_rejects_bad_cash_balance_chain_without_writes(self, wallet_url: str) -> None:
        fixture = _seed_wallet_account("bobadbal", opening_balance="0.00", currency="PLN")
        brokerage_account_id = _seed_brokerage_account_link(fixture, currency="PLN")

        response = httpx.post(
            f"{wallet_url}/wallet/brokerage/history/import",
            headers=_auth_headers(fixture["user_id"]),
            json={
                "brokerage_account_id": brokerage_account_id,
                "rows": [
                    {
                        "row_number": 1,
                        "operation_type": "TRANSFER",
                        "trade_at": "2026-06-01T10:00:00+00:00",
                        "currency": "PLN",
                        "amount": "100.00",
                        "amount_after": "100.00",
                        "description": "Przelew do DM BOŚ PLN",
                    },
                    {
                        "row_number": 2,
                        "operation_type": "TRANSFER",
                        "trade_at": "2026-06-02T10:00:00+00:00",
                        "currency": "PLN",
                        "amount": "50.00",
                        "amount_after": "999.00",
                        "description": "Błędny łańcuch salda",
                    },
                ],
            },
            timeout=10.0,
        )

        assert response.status_code == 422, response.text
        assert "999.00" in response.text or "Saldo" in response.text or "balance" in response.text

        with _wallet_db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM transactions WHERE account_id = %s",
                    (fixture["account_id"],),
                )
                transaction_count = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT COUNT(*) FROM brokerage_events WHERE brokerage_account_id = %s",
                    (brokerage_account_id,),
                )
                event_count = cursor.fetchone()[0]

        assert transaction_count == 0
        assert event_count == 0
        assert _get_account_balance(fixture["account_id"]) == Decimal("0.00")

    def test_bossa_parser_generated_balances_import_to_linked_cash_accounts(self, wallet_url: str) -> None:
        fixture = _seed_wallet_account("bomulti", opening_balance="0.00", currency="PLN")
        brokerage_account_id = _seed_brokerage_account_link(fixture, currency="PLN")
        usd_account_id = _seed_brokerage_cash_account(fixture, brokerage_account_id, "USD")
        eur_account_id = _seed_brokerage_cash_account(fixture, brokerage_account_id, "EUR")
        csv_payload = "\r\n".join([
            "data;tytuł operacji;szczegóły;kwota;Saldo po operacji;waluta",
            "2026-06-04;Wypłata dywidendy TEST;;5,00;;PLN",
            "2026-06-03;Wymiana waluty PLN/EUR 4.0000;;10,00;;EUR",
            "2026-06-03;Wymiana waluty PLN/EUR 4.0000;;-40,00;;PLN",
            "2026-06-03;Wymiana waluty PLN/USD 4.0000;;25,00;;USD",
            "2026-06-03;Wymiana waluty PLN/USD 4.0000;;-100,00;;PLN",
            "2026-06-02;Przelew do DM BOŚ;;200,00;;PLN",
        ]).encode("cp1250")

        parse_response = httpx.post(
            "http://nice-ui:8501/api/import/parse",
            data={"parser_name": "BossaMakler CSV", "mode": "brokerage_history"},
            files={"file": ("bossa.csv", csv_payload, "text/csv")},
            timeout=10.0,
        )
        assert parse_response.status_code == 200, parse_response.text
        parsed_payload = parse_response.json()
        assert [Decimal(str(row["amount_after"])) for row in parsed_payload["rows"]] == [
            Decimal("65.00"),
            Decimal("10.00"),
            Decimal("60.00"),
            Decimal("25.00"),
            Decimal("100.00"),
            Decimal("200.00"),
        ]

        import_response = httpx.post(
            f"{wallet_url}/wallet/brokerage/history/import",
            headers=_auth_headers(fixture["user_id"]),
            json={
                "brokerage_account_id": brokerage_account_id,
                "rows": parsed_payload["rows"],
            },
            timeout=10.0,
        )

        assert import_response.status_code == 200, import_response.text
        payload = import_response.json()
        assert payload["total"] == 6
        assert payload["created"] == 6
        assert payload["cash_transactions_created"] == 6
        assert payload["failed"] == 0
        assert _get_account_balance(fixture["account_id"]) == Decimal("65.00")
        assert _get_account_balance(usd_account_id) == Decimal("25.00")
        assert _get_account_balance(eur_account_id) == Decimal("10.00")

    def test_manual_brokerage_event_rejects_invalid_split_ratio_without_event(self, wallet_url: str, stock_url: str) -> None:
        fixture = _seed_wallet_account("brsplitbad", opening_balance="1000.00", currency="PLN")
        brokerage_account_id = _seed_brokerage_account_link(fixture, currency="PLN")
        split = self._event_row(
            kind="SPLIT",
            quantity="0.00",
            price="0.00",
            split_ratio="0.0000000000",
            trade_at="2026-06-02T09:00:00+00:00",
        )
        self._ensure_stock_instruments_for_rows(stock_url, [split])

        response = httpx.post(
            f"{wallet_url}/wallet/brokerage/event",
            headers=_auth_headers(fixture["user_id"]),
            json={"brokerage_account_id": brokerage_account_id, **split},
            timeout=10.0,
        )

        assert response.status_code == 400, response.text
        assert "Split ratio" in response.text

        with _wallet_db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM brokerage_events WHERE brokerage_account_id = %s",
                    (brokerage_account_id,),
                )
                event_count = cursor.fetchone()[0]

        assert event_count == 0

    def test_manual_conversion_rejects_missing_target_without_event(self, wallet_url: str, stock_url: str) -> None:
        fixture = _seed_wallet_account("brconvbad", opening_balance="1000.00", currency="PLN")
        brokerage_account_id = _seed_brokerage_account_link(fixture, currency="PLN")
        conversion = self._event_row(
            symbol="WORK",
            name="WORKSERV SA",
            kind="CONVERSION",
            quantity="100.00",
            price="0.00",
            split_ratio="0.2000000000",
            note="WORKSERV -> missing target",
            trade_at="2026-06-02T09:00:00+00:00",
        )
        self._ensure_stock_instruments_for_rows(stock_url, [conversion])

        response = httpx.post(
            f"{wallet_url}/wallet/brokerage/event",
            headers=_auth_headers(fixture["user_id"]),
            json={"brokerage_account_id": brokerage_account_id, **conversion},
            timeout=10.0,
        )

        assert response.status_code == 400, response.text
        assert "target instrument" in response.text

        with _wallet_db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM brokerage_events WHERE brokerage_account_id = %s",
                    (brokerage_account_id,),
                )
                event_count = cursor.fetchone()[0]

        assert event_count == 0

    def test_manual_split_and_adjustment_update_holding_without_extra_cash_rows(self, wallet_url: str, stock_url: str) -> None:
        fixture = _seed_wallet_account("bradj", opening_balance="1000.00", currency="PLN")
        brokerage_account_id = _seed_brokerage_account_link(fixture, currency="PLN")
        headers = _auth_headers(fixture["user_id"])

        buy = self._event_row(
            kind="BUY",
            quantity="10.00",
            price="20.00",
            trade_at="2026-06-01T09:00:00+00:00",
        )
        split = self._event_row(
            kind="SPLIT",
            quantity="0.00",
            price="0.00",
            split_ratio="2.0000000000",
            trade_at="2026-06-02T09:00:00+00:00",
        )
        adjustment = self._event_row(
            kind="ADJUSTMENT",
            quantity="25.00",
            price="8.00",
            note="Korekta po scaleniu, stara nazwa: ELZAB",
            trade_at="2026-06-03T09:00:00+00:00",
        )
        self._ensure_stock_instruments_for_rows(stock_url, [buy, split, adjustment])

        for payload in (buy, split, adjustment):
            response = httpx.post(
                f"{wallet_url}/wallet/brokerage/event",
                headers=headers,
                json={"brokerage_account_id": brokerage_account_id, **payload},
                timeout=10.0,
            )
            assert response.status_code == 200, response.text

        with _wallet_db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT h.quantity, h.avg_cost
                    FROM holdings h
                    JOIN instruments i ON i.id = h.instrument_id
                    WHERE h.account_id = %s
                      AND i.symbol = 'PKOBP'
                    """,
                    (brokerage_account_id,),
                )
                holding = cursor.fetchone()
                cursor.execute(
                    """
                    SELECT kind, split_ratio, note
                    FROM brokerage_events
                    WHERE brokerage_account_id = %s
                    ORDER BY trade_at
                    """,
                    (brokerage_account_id,),
                )
                events = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM transactions
                    WHERE account_id = %s
                    """,
                    (fixture["account_id"],),
                )
                cash_rows = cursor.fetchone()[0]
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM capital_gains
                    WHERE deposit_account_id = %s
                    """,
                    (fixture["account_id"],),
                )
                gain_rows = cursor.fetchone()[0]

        assert holding is not None
        assert Decimal(str(holding[0])) == Decimal("25.0000000000")
        assert Decimal(str(holding[1])) == Decimal("8.0000000000")
        assert [event[0] for event in events] == ["TRADE_BUY", "SPLIT", "ADJUSTMENT"]
        assert Decimal(str(events[1][1])) == Decimal("2.0000000000")
        assert events[2][2] == "Korekta po scaleniu, stara nazwa: ELZAB"
        assert cash_rows == 1
        assert gain_rows == 0

    def test_manual_conversion_rebrands_instrument_and_preserves_cost_basis(self, wallet_url: str, stock_url: str) -> None:
        fixture = _seed_wallet_account("brconv", opening_balance="5000.00", currency="PLN")
        brokerage_account_id = _seed_brokerage_account_link(fixture, currency="PLN")
        headers = _auth_headers(fixture["user_id"])

        buy = self._event_row(
            symbol="WORK",
            name="WORKSERV SA",
            kind="BUY",
            quantity="1000.00",
            price="2.00",
            trade_at="2026-06-01T09:00:00+00:00",
        )
        conversion = {
            **self._event_row(
                symbol="WORK",
                name="WORKSERV SA",
                kind="CONVERSION",
                quantity="1000.00",
                price="0.00",
                split_ratio="0.2000000000",
                note="WORKSERV -> GIGROUP, scalenie 1:5",
                trade_at="2026-06-02T09:00:00+00:00",
            ),
            "target_instrument_symbol": "GIG",
            "target_instrument_mic": "XWAR",
            "target_instrument_name": "GIGROUP SA",
        }
        self._ensure_stock_instruments_for_rows(stock_url, [buy, conversion])

        for payload in (buy, conversion):
            response = httpx.post(
                f"{wallet_url}/wallet/brokerage/event",
                headers=headers,
                json={"brokerage_account_id": brokerage_account_id, **payload},
                timeout=10.0,
            )
            assert response.status_code == 200, response.text

        with _wallet_db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT i.symbol, h.quantity, h.avg_cost
                    FROM holdings h
                    JOIN instruments i ON i.id = h.instrument_id
                    WHERE h.account_id = %s
                    ORDER BY i.symbol
                    """,
                    (brokerage_account_id,),
                )
                holdings = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT e.id, e.kind, src.symbol, tgt.symbol, e.quantity, e.split_ratio, e.note
                    FROM brokerage_events e
                    JOIN instruments src ON src.id = e.instrument_id
                    LEFT JOIN instruments tgt ON tgt.id = e.target_instrument_id
                    WHERE e.brokerage_account_id = %s
                    ORDER BY e.trade_at
                    """,
                    (brokerage_account_id,),
                )
                events = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM transactions
                    WHERE account_id = %s
                    """,
                    (fixture["account_id"],),
                )
                cash_rows = cursor.fetchone()[0]
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM capital_gains
                    WHERE deposit_account_id = %s
                    """,
                    (fixture["account_id"],),
                )
                gain_rows = cursor.fetchone()[0]

        assert holdings == [("GIG", Decimal("200.0000000000"), Decimal("10.0000000000"))]
        assert [event[1] for event in events] == ["TRADE_BUY", "CONVERSION"]
        assert events[1][2] == "WORK"
        assert events[1][3] == "GIG"
        assert Decimal(str(events[1][4])) == Decimal("1000.0000000000")
        assert Decimal(str(events[1][5])) == Decimal("0.2000000000")
        assert events[1][6] == "WORKSERV -> GIGROUP, scalenie 1:5"
        assert cash_rows == 1
        assert gain_rows == 0

        delete_response = httpx.delete(
            f"{wallet_url}/wallet/brokerage/events/{events[1][0]}",
            headers=headers,
            timeout=10.0,
        )
        assert delete_response.status_code == 200, delete_response.text

        with _wallet_db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT i.symbol, h.quantity, h.avg_cost
                    FROM holdings h
                    JOIN instruments i ON i.id = h.instrument_id
                    WHERE h.account_id = %s
                    ORDER BY i.symbol
                    """,
                    (brokerage_account_id,),
                )
                rebuilt_holdings = cursor.fetchall()

        assert rebuilt_holdings == [("WORK", Decimal("1000.0000000000"), Decimal("2.0000000000"))]

    def test_manual_brokerage_event_rejects_cross_user_account(self, wallet_url: str) -> None:
        owner = _seed_wallet_account("brownevt", opening_balance="1000.00", currency="PLN")
        other = _seed_wallet_account("broevtoth", opening_balance="1000.00", currency="PLN")
        brokerage_account_id = _seed_brokerage_account_link(owner, currency="PLN")

        response = httpx.post(
            f"{wallet_url}/wallet/brokerage/event",
            headers=_auth_headers(other["user_id"]),
            json={
                "brokerage_account_id": brokerage_account_id,
                **self._event_row(
                    kind="ADJUSTMENT",
                    quantity="1.00",
                    price="10.00",
                    note="Nie powinno przejść",
                    trade_at="2026-06-03T09:00:00+00:00",
                ),
            },
            timeout=10.0,
        )

        assert response.status_code == 404, response.text
        assert response.json()["detail"] == "Brokerage account not found."

    def test_delete_brokerage_account_removes_dedicated_cash_account(self, wallet_url: str) -> None:
        fixture = _seed_wallet_account(
            "brdel",
            opening_balance="123.45",
            currency="PLN",
            account_type="BROKERAGE",
        )
        brokerage_account_id = _seed_brokerage_account_link(fixture, currency="PLN")

        response = httpx.delete(
            f"{wallet_url}/wallet/brokerage/{brokerage_account_id}",
            headers=_auth_headers(fixture["user_id"]),
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
        assert response.json()["ok"] is True

        with _wallet_db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM brokerage_accounts WHERE id = %s",
                    (brokerage_account_id,),
                )
                brokerage_count = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT COUNT(*) FROM brokerage_deposit_links WHERE brokerage_account_id = %s",
                    (brokerage_account_id,),
                )
                link_count = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT COUNT(*) FROM deposit_accounts WHERE id = %s",
                    (fixture["account_id"],),
                )
                cash_account_count = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT COUNT(*) FROM deposit_account_balances WHERE account_id = %s",
                    (fixture["account_id"],),
                )
                cash_balance_count = cursor.fetchone()[0]

        assert brokerage_count == 0
        assert link_count == 0
        assert cash_account_count == 0
        assert cash_balance_count == 0

    def test_delete_brokerage_account_denies_cross_user_and_preserves_cash_account(self, wallet_url: str) -> None:
        owner = _seed_wallet_account(
            "brdelown",
            opening_balance="123.45",
            currency="PLN",
            account_type="BROKERAGE",
        )
        other = _seed_wallet_account("brdeloth", opening_balance="0.00", currency="PLN")
        brokerage_account_id = _seed_brokerage_account_link(owner, currency="PLN")

        response = httpx.delete(
            f"{wallet_url}/wallet/brokerage/{brokerage_account_id}",
            headers=_auth_headers(other["user_id"]),
            timeout=10.0,
        )

        assert response.status_code == 404, response.text
        assert response.json()["detail"] == "Account not found"

        with _wallet_db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM brokerage_accounts WHERE id = %s",
                    (brokerage_account_id,),
                )
                brokerage_count = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT COUNT(*) FROM brokerage_deposit_links WHERE brokerage_account_id = %s",
                    (brokerage_account_id,),
                )
                link_count = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT COUNT(*) FROM deposit_accounts WHERE id = %s",
                    (owner["account_id"],),
                )
                cash_account_count = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT COUNT(*) FROM deposit_account_balances WHERE account_id = %s",
                    (owner["account_id"],),
                )
                cash_balance_count = cursor.fetchone()[0]

        assert brokerage_count == 1
        assert link_count == 1
        assert cash_account_count == 1
        assert cash_balance_count == 1

    def test_ensure_brokerage_cash_link_creates_technical_usd_subaccount(
        self,
        wallet_url: str,
        session_url: str,
    ) -> None:
        fixture = _seed_wallet_account(
            "brcash",
            opening_balance="0.00",
            currency="PLN",
            account_type="BROKERAGE",
        )
        _register_session_crypto_user(session_url, fixture)
        brokerage_account_id = _seed_brokerage_account_link(fixture, currency="PLN")

        response = httpx.post(
            f"{wallet_url}/wallet/brokerage/{brokerage_account_id}/cash-links/ensure",
            headers=_auth_headers(fixture["user_id"]),
            json={
                "cash_accounts": [
                    {
                        "currency": "USD",
                        "account_number": "BOSSA-IKE-USD-ARTUR",
                        "name": "BOSSA IKE Artur · USD",
                    }
                ]
            },
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["currency"] == "USD"
        assert payload[0]["created"] is True
        cash_account_id = payload[0]["deposit_account_id"]

        with _wallet_db_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT name, account_type, currency
                    FROM deposit_accounts
                    WHERE id = %s
                    """,
                    (cash_account_id,),
                )
                cash_account = cursor.fetchone()
                cursor.execute(
                    """
                    SELECT currency
                    FROM brokerage_deposit_links
                    WHERE brokerage_account_id = %s
                      AND deposit_account_id = %s
                    """,
                    (brokerage_account_id, cash_account_id),
                )
                link = cursor.fetchone()
                cursor.execute(
                    """
                    SELECT available, blocked
                    FROM deposit_account_balances
                    WHERE account_id = %s
                    """,
                    (cash_account_id,),
                )
                balance = cursor.fetchone()

        assert cash_account == ("BOSSA IKE Artur · USD", "BROKERAGE", "USD")
        assert link == ("USD",)
        assert balance == (Decimal("0.00"), Decimal("0.00"))

    def test_import_rejects_brokerage_account_owned_by_another_user(self, wallet_url: str) -> None:
        owner = _seed_wallet_account("browner", opening_balance="0.00", currency="PLN")
        other = _seed_wallet_account("broother", opening_balance="0.00", currency="PLN")
        brokerage_account_id = _seed_brokerage_account_link(owner, currency="PLN")

        response = httpx.post(
            f"{wallet_url}/wallet/brokerage/events/import",
            headers=_auth_headers(other["user_id"]),
            json={
                "brokerage_account_id": brokerage_account_id,
                "events": [
                    self._event_row(
                        kind="BUY",
                        quantity="1.00",
                        price="10.00",
                        trade_at="2026-06-01T09:00:00+00:00",
                    )
                ],
            },
            timeout=10.0,
        )

        assert response.status_code == 404, response.text
        assert response.json()["detail"] == "Brokerage account not found."


@pytest.mark.component
@pytest.mark.db
@allure.epic("System Tests")
@allure.feature("Component")
@allure.story("Wallet transaction list filters return correctly scoped results")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "transactions", "filters", "api-contract", "database")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Exercises GET /wallet/transactions filters against the test database: "
    "status=TAXES returns only TAXES transactions, category filter returns only "
    "matching rows, and pagination correctly splits results across pages."
)
class TestWalletTransactionListFiltersApi:
    def test_status_taxes_filter_returns_only_taxes_transactions(self, wallet_url: str) -> None:
        fixture = _seed_wallet_account("txftax", opening_balance="200.00", currency="PLN")
        summary = _create_transactions(
            wallet_url,
            fixture["user_id"],
            fixture["account_id"],
            [
                _transaction_row("2026-06-10T09:00:00+00:00", "100.00", "300.00", "Salary income"),
                _transaction_row("2026-06-11T09:00:00+00:00", "-30.00", "270.00", "Tax payment"),
            ],
        )
        income_id, tax_id = summary["transaction_ids"]

        httpx.patch(
            f"{wallet_url}/wallet/transactions/batch",
            headers=_auth_headers(fixture["user_id"]),
            json={"items": [{"id": tax_id, "status": "TAXES"}]},
            timeout=10.0,
        ).raise_for_status()

        response = httpx.get(
            f"{wallet_url}/wallet/transactions",
            headers=_auth_headers(fixture["user_id"]),
            params={"account_id": fixture["account_id"], "status": "TAXES"},
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
        page = response.json()
        assert page["total"] == 1
        assert page["items"][0]["id"] == tax_id
        assert page["items"][0]["status"] == "TAXES"
        assert all(row["id"] != income_id for row in page["items"])

    def test_category_filter_returns_only_matching_transactions(self, wallet_url: str) -> None:
        fixture = _seed_wallet_account("txfcat", opening_balance="100.00", currency="PLN")
        summary = _create_transactions(
            wallet_url,
            fixture["user_id"],
            fixture["account_id"],
            [
                _transaction_row("2026-06-20T09:00:00+00:00", "-15.00", "85.00", "Grocery shop"),
                _transaction_row("2026-06-21T09:00:00+00:00", "-40.00", "45.00", "Fuel station"),
            ],
        )
        grocery_id, fuel_id = summary["transaction_ids"]

        httpx.patch(
            f"{wallet_url}/wallet/transactions/batch",
            headers=_auth_headers(fixture["user_id"]),
            json={"items": [{"id": grocery_id, "category": "FOOD"}]},
            timeout=10.0,
        ).raise_for_status()

        response = httpx.get(
            f"{wallet_url}/wallet/transactions",
            headers=_auth_headers(fixture["user_id"]),
            params={"account_id": fixture["account_id"], "category": "FOOD"},
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
        page = response.json()
        assert page["total"] == 1
        assert page["items"][0]["id"] == grocery_id
        assert page["items"][0]["category"] == "FOOD"
        assert all(row["id"] != fuel_id for row in page["items"])

    def test_pagination_returns_correct_page_slice_and_total(self, wallet_url: str) -> None:
        fixture = _seed_wallet_account("txfpag", opening_balance="0.00", currency="PLN")
        _create_transactions(
            wallet_url,
            fixture["user_id"],
            fixture["account_id"],
            [
                _transaction_row("2026-06-01T09:00:00+00:00", "10.00", "10.00", "Tx 1"),
                _transaction_row("2026-06-02T09:00:00+00:00", "10.00", "20.00", "Tx 2"),
                _transaction_row("2026-06-03T09:00:00+00:00", "10.00", "30.00", "Tx 3"),
            ],
        )

        page1 = httpx.get(
            f"{wallet_url}/wallet/transactions",
            headers=_auth_headers(fixture["user_id"]),
            params={"account_id": fixture["account_id"], "page": 1, "size": 2},
            timeout=10.0,
        )
        page2 = httpx.get(
            f"{wallet_url}/wallet/transactions",
            headers=_auth_headers(fixture["user_id"]),
            params={"account_id": fixture["account_id"], "page": 2, "size": 2},
            timeout=10.0,
        )

        assert page1.status_code == 200, page1.text
        p1 = page1.json()
        assert p1["total"] == 3
        assert len(p1["items"]) == 2
        assert p1["page"] == 1
        assert p1["size"] == 2

        assert page2.status_code == 200, page2.text
        p2 = page2.json()
        assert p2["total"] == 3
        assert len(p2["items"]) == 1
        assert p2["page"] == 2


@pytest.mark.component
@pytest.mark.db
@allure.epic("System Tests")
@allure.feature("Component")
@allure.story("Wallet transaction list sort query parameters order paginated API results")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "transactions", "sorting", "pagination", "api-contract", "database")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Exercises GET /wallet/transactions sort_by/sort_dir against persisted rows. "
    "The scenario verifies date sorting and category sorting at the wallet API level, "
    "so Next UI can request globally sorted pages instead of sorting only the visible page."
)
class TestWalletTransactionListSortingApi:
    def test_sorting_by_date_and_category_returns_ordered_rows(self, wallet_url: str) -> None:
        fixture = _seed_wallet_account("txsort", opening_balance="0.00", currency="PLN")
        summary = _create_transactions(
            wallet_url,
            fixture["user_id"],
            fixture["account_id"],
            [
                _transaction_row("2026-06-01T09:00:00+00:00", "10.00", "10.00", "First income"),
                _transaction_row("2026-06-02T09:00:00+00:00", "10.00", "20.00", "Second income"),
                _transaction_row("2026-06-03T09:00:00+00:00", "10.00", "30.00", "Third income"),
            ],
        )
        first_id, second_id, third_id = summary["transaction_ids"]

        httpx.patch(
            f"{wallet_url}/wallet/transactions/batch",
            headers=_auth_headers(fixture["user_id"]),
            json={"items": [
                {"id": first_id, "category": "ZUS_TAXES"},
                {"id": third_id, "category": "FOOD"},
                {"id": second_id, "category": "FUEL"},
            ]},
            timeout=10.0,
        ).raise_for_status()

        date_asc = httpx.get(
            f"{wallet_url}/wallet/transactions",
            headers=_auth_headers(fixture["user_id"]),
            params={
                "account_id": fixture["account_id"],
                "sort_by": "date",
                "sort_dir": "asc",
                "size": 10,
            },
            timeout=10.0,
        )
        date_desc = httpx.get(
            f"{wallet_url}/wallet/transactions",
            headers=_auth_headers(fixture["user_id"]),
            params={
                "account_id": fixture["account_id"],
                "sort_by": "date",
                "sort_dir": "desc",
                "size": 10,
            },
            timeout=10.0,
        )
        category_asc = httpx.get(
            f"{wallet_url}/wallet/transactions",
            headers=_auth_headers(fixture["user_id"]),
            params={
                "account_id": fixture["account_id"],
                "sort_by": "category",
                "sort_dir": "asc",
                "size": 10,
            },
            timeout=10.0,
        )

        assert date_asc.status_code == 200, date_asc.text
        assert date_desc.status_code == 200, date_desc.text
        assert category_asc.status_code == 200, category_asc.text

        assert [row["id"] for row in date_asc.json()["items"]] == [
            first_id,
            second_id,
            third_id,
        ]
        assert [row["id"] for row in date_desc.json()["items"]] == [
            third_id,
            second_id,
            first_id,
        ]
        assert [row["id"] for row in category_asc.json()["items"]] == [
            third_id,
            second_id,
            first_id,
        ]


@pytest.mark.component
@pytest.mark.db
@allure.epic("System Tests")
@allure.feature("Component")
@allure.story("TAXES transactions appear in dash_flow tax bucket and not in expense")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "transactions", "taxes", "dash-flow", "financial-data", "api-contract")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "End-to-end verification of the TAXES status feature: creates transactions, "
    "reclassifies one as TAXES via batch update, then calls POST /wallet/sync/user "
    "and asserts the transaction appears in dash_flow_8m.tax_by_currency and NOT "
    "in expense_by_currency for that month."
)
class TestWalletTaxesDashFlowApi:
    def test_taxes_transactions_appear_in_tax_bucket_not_in_expense(self, wallet_url: str) -> None:
        now = datetime.now(timezone.utc)
        month_key = now.strftime("%Y-%m")
        base_dt = now.replace(hour=9, minute=0, second=0, microsecond=0)
        income_date = base_dt.isoformat()
        tax_date = base_dt.replace(hour=10).isoformat()

        fixture = _seed_wallet_account("txdashtax", opening_balance="1000.00", currency="PLN")
        summary = _create_transactions(
            wallet_url,
            fixture["user_id"],
            fixture["account_id"],
            [
                _transaction_row(income_date, "500.00", "1500.00", "Przychód miesiąca"),
                _transaction_row(tax_date, "-190.00", "1310.00", "Podatek do zapłaty"),
            ],
        )
        income_id, tax_id = summary["transaction_ids"]

        # dash_flow_8m only aggregates transactions with an explicit status
        httpx.patch(
            f"{wallet_url}/wallet/transactions/batch",
            headers=_auth_headers(fixture["user_id"]),
            json={"items": [
                {"id": income_id, "status": "INCOME"},
                {"id": tax_id, "status": "TAXES"},
            ]},
            timeout=10.0,
        ).raise_for_status()

        wallet_response = httpx.post(
            f"{wallet_url}/wallet/sync/user",
            json={
                "username": fixture["username"],
                "email": fixture["email"],
                "first_name": "Component",
            },
            timeout=10.0,
        )

        assert wallet_response.status_code == 200, wallet_response.text
        wallets = wallet_response.json().get("wallets", [])
        assert wallets, "sync/user returned no wallets"

        dash_flow = wallets[0].get("dash_flow_8m", [])
        this_month = next(
            (item for item in dash_flow if item["month"] == month_key),
            None,
        )
        assert this_month is not None, (
            f"Month {month_key} not found in dash_flow_8m — "
            f"available months: {[d['month'] for d in dash_flow]}"
        )

        tax_amounts = this_month.get("tax_by_currency", {})
        expense_amounts = this_month.get("expense_by_currency", {})

        assert Decimal(str(tax_amounts.get("PLN", "0"))) == Decimal("-190.00"), (
            f"Expected tax_by_currency PLN=-190.00, got {tax_amounts}"
        )
        assert "PLN" not in expense_amounts or Decimal(str(expense_amounts["PLN"])) != Decimal("-190.00"), (
            "TAXES transaction must not appear in expense_by_currency"
        )
        assert Decimal(str(this_month.get("income_by_currency", {}).get("PLN", "0"))) == Decimal("500.00")
