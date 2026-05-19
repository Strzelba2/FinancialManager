from __future__ import annotations

from pathlib import Path

import allure
import pytest


def _compose_text() -> str:
    return (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text(encoding="utf-8")


def _service_section(compose: str, service_name: str, next_service_name: str) -> str:
    return compose.split(f"\n  {service_name}:\n", 1)[1].split(f"\n  {next_service_name}:\n", 1)[0]


def _service_labels(compose: str, service_name: str, next_service_name: str) -> set[str]:
    section = _service_section(compose, service_name, next_service_name)
    labels: set[str] = set()
    in_labels = False

    for line in section.splitlines():
        stripped = line.strip()
        if stripped == "labels:":
            in_labels = True
            continue
        if not in_labels:
            continue
        if stripped.startswith("- "):
            labels.add(stripped[2:].strip().strip('"').strip("'"))
            continue
        if stripped and not stripped.startswith("#"):
            break

    return labels


@pytest.mark.integration
@pytest.mark.contract
@allure.epic("System Tests")
@allure.feature("Integration")
@allure.story("Next UI protected routing remains behind session ForwardAuth")
@allure.severity(allure.severity_level.BLOCKER)
@allure.tag("next-ui", "session", "auth", "security", "routing")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class TestNextUiAuthRoutingContract:
    def test_protected_next_ui_router_uses_session_forwardauth_and_auth_headers(self) -> None:
        compose = _compose_text()
        labels = _service_labels(compose, "next-ui", "wallet")

        assert "traefik.http.routers.next-ui.middlewares=next-forwardauth@docker,next-auth-errors@docker,nocache@docker" in labels
        assert "traefik.http.middlewares.next-forwardauth.forwardauth.address=http://session-auth:8000/verifySession/" in labels
        assert "traefik.http.middlewares.next-forwardauth.forwardauth.authResponseHeaders=X-User,X-First-Name,X-Email,X-User-Id" in labels
        assert "traefik.http.middlewares.next-forwardauth.forwardauth.addAuthCookiesToResponse=hmac,sessionid" in labels

    def test_public_auth_routes_are_explicitly_separated_from_protected_router(self) -> None:
        compose = _compose_text()
        labels = _service_labels(compose, "next-ui", "wallet")

        assert "traefik.http.routers.next-ui-login.rule=Host(`next.localhost`) && (PathPrefix(`/login`) || PathPrefix(`/register`) || PathPrefix(`/logout`))" in labels
        assert "traefik.http.routers.next-ui-login.service=next-ui-service" in labels
        assert "traefik.http.routers.next-ui-login.middlewares=next-forwardauth@docker" not in labels

    def test_next_api_routes_stay_on_the_forwardauth_protected_router(self) -> None:
        compose = _compose_text()
        labels = _service_labels(compose, "next-ui", "wallet")

        assert "traefik.http.routers.next-ui.rule=Host(`next.localhost`)" in labels
        assert "traefik.http.routers.next-ui.middlewares=next-forwardauth@docker,next-auth-errors@docker,nocache@docker" in labels
        assert not any(label.startswith("traefik.http.routers.next-ui-api.") for label in labels)

    def test_wallet_backend_is_not_exposed_as_a_public_traefik_router(self) -> None:
        compose = _compose_text()
        wallet_section = _service_section(compose, "wallet", "stock")

        assert "traefik.http.routers.wallet" not in wallet_section
        assert "\n    ports:" not in wallet_section
        assert "\n    expose:\n      - 8001" in wallet_section
