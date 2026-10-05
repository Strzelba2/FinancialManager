from __future__ import annotations

import ast
from pathlib import Path
import unittest

import allure
import pytest


pytestmark = pytest.mark.unit


def _negative_credit_migration_source() -> str:
    migration = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "d4f61a2b9c7e_allow_negative_credit_balances.py"
    return migration.read_text(encoding="utf-8")


def _brokerage_adjustment_migration_source() -> str:
    migration = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "e0f4aa2c6d9b_add_brokerage_adjustments.py"
    return migration.read_text(encoding="utf-8")


def _brokerage_conversion_migration_source() -> str:
    migration = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "f2b7c9d4e1a6_add_brokerage_conversions.py"
    return migration.read_text(encoding="utf-8")


def _brokerage_event_transaction_link_migration_source() -> str:
    migration = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "a3c5e7f9b1d2_link_brokerage_events_to_transactions.py"
    return migration.read_text(encoding="utf-8")


def _cash_holdings_migration_source() -> str:
    migration = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "b6d8f0a2c4e6_create_cash_holdings_table.py"
    return migration.read_text(encoding="utf-8")


def _cash_snapshot_migration_source() -> str:
    migration = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "c8e0a2b4d6f8_create_cash_holding_monthly_snapshots.py"
    return migration.read_text(encoding="utf-8")


def _year_goal_capital_target_migration_source() -> str:
    migration = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "4f2b8c1d9a0e_add_capital_gain_target_to_year_goals.py"
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

    def test_brokerage_adjustment_migration_adds_enum_values_and_note_column(self) -> None:
        source = _brokerage_adjustment_migration_source()
        statements = _upgrade_execute_statements(source)

        self.assertIn("ALTER TYPE brokerage_event_kind ADD VALUE IF NOT EXISTS 'DIV'", statements)
        self.assertIn("ALTER TYPE brokerage_event_kind ADD VALUE IF NOT EXISTS 'ADJUSTMENT'", statements)
        self.assertIn('sa.Column("note", sa.String(length=500), nullable=True)', source)
        self.assertIn("sa.Numeric(precision=28, scale=10)", source)

    def test_brokerage_conversion_migration_adds_enum_value_and_target_instrument_fk(self) -> None:
        source = _brokerage_conversion_migration_source()
        statements = _upgrade_execute_statements(source)

        self.assertIn("ALTER TYPE brokerage_event_kind ADD VALUE IF NOT EXISTS 'CONVERSION'", statements)
        self.assertIn('sa.Column("target_instrument_id", pg.UUID(as_uuid=True), nullable=True)', source)
        self.assertIn('"fk_brokerage_events_target_instrument_id"', source)
        self.assertIn('ondelete="SET NULL"', source)

    def test_brokerage_event_transaction_link_migration_adds_unique_fk_and_safe_backfill(self) -> None:
        source = _brokerage_event_transaction_link_migration_source()

        self.assertIn('sa.Column("transaction_id", pg.UUID(as_uuid=True), nullable=True)', source)
        self.assertIn('"ix_brokerage_events_transaction_id"', source)
        self.assertIn("unique=True", source)
        self.assertIn('"fk_brokerage_events_transaction_id"', source)
        self.assertIn('ondelete="SET NULL"', source)
        # Backfill links only the manual cash settlement description and one-to-one matches.
        self.assertIn("'^(BUY|SELL|DIV) (\\S+) ([0-9]+(?:\\.[0-9]+)?) @ ([0-9]+(?:\\.[0-9]+)?)$'", source)
        self.assertIn("tt.date_transaction = be.trade_at", source)
        self.assertIn("c2.event_id = c.event_id) = 1", source)
        self.assertIn("c3.transaction_id = c.transaction_id) = 1", source)
        self.assertIn("op.execute(BACKFILL_SQL)", source)
        # On a fresh database 'DIV' is added to brokerage_event_kind in the same Alembic
        # transaction; comparing the enum column with a 'DIV' literal raises
        # UnsafeNewEnumValueUsageError, so kind must be compared as text.
        self.assertIn("be.kind::text IN ('TRADE_BUY', 'TRADE_SELL', 'DIV')", source)
        self.assertIn("CASE be.kind::text", source)
        self.assertNotIn("be.kind IN (", source)

    def test_cash_holdings_migration_reuses_instrument_currency_enum_and_guards_amount(self) -> None:
        source = _cash_holdings_migration_source()

        self.assertIn('"cash_holdings"', source)
        self.assertIn('name="instrument_currency_enum"', source)
        self.assertIn("create_type=False", source)
        self.assertIn('"PLN", "USD", "EUR", "GBP", "CHF"', source)
        self.assertIn('sa.CheckConstraint("amount >= 0", name="ck_cash_holding_amount_nonneg")', source)
        self.assertIn('sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"], ondelete="CASCADE")', source)

    def test_cash_snapshot_migration_keeps_original_currency_and_survives_holding_delete(self) -> None:
        source = _cash_snapshot_migration_source()

        self.assertIn('"cash_holding_monthly_snapshots"', source)
        self.assertIn('name="instrument_currency_enum"', source)
        self.assertIn("create_type=False", source)
        self.assertIn('sa.ForeignKeyConstraint(["cash_holding_id"], ["cash_holdings.id"], ondelete="SET NULL")', source)
        self.assertIn('sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"], ondelete="CASCADE")', source)
        self.assertIn('sa.UniqueConstraint("cash_holding_id", "month_key", name="uq_cash_monthly_snapshot")', source)

    def test_year_goal_migration_adds_capital_gain_target_with_default(self) -> None:
        source = _year_goal_capital_target_migration_source()

        self.assertIn('"capital_gain_target_year"', source)
        self.assertIn("sa.Numeric(precision=20, scale=2)", source)
        self.assertIn('server_default=sa.text("0.00")', source)
        self.assertIn("nullable=False", source)
