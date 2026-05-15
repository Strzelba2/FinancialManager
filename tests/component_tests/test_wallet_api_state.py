from __future__ import annotations

from uuid import uuid4

import allure
import httpx
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
