import logging
from typing import Optional
from fastapi import Request
from pydantic import ValidationError
from nicegui import app
from schemas.session import SessionUser  

logger = logging.getLogger(__name__)


_CURRENT_USER_KEY = "current_user"


async def get_current_user_or_create(
    request: Request,
    use_cache: bool = True,
) -> Optional[SessionUser]:
    """
    Retrieve the current logged-in user from session storage or cache.

    This function first checks the user cache in `app.storage.user`.  
    If not found or invalid, it loads session data from Redis (via `app.storage.session`)  
    using the `sessionid` cookie and validates it as a `SessionUser`.

    - If validation succeeds → user is cached locally and returned.
    - If validation fails → the invalid session is deleted.
    - If no session exists → returns None.

    Args:
        request: Incoming HTTP request containing the `sessionid` cookie.
        use_cache: Whether to try reading the cached user from `app.storage.user`.

    Returns:
        A validated `SessionUser` instance if found and valid, otherwise `None`.
    """

    if use_cache:
        cached = app.storage.user.get(_CURRENT_USER_KEY)
        if cached:
            try:
                return SessionUser.model_validate(cached)
            except ValidationError:
                logger.warning("Cached user data is invalid, clearing cache.")
                app.storage.user.pop(_CURRENT_USER_KEY, None)

    sessionid = request.cookies.get("sessionid")
    if not sessionid:
        logger.debug("No 'sessionid' cookie found in request.")
        return None

    try:
        raw = await app.storage.session.get(sessionid)
        logger.info(raw)
    except Exception as e:
        logger.exception(f"Session backend error while reading session {sessionid}: {e}")
        return None

    if not raw:
        logger.debug("Brak danych sesji w Redis dla klucza %s", sessionid)
        return None

    try:
        user = SessionUser.model_validate(raw)
        logger.info(f"Validated session user: {user.first_name}")
    except ValidationError as e:
        logger.error(f"Invalid session data format: {e}")
        return None

    try:
        app.storage.user[_CURRENT_USER_KEY] = user.model_dump()
        logger.debug("User cached successfully in app.storage.user.")
    except Exception as e:
        logger.warning(f"Failed to cache user in app.storage.user: {e}")
        
    try:
        await app.storage.session.clear(sessionid)
        logger.debug(f"Deleted session key from Redis: {sessionid}")
    except Exception as e:
        logger.warning(f"Failed to delete session key {sessionid}: {e}")

    return user


def get_username() -> str:
    """
    Retrieve the current cached user's first name.

    Returns:
        The first name of the user if available, otherwise `None`.
    """
    user_data = app.storage.user.get(_CURRENT_USER_KEY)
    if user_data:
        return user_data.get("first_name", "")
    return None


def clear_current_user_cache() -> None:
    """
    Clears the cached current user from local storage.
    Useful when logging out or resetting the session manually.
    """
    app.storage.user.pop(_CURRENT_USER_KEY, None)
