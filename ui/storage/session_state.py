
from typing import Dict, Optional, List, TypedDict
from nicegui import app
from nicegui.observables import ObservableDict
from schemas.wallet import WalletListItem
import logging

logger = logging.getLogger(__name__)

_STATE_KEY = "state" 


class SessionState(TypedDict, total=False):
    user_id: Optional[str] = None
    wallets: Dict[str, WalletListItem] = {}
    
    
DEFAULT_STATE: SessionState = {"user_id": None, "wallets": {}}
    
    
# ---------- Accessors ----------

def get_state() -> SessionState:
    """Get or create the per-user SessionState object."""
    state = app.storage.user.get(_STATE_KEY)
    if state is None:
        state = DEFAULT_STATE.copy()
        app.storage.user[_STATE_KEY] = state
        logger.debug("Created new SessionState for user storage")

    return app.storage.user.get(_STATE_KEY)


def set_state(state: ObservableDict) -> None:
    """Replace the entire state (rarely needed)."""
    app.storage.user[_STATE_KEY] = state
    logger.debug("SessionState replaced in user storage")


def clear_state() -> None:
    """Remove SessionState from user storage (e.g., on logout)."""
    app.storage.user.pop(_STATE_KEY, None)
    logger.debug("SessionState cleared from user storage")
    
    
# ---------- User helpers ----------

def get_current_user_id() -> Optional[str]:
    """Return user_id from SessionState, falling back to your _CURRENT_USER_KEY cache."""
    return get_state().get("user_id")


def set_current_user_id(user_id: Optional[str]) -> None:
    """Update user info in SessionState (non-sensitive only)."""
    state = get_state()
    state["user_id"] = user_id
    logger.debug(f"SessionState user set: user_id={user_id}")

    
def clear_current_user() -> None:
    """Clear only the user fields (not the whole state)."""
    state = get_state()
    state.user_id = None
    logger.debug("SessionState user fields cleared")
    
    
# ---------- Wallet helpers (small, shareable across pages) ----------

def list_wallets() -> List[WalletListItem]:
    """Return the wallets as a list (stable order not guaranteed)."""
    state = get_state()
    return list(state["wallets"].values())


def get_wallet(wallet_id: str) -> Optional[WalletListItem]:
    state = get_state()
    return state["wallets"].get(wallet_id)


def upsert_wallet(wallet: WalletListItem) -> WalletListItem:
    state = get_state()
    wallets: dict[str, WalletListItem] = state.setdefault("wallets", {})
    wallets[wallet.id] = wallet
    return wallets[wallet.id]


def rename_wallet(wallet_id: str, new_name: str) -> bool:
    w = get_wallet(wallet_id)
    if not w:
        return False
    if w.name == new_name:
        return True
    w.name = new_name
    return True


def remove_wallet(wallet_id: str) -> bool:
    wallets = get_state().get("wallets", {})
    return wallets.pop(wallet_id, None) is not None
 
 
def set_wallets_from_payload(payload: List[WalletListItem]) -> None:
    logger.info(f"payload: {payload}")
    state = get_state()
    state["wallets"] = {
        str(w.id): w
        for w in payload if "id" in w
    }
