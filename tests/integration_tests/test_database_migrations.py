from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any

import allure
import psycopg
from psycopg import sql
import pytest

REVISION_RE = re.compile(
    r"^revision\s*:\s*str\s*=\s*['\"]([^'\"]+)['\"]|^revision\s*=\s*['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)
DOWN_REVISION_RE = re.compile(
    r"^down_revision\s*:\s*[^=]+=\s*(.+)$|^down_revision\s*=\s*(.+)$",
    re.MULTILINE,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _literal_or_none(value: str) -> Any:
    value = value.strip()
    if value in {"None", "null"}:
        return None
    return ast.literal_eval(value)


def _migration_heads(versions_dir: Path) -> set[str]:
    revisions: set[str] = set()
    down_revisions: set[str] = set()

    for migration_file in versions_dir.glob("*.py"):
        text = migration_file.read_text(encoding="utf-8")
        revision_match = REVISION_RE.search(text)
        if not revision_match:
            continue

        revision = next(group for group in revision_match.groups() if group)
        revisions.add(revision)

        down_revision_match = DOWN_REVISION_RE.search(text)
        if not down_revision_match:
            continue

        raw_down_revision = next(group for group in down_revision_match.groups() if group)
        parsed_down_revision = _literal_or_none(raw_down_revision)
        if isinstance(parsed_down_revision, str):
            down_revisions.add(parsed_down_revision)
        elif isinstance(parsed_down_revision, tuple):
            down_revisions.update(item for item in parsed_down_revision if isinstance(item, str))

    heads = revisions - down_revisions
    if not heads:
        raise AssertionError(f"No Alembic migration heads detected in {versions_dir}")
    return heads


def _database_alembic_versions(host: str, database: str) -> set[str]:
    with psycopg.connect(
        host=host,
        port=int(os.environ.get("TEST_POSTGRES_PORT", "5432")),
        dbname=database,
        user=os.environ.get("TEST_POSTGRES_USER", "myuser"),
        password=os.environ.get("TEST_POSTGRES_PASSWORD", "mypassword"),
        connect_timeout=5,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select version_num from alembic_version")
            return {row[0] for row in cursor.fetchall()}


def _database_tables(host: str, database: str) -> set[str]:
    with psycopg.connect(
        host=host,
        port=int(os.environ.get("TEST_POSTGRES_PORT", "5432")),
        dbname=database,
        user=os.environ.get("TEST_POSTGRES_USER", "myuser"),
        password=os.environ.get("TEST_POSTGRES_PASSWORD", "mypassword"),
        connect_timeout=5,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select table_name
                from information_schema.tables
                where table_schema = 'public'
                  and table_type = 'BASE TABLE'
                """
            )
            return {row[0] for row in cursor.fetchall()}


def _database_counts(host: str, database: str, tables: set[str]) -> dict[str, int]:
    with psycopg.connect(
        host=host,
        port=int(os.environ.get("TEST_POSTGRES_PORT", "5432")),
        dbname=database,
        user=os.environ.get("TEST_POSTGRES_USER", "myuser"),
        password=os.environ.get("TEST_POSTGRES_PASSWORD", "mypassword"),
        connect_timeout=5,
    ) as connection:
        with connection.cursor() as cursor:
            counts: dict[str, int] = {}
            for table in sorted(tables):
                cursor.execute(
                    sql.SQL("select count(*) from {}").format(sql.Identifier(table))
                )
                counts[table] = cursor.fetchone()[0]
            return counts


def _database_constraints(host: str, database: str, tables: set[str]) -> set[str]:
    with psycopg.connect(
        host=host,
        port=int(os.environ.get("TEST_POSTGRES_PORT", "5432")),
        dbname=database,
        user=os.environ.get("TEST_POSTGRES_USER", "myuser"),
        password=os.environ.get("TEST_POSTGRES_PASSWORD", "mypassword"),
        connect_timeout=5,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select constraint_name
                from information_schema.table_constraints
                where table_schema = 'public'
                  and table_name = any(%s)
                """,
                (list(tables),),
            )
            return {row[0] for row in cursor.fetchall()}


def _database_foreign_key_edges(host: str, database: str) -> set[tuple[str, str]]:
    with psycopg.connect(
        host=host,
        port=int(os.environ.get("TEST_POSTGRES_PORT", "5432")),
        dbname=database,
        user=os.environ.get("TEST_POSTGRES_USER", "myuser"),
        password=os.environ.get("TEST_POSTGRES_PASSWORD", "mypassword"),
        connect_timeout=5,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select source.relname as source_table, target.relname as target_table
                from pg_constraint constraint_data
                join pg_class source on source.oid = constraint_data.conrelid
                join pg_namespace source_namespace
                  on source_namespace.oid = source.relnamespace
                join pg_class target on target.oid = constraint_data.confrelid
                join pg_namespace target_namespace
                  on target_namespace.oid = target.relnamespace
                where constraint_data.contype = 'f'
                  and source_namespace.nspname = 'public'
                  and target_namespace.nspname = 'public'
                """
            )
            return {(row[0], row[1]) for row in cursor.fetchall()}


def _expected_django_migrations(migrations_dir: Path) -> set[str]:
    migration_names = {
        migration_file.stem
        for migration_file in migrations_dir.glob("*.py")
        if migration_file.name != "__init__.py"
    }
    if not migration_names:
        raise AssertionError(f"No Django migrations detected in {migrations_dir}")
    return migration_names


def _database_django_migrations(host: str, database: str, app_name: str) -> set[str]:
    with psycopg.connect(
        host=host,
        port=int(os.environ.get("TEST_POSTGRES_PORT", "5432")),
        dbname=database,
        user=os.environ.get("TEST_POSTGRES_USER", "myuser"),
        password=os.environ.get("TEST_POSTGRES_PASSWORD", "mypassword"),
        connect_timeout=5,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "select name from django_migrations where app = %s",
                (app_name,),
            )
            return {row[0] for row in cursor.fetchall()}


@pytest.mark.integration
@pytest.mark.db
@allure.epic("System Tests")
@allure.feature("Integration")
@allure.story("Session test database is migrated with the current Django app migrations")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("database", "migration", "session")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
def test_session_database_is_migrated_to_current_django_migrations() -> None:
    migrations_dir = _repo_root() / "session" / "userauth" / "migrations"
    expected_migrations = _expected_django_migrations(migrations_dir)

    with allure.step("Read session Django migration table"):
        actual_migrations = _database_django_migrations(
            host="session-db",
            database="session_test",
            app_name="userauth",
        )

    assert expected_migrations <= actual_migrations


@pytest.mark.integration
@pytest.mark.db
@allure.epic("System Tests")
@allure.feature("Integration")
@allure.story("Wallet and stock test databases are migrated to the current Alembic heads")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("database", "migration", "wallet", "stock")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@pytest.mark.parametrize(
    ("service_name", "host", "database", "versions_dir"),
    [
        ("wallet", "wallet-db", "Wallet_test", _repo_root() / "wallet" / "migrations" / "versions"),
        ("stock", "stock-db", "stock_test", _repo_root() / "stock" / "migrations" / "versions"),
    ],
)
def test_service_database_is_migrated_to_current_head(
    service_name: str,
    host: str,
    database: str,
    versions_dir: Path,
) -> None:
    expected_heads = _migration_heads(versions_dir)

    with allure.step(f"Read {service_name} Alembic version table"):
        actual_versions = _database_alembic_versions(host, database)

    assert actual_versions == expected_heads


@pytest.mark.integration
@pytest.mark.db
@allure.epic("System Tests")
@allure.feature("Integration")
@allure.story("Test databases expose the expected migrated business tables")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("database", "migration", "schema", "session", "wallet", "stock")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@pytest.mark.parametrize(
    ("service_name", "host", "database", "expected_tables"),
    [
        (
            "session",
            "session-db",
            "session_test",
            {
                "userauth_user",
                "userauth_blockedip",
                "userauth_userkeys",
                "django_migrations",
                "django_session",
            },
        ),
        (
            "wallet",
            "wallet-db",
            "Wallet_test",
            {
                "users",
                "wallets",
                "banks",
                "deposit_accounts",
                "transactions",
                "brokerage_accounts",
                "brokerage_events",
                "holdings",
                "favorite_lists",
                "favorite_items",
                "price_alerts",
            },
        ),
        (
            "stock",
            "stock-db",
            "stock_test",
            {
                "market",
                "instrument",
                "quote_latest",
                "candle_daily",
                "instrument_sync_state",
                "report_ai_snapshot",
                "report_snapshot",
            },
        ),
    ],
)
def test_test_database_contains_expected_business_tables(
    service_name: str,
    host: str,
    database: str,
    expected_tables: set[str],
) -> None:
    with allure.step(f"Read migrated tables for {service_name}"):
        actual_tables = _database_tables(host, database)

    assert expected_tables <= actual_tables


@pytest.mark.integration
@pytest.mark.db
@allure.epic("System Tests")
@allure.feature("Integration")
@allure.story("Test databases start without persisted business records")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("database", "clean-state", "session", "wallet", "stock")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@pytest.mark.parametrize(
    ("service_name", "host", "database", "empty_tables"),
    [
        (
            "session",
            "session-db",
            "session_test",
            {"userauth_user", "userauth_blockedip", "userauth_userkeys"},
        ),
        (
            "wallet",
            "wallet-db",
            "Wallet_test",
            {
                "users",
                "wallets",
                "deposit_accounts",
                "transactions",
                "brokerage_accounts",
                "holdings",
                "favorite_lists",
                "favorite_items",
                "price_alerts",
            },
        ),
        (
            "stock",
            "stock-db",
            "stock_test",
            {
                "instrument",
                "quote_latest",
                "candle_daily",
                "instrument_sync_state",
                "report_ai_snapshot",
                "report_snapshot",
            },
        ),
    ],
)
def test_test_database_starts_without_business_rows(
    service_name: str,
    host: str,
    database: str,
    empty_tables: set[str],
) -> None:
    with allure.step(f"Count business rows for {service_name}"):
        table_counts = _database_counts(host, database, empty_tables)

    assert table_counts == {table: 0 for table in empty_tables}


@pytest.mark.integration
@pytest.mark.db
@allure.epic("System Tests")
@allure.feature("Integration")
@allure.story("Wallet and stock databases keep key business constraints")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("database", "constraints", "wallet", "stock")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@pytest.mark.parametrize(
    ("service_name", "host", "database", "tables", "expected_constraints"),
    [
        (
            "wallet",
            "wallet-db",
            "Wallet_test",
            {
                "wallets",
                "transactions",
                "holdings",
                "favorite_lists",
                "favorite_items",
                "price_alerts",
            },
            {
                "uq_wallet_owner_name",
                "uq_fav_list_user_name",
                "uq_fav_item_unique",
                "uq_alert_user_instr",
                "ck_alert_prices_nonneg",
            },
        ),
        (
            "stock",
            "stock-db",
            "stock_test",
            {"instrument", "report_ai_snapshot", "report_snapshot"},
            {
                "uq_instrument_symbol",
                "uq_report_ai_snapshot_business_key",
                "uq_report_snapshot_business_key",
            },
        ),
    ],
)
def test_service_database_has_core_business_constraints(
    service_name: str,
    host: str,
    database: str,
    tables: set[str],
    expected_constraints: set[str],
) -> None:
    with allure.step(f"Read business constraints for {service_name}"):
        actual_constraints = _database_constraints(host, database, tables)

    assert expected_constraints <= actual_constraints


@pytest.mark.integration
@pytest.mark.db
@allure.epic("System Tests")
@allure.feature("Integration")
@allure.story("Service databases keep required foreign-key relationships")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("database", "foreign-key", "session", "wallet", "stock")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@pytest.mark.parametrize(
    ("service_name", "host", "database", "expected_edges"),
    [
        (
            "session",
            "session-db",
            "session_test",
            {("userauth_userkeys", "userauth_user")},
        ),
        (
            "wallet",
            "wallet-db",
            "Wallet_test",
            {
                ("wallets", "users"),
                ("deposit_accounts", "wallets"),
                ("transactions", "deposit_accounts"),
                ("favorite_lists", "users"),
                ("favorite_items", "favorite_lists"),
                ("favorite_items", "instruments"),
            },
        ),
        (
            "stock",
            "stock-db",
            "stock_test",
            {
                ("instrument", "market"),
                ("quote_latest", "instrument"),
                ("candle_daily", "instrument"),
                ("report_snapshot", "instrument"),
            },
        ),
    ],
)
def test_service_database_has_required_foreign_keys(
    service_name: str,
    host: str,
    database: str,
    expected_edges: set[tuple[str, str]],
) -> None:
    with allure.step(f"Read foreign-key edges for {service_name}"):
        actual_edges = _database_foreign_key_edges(host, database)

    assert expected_edges <= actual_edges
