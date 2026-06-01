from __future__ import annotations

import ast
from pathlib import Path
import unittest

import allure
import pytest


pytestmark = pytest.mark.unit


def _negative_credit_migration_source() -> str:
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "d4f61a2b9c7e_allow_negative_credit_balances.py"
    )
    return migration.read_text(encoding="utf-8")


def _upgrade_execute_statements(source: str) -> list[str]:
    module = ast.parse(source)
    upgrade = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade"
    )

    statements: list[str] = []
    for node in ast.walk(upgrade):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "execute":
            continue
        if not node.args:
            continue
        sql = ast.literal_eval(node.args[0])
        if isinstance(sql, str):
            statements.append(sql)
    return statements


@allure.epic("Unit Tests")
@allure.feature("Wallet")
@allure.story("Wallet migrations remain compatible with asyncpg prepared statements")
@allure.severity(allure.severity_level.BLOCKER)
@allure.tag("database", "migration", "wallet", "financial-data")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
class WalletMigrationTests(unittest.TestCase):
    def test_negative_credit_upgrade_executes_trigger_ddl_one_command_at_a_time(self) -> None:
        statements = _upgrade_execute_statements(_negative_credit_migration_source())

        trigger_drops = [sql for sql in statements if "DROP TRIGGER" in sql]
        trigger_creates = [sql for sql in statements if "CREATE TRIGGER" in sql]

        self.assertEqual(len(trigger_drops), 3)
        self.assertEqual(len(trigger_creates), 3)
        for sql in trigger_drops:
            self.assertNotIn("CREATE TRIGGER", sql)
