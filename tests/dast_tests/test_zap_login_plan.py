from __future__ import annotations

from pathlib import Path

import allure
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.dast
@pytest.mark.security
@pytest.mark.contract
@allure.epic("Security")
@allure.feature("DAST")
@allure.story("OWASP ZAP login DAST runner is configured with bounded security evidence")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("auth", "security", "dast", "zap")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Verifies that the explicit OWASP ZAP login scan runner targets the routed login page, "
    "writes evidence artifacts, and does not embed secrets."
)
class TestZapLoginDastPlan:
    def test_zap_login_dast_runner_targets_next_ui_login_and_writes_reports(self) -> None:
        script = (REPO_ROOT / "tests/docker/run_zap_login_dast.sh").read_text(encoding="utf-8")

        assert "ghcr.io/zaproxy/zaproxy:stable" in script
        assert "http://next.localhost/login" in script
        assert "zap-baseline.py" in script
        assert "zap-login-report.html" in script
        assert "zap-login-report.json" in script
        assert "zap-login-report.md" in script
        assert "--network" in script
        assert "financialmanager_tests_network" in script

    def test_zap_login_dast_runner_does_not_embed_credentials_or_tokens(self) -> None:
        script = (REPO_ROOT / "tests/docker/run_zap_login_dast.sh").read_text(encoding="utf-8").lower()

        forbidden_fragments = [
            "password=",
            "password:",
            "sessionid=",
            "hmac=",
            "hmac_token",
            "authorization:",
        ]
        assert all(fragment not in script for fragment in forbidden_fragments)
