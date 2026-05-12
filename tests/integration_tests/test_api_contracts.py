from __future__ import annotations

import allure
import pytest

from tests.helpers.http import wait_for_response


@pytest.mark.integration
@pytest.mark.contract
@allure.epic("System Tests")
@allure.feature("Integration")
@allure.story("FastAPI services publish expected OpenAPI route contracts")
@pytest.mark.parametrize(
    ("service_name", "base_url", "expected_paths"),
    [
        ("wallet", "wallet_url", ["/wallet/create/wallet", "/wallet/accounts", "/users/favorites/lists"]),
        ("stock", "stock_url", ["/stock/markets", "/stock/instruments/options", "/stock/quotes/latest/bulk"]),
    ],
)
def test_fastapi_services_publish_expected_openapi_paths(
    request: pytest.FixtureRequest,
    service_name: str,
    base_url: str,
    expected_paths: list[str],
) -> None:
    url = request.getfixturevalue(base_url)

    with allure.step(f"Fetch {service_name} OpenAPI schema"):
        response = wait_for_response(f"{url}/openapi.json", expected_statuses={200})

    schema = response.json()
    paths = schema.get("paths", {})

    assert schema.get("openapi", "").startswith("3.")
    for expected_path in expected_paths:
        assert expected_path in paths
