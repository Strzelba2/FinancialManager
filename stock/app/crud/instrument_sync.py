from datetime import date, datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Final

from app.models.models import InstrumentSyncState

_DAILY_ERROR_MAX_LEN: Final[int] = 2000


async def get_or_create_sync_state(
    session: AsyncSession,
    instrument_id,
) -> InstrumentSyncState:
    """
    Get the per-instrument sync state row or create it if it doesn't exist.

    This helper ensures there is always an `InstrumentSyncState` record for the
    given instrument. It flushes the session so the new row becomes visible
    within the current transaction (without committing).

    Args:
        session: SQLAlchemy async database session.
        instrument_id: Primary key of the instrument (used as PK of InstrumentSyncState).

    Returns:
        The existing or newly created `InstrumentSyncState` instance.
    """
    state = await session.get(InstrumentSyncState, instrument_id)
    if state is None:
        state = InstrumentSyncState(instrument_id=instrument_id)
        session.add(state)
        await session.flush()
    return state


def should_skip_daily_sync(
    state: InstrumentSyncState,
    today: date,
    target_end: date,
    min_retry_minutes_on_error: int = 10,
) -> bool:
    """
    Decide whether a daily candle sync should be skipped for a given target_end.

    The function skips syncing when:
      1) The last successful sync already reached `target_end`.
      2) A sync attempt for `target_end` already happened today and did not error.
      3) The last attempt for `target_end` errored, but the cooldown window has not passed.

    Args:
        state: Instrument sync state row.
        today: Current date (UTC date recommended, consistent with stored timestamps).
        target_end: Desired end date for the daily sync window.
        min_retry_minutes_on_error: Cooldown (minutes) before retrying after an error.

    Returns:
        True if the sync should be skipped, otherwise False.
    """
    success_has_rows = (state.daily_last_fetched_rows or 0) > 0
    same_target_success = state.daily_last_success_end == target_end

    # Older buggy runs could mark success for an empty/non-CSV response.
    # Treat that state as invalid so the next request can retry.
    if same_target_success and success_has_rows:
        return True

    if same_target_success and not success_has_rows:
        return False

    if (
        state.daily_last_attempt_end == target_end
        and state.daily_last_attempt_at is not None
        and state.daily_last_attempt_at.date() == today
        and not state.daily_last_error
    ):
        return True

    if (
        state.daily_last_attempt_end == target_end
        and state.daily_last_attempt_at is not None
        and state.daily_last_error
    ):
        now = datetime.now(timezone.utc)
        if now - state.daily_last_attempt_at < timedelta(minutes=min_retry_minutes_on_error):
            return True

    return False


async def mark_daily_attempt(
    session: AsyncSession,
    state: InstrumentSyncState,
    now: datetime,
    target_end: date,
    requested_url: str,
) -> None:
    """
    Mark the beginning of a daily sync attempt.

    This updates attempt metadata and clears any previous `daily_last_error`.
    The function flushes the session (without committing).

    Args:
        session: SQLAlchemy async database session.
        state: Sync state row to update.
        now: Attempt timestamp (UTC recommended).
        target_end: Requested end date for the daily sync window.
        requested_url: Source URL used for fetching daily candles.
    """
    state.daily_last_attempt_at = now
    state.daily_last_attempt_end = target_end
    state.daily_last_requested_url = requested_url
    state.daily_last_fetched_rows = None
    state.daily_last_upserted_rows = None
    state.daily_last_error = None
    await session.flush()


async def mark_daily_success(
    session: AsyncSession,
    state: InstrumentSyncState,
    now: datetime,
    target_end: date,
    fetched_rows: int,
    upserted_rows: int,
) -> None:
    """
    Mark a daily sync attempt as successful.

    Stores the last successful end date and row counts, clears errors, and flushes
    the session (without committing).

    Args:
        session: SQLAlchemy async database session.
        state: Sync state row to update.
        now: Success timestamp (UTC recommended).
        target_end: End date reached by the successful sync.
        fetched_rows: Number of rows fetched from the remote source.
        upserted_rows: Number of rows inserted/updated in the database.
    """
    state.daily_last_success_at = now
    state.daily_last_success_end = target_end
    state.daily_last_fetched_rows = fetched_rows
    state.daily_last_upserted_rows = upserted_rows
    state.daily_last_error = None
    await session.flush()
    

async def mark_daily_failure(
    session: AsyncSession,
    state: InstrumentSyncState,
    error: object,
) -> None:
    """
    Mark a daily sync attempt as failed.

    The error message is truncated to a safe length and written to the state row.
    The function flushes the session (without committing).

    Args:
        session: SQLAlchemy async database session.
        state: Sync state row to update.
        error: Error message to store (will be truncated).
    """
    trimmed = str(error or "")[:_DAILY_ERROR_MAX_LEN]

    state.daily_last_error = trimmed
    await session.flush()
