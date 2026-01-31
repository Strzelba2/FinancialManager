from nicegui import ui
from decimal import Decimal
from datetime import datetime
from typing import Any, Optional
import logging

from utils.utils import to_uuid, parse_decimal
from .date import attach_date_time_popups

logger = logging.getLogger(__name__)


async def open_favorites_dialog(self, row: dict, mic: str) -> None:
    """
    Open a dialog to manage favorite lists and price alerts for a selected instrument.

    The dialog allows the user to:
      - Create/delete favorite lists
      - Add/remove the current instrument to/from lists
      - Create/update/delete a price alert for an instrument within a list

    Args:
        row: A row dict coming from a table/data source. Must include `symbol`.
        mic: Market Identifier Code (MIC) for the instrument (used when adding to favorites).

    Returns:
        None. This method renders and opens a NiceGUI dialog.
    """

    symbol = (row.get("symbol") or "").strip()
    name = (row.get("name") or "").strip()

    if not symbol:
        ui.notify("Missing symbol", type="negative")
        logger.warning("open_favorites_dialog: missing symbol in row")
        return

    try:
        user_id = to_uuid(self.get_user_id())
    except Exception:
        ui.notify("Missing user_id", type="negative")
        logger.exception("open_favorites_dialog: cannot resolve user_id from self.get_user_id()")
        return

    def _list_id(x: Any) -> str:
        """Extract list id from Pydantic model or dict-like response."""
        return str(getattr(x, "id", None) or (x.get("id") if isinstance(x, dict) else ""))

    def _list_name(x: Any) -> str:
        """Extract list name from Pydantic model or dict-like response."""
        return str(getattr(x, "name", None) or (x.get("name") if isinstance(x, dict) else "List"))

    def _list_desc(x: Any) -> str:
        """Extract list description from Pydantic model or dict-like response."""
        val = getattr(x, "description", None)
        if val is None and isinstance(x, dict):
            val = x.get("description")
        return str(val or "")

    def _item_symbol(item: dict) -> str:
        """Extract symbol from an item payload (supports item['symbol'] or item['instrument']['symbol'])."""
        if "symbol" in item:
            return str(item.get("symbol") or "")
        instr = item.get("instrument") or {}
        if isinstance(instr, dict):
            return str(instr.get("symbol") or "")
        return ""

    def _item_name(item: dict) -> str:
        """Extract name from an item payload (supports item['name'] or item['instrument']['name'])."""
        if "name" in item:
            return str(item.get("name") or "")
        instr = item.get("instrument") or {}
        if isinstance(instr, dict):
            return str(instr.get("name") or "")
        return ""

    def _item_alert(item: dict) -> Optional[dict]:
        """Extract alert payload (if present and dict-like)."""
        a = item.get("alert")
        return a if isinstance(a, dict) else None

    state = {"active_tab": None}

    dlg = ui.dialog()

    with dlg:
        with ui.card().style("""
            width: 980px;
            max-width: 95vw;
            border-radius: 24px;
            background: linear-gradient(180deg, #ffffff 0%, #f6f9ff 100%);
            box-shadow: 0 12px 30px rgba(15,23,42,.08);
            border: 1px solid rgba(15,23,42,.06);
            padding: 22px 22px 14px;
        """):

            with ui.row().classes("items-center q-gutter-md w-full"):
                ui.icon("sym_o_star").style("""
                    font-size: 38px;
                    color: #f59e0b;
                    background: #fef3c7;
                    padding: 14px;
                    border-radius: 50%;
                """)
                with ui.column().classes("q-gutter-xs"):
                    ui.label("Favorites & Alerts").classes("text-h5 text-weight-medium")
                    ui.label(f"{symbol} — {name or '—'}").classes("text-body2 text-grey-7")

            ui.separator().classes("q-my-md")

            root = ui.column().classes("w-full")

            with ui.row().classes("justify-end q-gutter-sm q-mt-md w-full"):
                ui.button("Close", on_click=dlg.close).props("no-caps").style("min-width: 110px; height: 40px;")

            async def _open_alert_editor(symbol_: str, initial_alert: Optional[dict] = None) -> None:
                """
                Open a dialog to create/update/delete a price alert for a symbol.

                Args:
                    symbol_: Instrument symbol to edit alert for (prefer normalized).
                    initial_alert: Existing alert payload if present.
                """
                adlg = ui.dialog()
                with adlg:
                    with ui.card().style("""
                        width: 560px;
                        max-width: 95vw;
                        border-radius: 18px;
                        padding: 18px 18px 14px;
                        background: #ffffff;
                        border: 1px solid rgba(148,163,184,.35);
                        box-shadow: 0 8px 20px rgba(15,23,42,.06);
                    """):
                        ui.label("Price alert").classes("text-h6 text-weight-medium")
                        ui.label(f"{symbol_ or '—'} — {name or '—'}").classes("text-caption text-grey-7")

                        ui.separator().classes("q-my-sm")

                        init_enabled = True
                        init_one_shot = False
                        init_below = None
                        init_above = None
                        init_expires = None

                        if initial_alert:
                            init_enabled = bool(initial_alert.get("enabled", True))
                            init_one_shot = bool(initial_alert.get("one_shot", False))
                            init_below = initial_alert.get("below_price")
                            init_above = initial_alert.get("above_price")
                            init_expires = initial_alert.get("expires_at")

                        enabled_cb = ui.checkbox("Enabled", value=init_enabled)
                        one_shot_cb = ui.checkbox("One-shot (disable after trigger)", value=init_one_shot)

                        with ui.row().classes("gap-3 w-full q-mt-sm"):
                            below_in = ui.input(label="Below price", placeholder="e.g. 100.00") \
                                .props("outlined dense clearable").classes("grow")
                            above_in = ui.input(label="Above price", placeholder="e.g. 120.00") \
                                .props("outlined dense clearable").classes("grow")

                        if init_below is not None:
                            below_in.value = str(init_below)
                        if init_above is not None:
                            above_in.value = str(init_above)

                        expires_in = ui.input("Expires at (optional)").props("outlined dense clearable").classes("w-full")
                        attach_date_time_popups(expires_in)
                        if init_expires:
                            expires_in.value = str(init_expires)

                        async def _save_alert() -> None:
                            """Validate inputs and upsert the alert."""
                            try:
                                below = parse_decimal(below_in.value)
                                above = parse_decimal(above_in.value)
                            except Exception:
                                ui.notify("Invalid price format", type="negative")
                                return

                            if below is None and above is None:
                                ui.notify("Provide below and/or above price", type="warning")
                                return
                            if below is not None and below < 0:
                                ui.notify("below_price must be >= 0", type="warning")
                                return
                            if above is not None and above < 0:
                                ui.notify("above_price must be >= 0", type="warning")
                                return
                            if below is not None and above is not None and below >= above:
                                ui.notify("below_price must be < above_price", type="warning")
                                return

                            expires_at = None
                            raw_exp = str(expires_in.value or "").strip()
                            if raw_exp:
                                try:
                                    expires_at = datetime.fromisoformat(raw_exp)
                                except Exception:
                                    ui.notify("Invalid expires_at datetime (use ISO format)", type="warning")
                                    return

                            res = await self.wallet_client.upsert_alert(
                                user_id=user_id,
                                symbol=symbol_,
                                below_price=below,
                                above_price=above,
                                enabled=bool(enabled_cb.value),
                                one_shot=bool(one_shot_cb.value),
                                expires_at=expires_at,
                            )
                            if not res:
                                ui.notify("Failed to save alert", type="negative")
                                return

                            ui.notify("Alert saved", type="positive")
                            adlg.close()
                            await _refresh()

                        async def _delete_alert() -> None:
                            """Delete the current alert for this symbol."""
                            ok = await self.wallet_client.delete_alert(user_id=user_id, symbol=symbol_)
                            ui.notify("Alert deleted" if ok else "Failed to delete alert",
                                      type="positive" if ok else "negative")
                            adlg.close()
                            await _refresh()

                        with ui.row().classes("justify-end q-gutter-sm q-mt-md w-full"):
                            if initial_alert:
                                ui.button("Delete", on_click=_delete_alert).props("no-caps flat color=negative")

                            ui.button("Cancel", on_click=adlg.close).props("no-caps flat")
                            ui.button("Save", on_click=_save_alert) \
                                .props("no-caps unelevated color=primary") \
                                .style("min-width: 120px; height: 40px;")

                adlg.open()

            async def _refresh() -> None:
                """
                Rebuild the dialog body:
                  - Load lists
                  - Load items-with-alerts per list
                  - Render tabs and per-list actions
                """
                root.clear()

                lists = await self.wallet_client.list_favorite_lists(user_id=user_id)
                lists = lists or []

                if not lists:
                    with root:
                        with ui.row().classes("items-center justify-center w-full text-grey-7").style("padding: 18px 0;"):
                            with ui.column().classes("items-center q-gutter-xs"):
                                ui.icon("sym_o_star_border").style("font-size: 40px; color: #94a3b8;")
                                ui.label("No favorite lists yet").classes("text-subtitle2 text-weight-medium")
                                ui.label("Create your first list to start saving instruments.").classes("text-caption")

                        ui.separator().classes("q-my-sm")

                        with ui.card().classes("w-full").style("""
                            border-radius: 16px;
                            border: 1px solid rgba(148,163,184,.35);
                            padding: 12px 12px 10px;
                            box-shadow: 0 4px 10px rgba(15,23,42,.03);
                        """):
                            ui.label("Create list").classes("text-subtitle1 text-weight-medium")

                            new_name = ui.input(label="List name *").props("outlined dense clearable").classes("w-full q-mt-sm")
                            new_desc = ui.input(label="Description (optional)").props("outlined dense clearable").classes("w-full")

                            async def _create_list() -> None:
                                nm = (new_name.value or "").strip()
                                if not nm:
                                    ui.notify("List name is empty", type="warning")
                                    return

                                created = await self.wallet_client.create_favorite_list(
                                    user_id=user_id,
                                    name=nm,
                                    description=(new_desc.value or "").strip() or None,
                                )
                                if not created:
                                    ui.notify("Failed to create list", type="negative")
                                    return

                                state["active_tab"] = str(getattr(created, "id", None) or created.get("id"))
                                ui.notify("List created", type="positive")
                                await _refresh()

                            with ui.row().classes("justify-end q-mt-sm"):
                                ui.button("Create", on_click=_create_list) \
                                    .props("unelevated color=primary no-caps") \
                                    .style("min-width: 120px; height: 40px;")

                    return

                items_by_list: dict[str, list[dict]] = {}
                list_ids: list[str] = []

                for lst in lists:
                    lid = _list_id(lst)
                    if not lid:
                        continue
                    list_ids.append(lid)

                    items = await self.wallet_client.list_favorite_items_with_alerts(
                        user_id=user_id,
                        list_id=to_uuid(lid),
                    )
                    items_by_list[lid] = items or []

                if not list_ids:
                    ui.notify("Favorites lists invalid (missing ids)", type="negative")
                    return

                if state.get("active_tab") not in list_ids:
                    state["active_tab"] = list_ids[0]

                active_tab = state["active_tab"]

                with root:

                    with ui.expansion("Add new list", icon="sym_o_add").classes("w-full").props("dense"):
                        with ui.card().classes("w-full").style("""
                            border-radius: 16px;
                            border: 1px solid rgba(148,163,184,.35);
                            padding: 12px 12px 10px;
                            box-shadow: 0 4px 10px rgba(15,23,42,.03);
                        """):
                            nm_in = ui.input(label="List name *").props("outlined dense clearable").classes("w-full")
                            ds_in = ui.input(label="Description (optional)").props("outlined dense clearable").classes("w-full")

                            async def _create_list_when_exists() -> None:
                                """
                                Create a new favorite list when lists already exist.

                                Validates name, calls backend, sets the newly created list as active tab,
                                and rerenders the dialog.
                                """
                                nm = (nm_in.value or "").strip()
                                if not nm:
                                    ui.notify("List name is empty", type="warning")
                                    return

                                created = await self.wallet_client.create_favorite_list(
                                    user_id=user_id,
                                    name=nm,
                                    description=(ds_in.value or "").strip() or None,
                                )
                                if not created:
                                    ui.notify("Failed to create list", type="negative")
                                    return

                                new_id = _list_id(created)
                                if new_id:
                                    state["active_tab"] = new_id

                                ui.notify("List created", type="positive")
                                await _refresh()

                            with ui.row().classes("justify-end q-mt-sm"):
                                ui.button("Create list", on_click=_create_list_when_exists) \
                                    .props("unelevated color=primary no-caps") \
                                    .style("min-width: 140px; height: 40px;")

                    ui.separator().classes("q-my-sm")

                    tabs = ui.tabs(value=active_tab).props("dense align=left").classes("w-full")

                    def _on_tab_change(e) -> None:
                        """
                        Persist current tab selection to local dialog state.
                        """
                        state["active_tab"] = str(e.args)

                    tabs.on("update:model-value", _on_tab_change)

                    with tabs:
                        for lst in lists:
                            lid = _list_id(lst)
                            if not lid:
                                continue
                            nm = _list_name(lst)
                            cnt = len(items_by_list.get(lid, []))
                            ui.tab(lid, label=f"{nm} ({cnt})")

                    panels = ui.tab_panels(tabs, value=active_tab).classes("w-full")

                    with panels:
                        for lst in lists:
                            lid = _list_id(lst)
                            if not lid:
                                continue

                            nm = _list_name(lst)
                            desc = _list_desc(lst)
                            items = items_by_list.get(lid, [])

                            in_this_list = any((_item_symbol(it) or "").upper() == symbol.upper() for it in items)

                            with ui.tab_panel(lid):

                                with ui.card().classes("w-full").style("""
                                    border-radius: 16px;
                                    border: 1px solid rgba(148,163,184,.35);
                                    padding: 12px 14px 10px;
                                    box-shadow: 0 4px 10px rgba(15,23,42,.03);
                                    margin-bottom: 10px;
                                """):
                                    with ui.row().classes("items-center justify-between w-full"):
                                        with ui.column().classes("q-gutter-xs"):
                                            ui.label(nm).classes("text-subtitle1 text-weight-medium")
                                            if desc:
                                                ui.label(desc).classes("text-caption text-grey-7")

                                        with ui.row().classes("items-center q-gutter-sm"):

                                            async def _add_current_to_this_list(list_id_=lid) -> None:
                                                """
                                                Add the currently selected instrument (symbol+mic) to this list.

                                                Args:
                                                    list_id_: Target list id (captured default prevents late-binding issues).
                                                """
                                                if in_this_list:
                                                    ui.notify("Already in this list", type="info")
                                                    return

                                                created = await self.wallet_client.add_favorite_item(
                                                    user_id=user_id,
                                                    list_id=to_uuid(list_id_),
                                                    symbol=symbol,
                                                    mic=mic,
                                                )
                                                if not created:
                                                    ui.notify("Failed to add instrument", type="negative")
                                                    return

                                                ui.notify("Added to favorites", type="positive")
                                                await _refresh()

                                            async def _remove_current_from_this_list(list_id_=lid) -> None:
                                                """
                                                Remove the currently selected instrument from this list.

                                                Also attempts to delete its alert (best-effort), then refreshes UI.

                                                Args:
                                                    list_id_: Target list id (captured default prevents late-binding issues).
                                                """
                                                if not in_this_list:
                                                    ui.notify("Not in this list", type="info")
                                                    return

                                                ok = await self.wallet_client.remove_favorite_item(
                                                    user_id=user_id,
                                                    list_id=to_uuid(list_id_),
                                                    symbol=symbol,
                                                )
                                                if not ok:
                                                    ui.notify("Failed to remove from list", type="negative")
                                                    return

                                                _ = await self.wallet_client.delete_alert(user_id=user_id, symbol=symbol)

                                                ui.notify("Removed (and alert deleted if existed)", type="positive")
                                                await _refresh()

                                            async def _delete_this_list(list_id_=lid) -> None:
                                                """
                                                Delete the selected favorite list after user confirmation.

                                                Args:
                                                    list_id_: Target list id (captured default prevents late-binding issues).
                                                """
                                                confirm = ui.dialog()
                                                decision = {"ok": False}

                                                with confirm:
                                                    with ui.card().style("""
                                                        width: 520px;
                                                        max-width: 95vw;
                                                        border-radius: 18px;
                                                        padding: 18px 18px 14px;
                                                        background: #ffffff;
                                                        border: 1px solid rgba(148,163,184,.35);
                                                        box-shadow: 0 8px 20px rgba(15,23,42,.06);
                                                    """):
                                                        ui.label("Delete list?").classes("text-h6 text-weight-medium")
                                                        ui.label(f"This will delete: {nm}").classes("text-body2 text-grey-7")
                                                        ui.separator().classes("q-my-sm")

                                                        def _cancel():
                                                            """Cancel deletion confirmation dialog."""
                                                            decision["ok"] = False
                                                            confirm.close()

                                                        def _ok():
                                                            """Confirm deletion in confirmation dialog."""
                                                            decision["ok"] = True
                                                            confirm.close()

                                                        with ui.row().classes("justify-end q-gutter-sm w-full"):
                                                            ui.button("Cancel", on_click=_cancel).props("no-caps flat")
                                                            ui.button("Delete", on_click=_ok).props("no-caps unelevated color=negative")

                                                confirm.open()
                                                await confirm

                                                if not decision["ok"]:
                                                    return

                                                ok = await self.wallet_client.delete_favorite_list(
                                                    user_id=user_id,
                                                    list_id=to_uuid(list_id_),
                                                )
                                                if not ok:
                                                    ui.notify("Failed to delete list", type="negative")
                                                    return

                                                ui.notify("List deleted", type="positive")

                                                if state.get("active_tab") == list_id_:
                                                    state["active_tab"] = None

                                                await _refresh()

                                            btn_add = ui.button("Add current", on_click=_add_current_to_this_list) \
                                                .props("no-caps unelevated color=primary dense") 
                                            
                                            if in_this_list:
                                                btn_add.disable()

                                            btn_rm = ui.button("Remove current", on_click=_remove_current_from_this_list) \
                                                .props("no-caps outline color=negative dense") 
                                                
                                            if not in_this_list:
                                                btn_rm.disable()

                                            ui.button("Delete list", on_click=_delete_this_list) \
                                                .props("no-caps flat dense color=negative")
                                if not items:
                                    with ui.row().classes("items-center justify-center w-full text-grey-7").style("padding: 16px 0;"):
                                        with ui.column().classes("items-center q-gutter-xs"):
                                            ui.icon("sym_o_playlist_add").style("font-size: 34px; color: #94a3b8;")
                                            ui.label("Empty list").classes("text-caption text-grey-6")
                                    continue

                                with ui.column().classes("w-full").style("max-height: 380px; overflow-y: auto; padding-right: 2px;"):
                                    for it in items:
                                        it_symbol = _item_symbol(it) or "—"
                                        it_name = _item_name(it) or "—"
                                        it_alert = _item_alert(it)

                                        alert_label = "No alert"
                                        if it_alert:
                                            en = bool(it_alert.get("enabled", True))
                                            below = it_alert.get("below_price")
                                            above = it_alert.get("above_price")
                                            parts = []
                                            if below is not None:
                                                parts.append(f"< {below}")
                                            if above is not None:
                                                parts.append(f"> {above}")
                                            alert_label = (" | ".join(parts) or "Alert") + (" (ON)" if en else " (OFF)")

                                        with ui.card().classes("w-full").style("""
                                            border-radius: 14px;
                                            border: 1px solid rgba(148,163,184,.30);
                                            padding: 10px 12px 10px;
                                            box-shadow: 0 2px 8px rgba(15,23,42,.03);
                                            margin-bottom: 8px;
                                        """):
                                            with ui.row().classes("items-center justify-between w-full"):
                                                with ui.column().classes("q-gutter-xs"):
                                                    ui.label(f"{it_symbol}").classes("text-subtitle2 text-weight-medium")
                                                    ui.label(it_name).classes("text-caption text-grey-7")

                                                    chip_color = "green" if it_alert and bool(it_alert.get("enabled", True)) else "grey"
                                                    ui.badge(alert_label).props(f"color={chip_color}").classes("q-mt-xs")

                                                with ui.row().classes("items-center q-gutter-sm"):

                                                    async def _manage_alert(symbol_=it_symbol, a=it_alert) -> None:
                                                        await _open_alert_editor(symbol_, initial_alert=a)

                                                    async def _remove_item(symbol_=it_symbol, list_id_=lid) -> None:
                                                        ok = await self.wallet_client.remove_favorite_item(
                                                            user_id=user_id,
                                                            list_id=to_uuid(list_id_),
                                                            symbol=symbol_,
                                                        )
                                                        if not ok:
                                                            ui.notify("Failed to remove from list", type="negative")
                                                            return

                                                        _ = await self.wallet_client.delete_alert(user_id=user_id, symbol=symbol_)
                                                        ui.notify("Removed (and alert deleted if existed)", type="positive")
                                                        await _refresh()

                                                    ui.button("Alert", on_click=_manage_alert).props("no-caps flat dense color=primary")
                                                    ui.button("Remove", on_click=_remove_item).props("no-caps flat dense color=negative")
            await _refresh()

    dlg.open()
