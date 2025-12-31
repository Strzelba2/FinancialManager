from playwright.async_api import Page, Frame, TimeoutError as PWTimeout
import asyncio
import logging

from app.utils.regex_check import BUTTON_RX_ACCEPT, BUTTON_RX_REJECT

logger = logging.getLogger(__name__)


async def click_first_matching(frame: Frame, accept_first: bool = True) -> bool:
    """
    Try clicking a matching consent button in a specific frame.

    The function searches for cookie/consent buttons using Playwright locators:
    1. First tries explicit role="button" with the given text/regex.
    2. Then falls back to a broader locator (a, button, [role=button], etc.)
       filtered by text.

    Args:
        frame: Playwright frame in which to search for the button.
        accept_first: If True, try "accept" patterns first, then "reject".
                      If False, invert the order (reject first).

    Returns:
        True if a matching button was found and clicked; False otherwise.
    """
    logger.info(
        f"click_first_matching: starting search in frame={frame}, "
        f"accept_first={accept_first}"
    )
    
    patterns = [BUTTON_RX_ACCEPT, BUTTON_RX_REJECT] if accept_first else [BUTTON_RX_REJECT, BUTTON_RX_ACCEPT]
    for rx in patterns:
        logger.debug(
            f"click_first_matching: trying pattern {rx!r} on role=button in frame={frame}"
        )
        btns = frame.get_by_role("button", name=rx)
        if await btns.count():
            try:
                await btns.first.click(timeout=1500)
                return True
            except PWTimeout:
                logger.warning(
                    f"click_first_matching: timeout clicking role=button "
                    f"for pattern={rx!r}"
                )

        locator = frame.locator("a, button, [role=button], .fc-button, .fc-cta, .ot-sdk-container *")
        candidate = locator.filter(has_text=rx).first
        if await candidate.count():
            try:
                await candidate.click(timeout=1500)
                return True
            except PWTimeout:
                logger.warning(
                    f"click_first_matching: timeout clicking generic locator "
                    f"for pattern={rx!r}"
                )
                
    logger.info(f"click_first_matching: no matching button found in frame={frame}")
    return False


async def dismiss_cookies_if_present(page: Page, prefer_reject: bool = False, overall_timeout_ms: int = 6000) -> bool:
    """
    Attempt to dismiss cookie/consent dialogs on a page.

    The function:
    - Tries to click consent buttons across all frames within a time budget.
    - Uses `click_first_matching` on main frame first, then on all other frames.
    - Optionally prefers "reject" buttons over "accept" buttons.
    - If no matching element is found, sends an Escape keypress as a fallback.

    Args:
        page: Playwright `Page` instance to operate on.
        prefer_reject: If True, try reject patterns before accept patterns.
        overall_timeout_ms: Maximum time to keep searching (in milliseconds).

    Returns:
        True if any cookie/consent button was clicked; False otherwise.
    """
    logger.info(
        f"dismiss_cookies_if_present: started for page={page}, "
        f"prefer_reject={prefer_reject}, overall_timeout_ms={overall_timeout_ms}"
    )
    deadline = page.context._loop.time() + (overall_timeout_ms / 1000.0)
    clicked_any = False

    async def try_everywhere() -> bool:
        logger.debug("dismiss_cookies_if_present: trying main_frame")
        if await click_first_matching(page.main_frame, accept_first=not prefer_reject):
            return True
        
        logger.debug("dismiss_cookies_if_present: trying all child frames")
        for fr in page.frames:
            if fr == page.main_frame:
                continue
            if await click_first_matching(fr, accept_first=not prefer_reject):
                return True
        return False

    while page.context._loop.time() < deadline:
        if await try_everywhere():
            clicked_any = True
            logger.info("dismiss_cookies_if_present: clicked a consent button")
            break
        await asyncio.sleep(0.25)

    if not clicked_any:
        try:
            await page.keyboard.press("Escape")
        except Exception as e:
            logger.warning(
                f"dismiss_cookies_if_present: failed to send Escape key: {e}"
            )
    return clicked_any
