from __future__ import annotations

import re
from pathlib import Path

import allure
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
AUTH_SOURCE_PATHS = [
    "next-ui/src/features/auth/actions/login.ts",
    "next-ui/src/proxy.ts",
    "session/config/settings.py",
    "session/userauth/backends.py",
    "session/userauth/hmac_token.py",
    "session/userauth/serializers.py",
    "session/userauth/throttles.py",
    "session/userauth/views.py",
    "session/utils/utils.py",
]
SENSITIVE_DYNAMIC_LOG_RE = re.compile(
    r"logger\.\w+\([^\n]*("
    r"\{[^}]*\b(email|password|rawBody|body|sessionid|hmac_token|provided_hmac|"
    r"encoded_hmac_signature|request\.user\.username|message)\b[^}]*\}|"
    r"\b(email|password|rawBody|body|sessionid|hmac_token|provided_hmac|"
    r"encoded_hmac_signature)\b\s*[,)}]"
    r")",
    re.IGNORECASE,
)
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b\w*(secret|token|password|hmac|cookie)\w*\s*[:=]\s*['\"]([^'\"\n{}$]{20,})['\"]"
)


def _lines_matching(path: Path, pattern: re.Pattern[str]) -> list[str]:
    matches = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if pattern.search(line):
            matches.append(f"{path.relative_to(REPO_ROOT)}:{line_number}: {line.strip()}")
    return matches


@pytest.mark.integration
@allure.epic("Security")
@allure.feature("Integration")
@allure.story("Auth source passes static security checks for logging and committed secrets")
@allure.severity(allure.severity_level.BLOCKER)
@allure.tag("auth", "security", "sast", "secrets")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class TestAuthStaticSecurityContracts:
    def test_auth_logging_does_not_reference_sensitive_runtime_values(self) -> None:
        violations = []
        for relative_path in AUTH_SOURCE_PATHS:
            violations.extend(_lines_matching(REPO_ROOT / relative_path, SENSITIVE_DYNAMIC_LOG_RE))

        assert violations == []

    def test_auth_source_does_not_commit_high_risk_secret_literals(self) -> None:
        violations = []
        for relative_path in AUTH_SOURCE_PATHS:
            violations.extend(_lines_matching(REPO_ROOT / relative_path, SECRET_ASSIGNMENT_RE))

        assert violations == []
