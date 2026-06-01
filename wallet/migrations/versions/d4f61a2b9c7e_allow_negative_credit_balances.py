"""allow negative credit account balances

Revision ID: d4f61a2b9c7e
Revises: c41b1cbad00f
Create Date: 2026-05-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d4f61a2b9c7e"
down_revision: Union[str, None] = "c41b1cbad00f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE deposit_account_balances "
        "DROP CONSTRAINT IF EXISTS ck_depaccbal_available_nonneg"
    )
    op.execute(
        "ALTER TABLE transactions "
        "DROP CONSTRAINT IF EXISTS ck_tx_balance_before_nonneg"
    )
    op.execute(
        "ALTER TABLE transactions "
        "DROP CONSTRAINT IF EXISTS ck_tx_balance_after_nonneg"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_deposit_account_balance_credit_policy()
        RETURNS trigger AS $$
        DECLARE
            account_kind account_type_enum;
        BEGIN
            SELECT account_type
            INTO account_kind
            FROM deposit_accounts
            WHERE id = NEW.account_id;

            IF NEW.available < 0
               AND account_kind IS DISTINCT FROM 'CREDIT'::account_type_enum THEN
                RAISE EXCEPTION
                    'Negative available balance is allowed only for CREDIT accounts.'
                    USING ERRCODE = '23514',
                          CONSTRAINT = 'ck_depaccbal_available_credit_only';
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_depaccbal_available_credit_only "
        "ON deposit_account_balances"
    )
    op.execute(
        """
        CREATE TRIGGER trg_depaccbal_available_credit_only
        BEFORE INSERT OR UPDATE OF available, account_id
        ON deposit_account_balances
        FOR EACH ROW
        EXECUTE FUNCTION enforce_deposit_account_balance_credit_policy()
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_transaction_balance_credit_policy()
        RETURNS trigger AS $$
        DECLARE
            account_kind account_type_enum;
        BEGIN
            SELECT account_type
            INTO account_kind
            FROM deposit_accounts
            WHERE id = NEW.account_id;

            IF (NEW.balance_before < 0 OR NEW.balance_after < 0)
               AND account_kind IS DISTINCT FROM 'CREDIT'::account_type_enum THEN
                RAISE EXCEPTION
                    'Negative transaction balance is allowed only for CREDIT accounts.'
                    USING ERRCODE = '23514',
                          CONSTRAINT = 'ck_tx_balances_credit_only';
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_tx_balances_credit_only ON transactions"
    )
    op.execute(
        """
        CREATE TRIGGER trg_tx_balances_credit_only
        BEFORE INSERT OR UPDATE OF balance_before, balance_after, account_id
        ON transactions
        FOR EACH ROW
        EXECUTE FUNCTION enforce_transaction_balance_credit_policy()
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_deposit_account_type_credit_policy()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.account_type IS DISTINCT FROM 'CREDIT'::account_type_enum
               AND (
                   EXISTS (
                       SELECT 1
                       FROM deposit_account_balances
                       WHERE account_id = NEW.id
                         AND available < 0
                   )
                   OR EXISTS (
                       SELECT 1
                       FROM transactions
                       WHERE account_id = NEW.id
                         AND (balance_before < 0 OR balance_after < 0)
                   )
               ) THEN
                RAISE EXCEPTION
                    'Account type cannot be changed while CREDIT-only negative balances exist.'
                    USING ERRCODE = '23514',
                          CONSTRAINT = 'ck_depacc_account_type_credit_only';
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_depacc_account_type_credit_only ON deposit_accounts"
    )
    op.execute(
        """
        CREATE TRIGGER trg_depacc_account_type_credit_only
        BEFORE UPDATE OF account_type
        ON deposit_accounts
        FOR EACH ROW
        EXECUTE FUNCTION enforce_deposit_account_type_credit_policy()
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM deposit_account_balances
                WHERE available < 0
            ) OR EXISTS (
                SELECT 1
                FROM transactions
                WHERE balance_before < 0 OR balance_after < 0
            ) THEN
                RAISE EXCEPTION
                    'Cannot downgrade: CREDIT-only negative balances exist. '
                    'Resolve them before restoring global non-negative constraints.';
            END IF;
        END;
        $$
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_depacc_account_type_credit_only ON deposit_accounts"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS enforce_deposit_account_type_credit_policy()"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_tx_balances_credit_only ON transactions"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS enforce_transaction_balance_credit_policy()"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_depaccbal_available_credit_only "
        "ON deposit_account_balances"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS enforce_deposit_account_balance_credit_policy()"
    )
    op.create_check_constraint(
        "ck_depaccbal_available_nonneg",
        "deposit_account_balances",
        "available >= 0",
    )
    op.create_check_constraint(
        "ck_tx_balance_before_nonneg",
        "transactions",
        "balance_before >= 0",
    )
    op.create_check_constraint(
        "ck_tx_balance_after_nonneg",
        "transactions",
        "balance_after >= 0",
    )
