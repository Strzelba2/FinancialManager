from components.navbar_footer import nav
from components.wallet import render_create_wallet_dialog, render_delete_wallet_dialog
from components.account import render_create_account_dialog
from storage.session_state import get_current_user_id
from typing import Optional
import uuid
import logging

logger = logging.getLogger(__name__)


class NavContextBase:
    """
    Base context for navigation/UI actions.

    Responsibilities:
        - Provide ready-to-use openers for "create wallet" and "delete wallet" dialogs.
        - Render the top navigation bar.
        - Resolve the current user's UUID from `self.user_id` or a global accessor.

    """  
        
    def render_navbar(self):
        """
        Render the main navigation bar.
        """
        self.open_create_wallet_dialog = render_create_wallet_dialog(self)
        self.open_delete_wallet_dialog = render_delete_wallet_dialog(self)
        self.open_create_account_dialog = render_create_account_dialog(self)
        
        nav("User", self)
        
    def get_user_id(self) -> Optional[uuid.UUID]:
        """
        Resolve the current user's UUID.

        Returns:
            The user's UUID or None if not available/invalid.
        """
        uid = getattr(self, 'user_id', None)

        if uid:
            return uuid.UUID(str(uid))
        val = get_current_user_id()
        return uuid.UUID(str(val)) if val else None
    