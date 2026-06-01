from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import allure
import httpx
import psycopg
import pytest


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
        "currency": currency,
        "account_type": account_type,
        "username": username,
        "email": email,
    }


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
