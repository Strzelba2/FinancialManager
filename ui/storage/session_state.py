
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


def get_current_user_id() -> Optional[str]:
    """Return user_id from SessionState, falling back to your _CURRENT_USER_KEY cache."""
    return get_state().get("user_id")


def set_current_user_id(user_id: Optional[str]) -> None:
    """Update user info in SessionState (non-sensitive only)."""
    state = get_state()
    state["user_id"] = user_id
    set_state(state)
    logger.debug(f"SessionState user set: user_id={user_id}")
  
   
def clear_current_user() -> None:
    """Clear only the user fields (not the whole state)."""
    state = get_state()
    state.user_id = None
    set_state(state)
    logger.debug("SessionState user fields cleared")
    

def list_wallets() -> List[str]:
    """Return the wallets as a list (stable order not guaranteed)."""
    state = get_state()
    return list(state["wallets"].values())


def get_wallets() -> Dict[str, str]:
    state = get_state()
    return state["wallets"]


def get_wallet(wallet_id: str) -> Optional[str]:
    state = get_state()
    return state["wallets"].get(wallet_id)


def upsert_wallet(wallet: WalletListItem) -> str:
    """
    Insert or update a wallet in the mapping, persisting the change.
    Returns the (string) wallet name.
    """
    state = get_state()
    wallets = state.get("wallets") or {}
    wallet_id = str(wallet.id)
    wallet_name = str(wallet.name)
    wallets[wallet_id] = wallet_name
    state["wallets"] = wallets
    set_state(state)
    return wallet_name


def rename_wallet(wallet_id: str, new_name: str) -> bool:
    """Rename an existing wallet and persist. Returns True if it existed."""
    state = get_state()
    wallets = state.get("wallets") or {}
    if wallet_id not in wallets:
        return False
    if wallets[wallet_id] == new_name:
        return True
    wallets[wallet_id] = new_name
    state["wallets"] = wallets
    set_state(state)
    return True


def remove_wallet(wallet_id: str) -> bool:
    """Remove a wallet by id and persist. Returns True if removed."""
    state = get_state()
    wallets = state.get("wallets") or {}
    existed = wallet_id in wallets
    if existed:
        wallets.pop(wallet_id, None)
        state["wallets"] = wallets
        set_state(state)
    return existed
 
 
def set_wallets_from_payload(payload: List[WalletListItem]) -> None:
    wallets_map = {
        str(w.id): str(w.name)
        for w in payload
        if getattr(w, "id", None) is not None and getattr(w, "name", None)
    }
    state = get_state()
    state["wallets"] = wallets_map
    set_state(state)
