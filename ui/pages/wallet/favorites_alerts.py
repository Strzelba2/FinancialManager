from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import Request
from nicegui import ui, app

from static.style import add_style, add_user_style, add_table_style
from components.context.nav_context import NavContextBase
from components.navbar_footer import footer
from clients.stock_client import StockClient
from clients.wallet_client import WalletClient
from schemas.quotes import QuoteRow
from utils.utils import to_uuid, parse_decimal
from utils.dates import TZ
from components.date import attach_date_time_popups

logger = logging.getLogger(__name__)


def _safe_dec_str(v: Any) -> str:
    """Render Decimal/str/None nicely for table cells."""
    if v is None:
        return "—"
    s = str(v).strip()
    return s if s else "—"


def _fmt_dt(v: Any) -> str:
    """Pretty datetime string for expires_at etc."""
    if not v:
        return "—"
    try:
        if isinstance(v, datetime):
            return v.strftime("%Y-%m-%d %H:%M")
        s = str(v)
        dt = datetime.fromisoformat(s)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(v)


class FavoritesAlerts(NavContextBase):
    """
    Favorites & Alerts page.

    Responsibilities:
      - Load favorite lists from wallet-service
      - Load list items with alerts from wallet-service
      - Merge items with latest quotes from stock-service (prefer Redis cache)
      - Render NiceGUI layout: header + manage bar + table
      - Provide actions: remove item, edit alert, delete alert, create list, delete list
    """

    def __init__(self, request: Request) -> None:
        super().__init__()

        self.request = request
        self.stock_client = StockClient()
        self.wallet_client = WalletClient()

        self.header_card = None
        self.manage_card = None
        self.table_card = None
        self.table = None

        self.user_id = None

        self.state: Dict[str, Any] = {
            "list_id": None,
            "search": "",
            "sort": ("symbol", "asc"),
        }

        self._lists_cache: List[dict] = []

        ui.timer(0.01, self._init_async, once=True)

    async def _init_async(self) -> None:
        """
        Async init: resolve user id, render navbar, build layout, render footer.
        """
        try:
            self.user_id = to_uuid(self.get_user_id())
        except Exception:
            ui.notify("Missing user_id", type="negative")
            logger.exception("FavoritesAlerts._init_async: cannot resolve user_id")
            return

        logger.info(f"FavoritesAlerts: init user_id={self.user_id}")

        self.render_navbar()
        await self.build_ui()
        footer()

    async def build_ui(self) -> None:
        """
        Create base layout cards (header/manage/table) and perform initial render.

        Returns:
            None. Creates UI components and triggers initial data load.
        """
        with ui.column().classes("w-[100vw] gap-1"):
            self.header_card = ui.card().classes("elevated-card q-pa-sm q-mb-md") \
                .style("width:min(1600px,98vw); margin:0 auto 1px;")
            self.manage_card = ui.card().classes("elevated-card q-pa-sm q-mb-md") \
                .style("width:min(1600px,98vw); margin:0 auto 1px;")
            self.table_card = ui.card().classes("elevated-card q-pa-sm q-mb-md") \
                .style("width:min(1600px,98vw); margin:0 auto 1px;")

        await self.render_all()

    async def render_all(self) -> None:
        """
        Render header, manage area, empty table shell, then load data once.
        """
        self.render_header()
        await self.render_manage()
        self.render_table([])
        await self.refresh_once()

    def render_header(self) -> None:
        """
        Render header card (title + current timestamp).
        """
        self.header_card.clear()
        with self.header_card:
            with ui.row().style(
                "display:flex;justify-content:space-between;align-items:center;"
                "flex-wrap:wrap;gap:10px;width:100%;padding:1px 20px;"
            ):
                ui.label("Ulubione & Alerty").classes("header-title")
                ui.label(datetime.now(TZ).strftime("%d.%m.%Y %H:%M:%S")).classes("text-grey-6 text-sm")

    async def render_manage(self) -> None:
        """
        Render manage panel:
          - Select list
          - Search input
          - Refresh button
          - Create/delete list buttons
        """
        self.manage_card.clear()

        self._lists_cache = await self.wallet_client.list_favorite_lists(user_id=self.user_id) or []
        logger.info(f"FavoritesAlerts.render_manage: lists={len(self._lists_cache)}")

        list_options = {str(lst.id): (lst.name or "Lista") for lst in self._lists_cache} if self._lists_cache else {}

        if list_options and not self.state["list_id"]:
            self.state["list_id"] = next(iter(list_options.keys()))

        with self.manage_card:
            with ui.row().style(
                "display:flex;justify-content:space-between;align-items:center;"
                "flex-wrap:wrap;gap:10px;width:100%;padding:1px 30px;"
            ):
                with ui.row().classes("items-center gap-2"):
                    self.sel_list = ui.select(
                        options=list_options,
                        value=self.state["list_id"],
                        label="Lista ulubionych",
                    ).classes("filter-field min-w-[260px] w-[360px]") \
                     .props("outlined dense clearable color=primary popup-content-class=filter-popup")

                    def _on_list_changed(e) -> None:
                        """
                        Handle list selection change.

                        Updates state and schedules a refresh.
                        """
                        self.state["list_id"] = e.sender.value
                        ui.timer(0.05, self.refresh_once, once=True)

                    self.sel_list.on("update:model-value", _on_list_changed)

                    self.search_input = ui.input(
                        value=self.state["search"],
                        placeholder="Szukaj symbol / nazwa…",
                        label="Szukaj",
                        on_change=lambda e: self._on_search_changed(e),
                    ).classes("filter-field min-w-[220px] w-[320px]") \
                     .props('outlined dense clearable color=primary input-class="q-pa-xs" clear-icon="close" debounce="250"')

                with ui.row().classes("items-center gap-2"):
                    ui.separator().props("vertical").classes("mx-2 hidden md:block")

                    ui.button("Odśwież", icon="refresh", on_click=self.refresh_once) \
                        .props("unelevated color=primary no-caps")

                    ui.button("Dodaj listę", icon="add", on_click=self._open_create_list_dialog) \
                        .props("outline color=primary no-caps")

                    btn_del = ui.button("Usuń listę", icon="delete", on_click=self._open_delete_list_dialog) \
                        .props("outline color=negative no-caps")

                    if not self.state["list_id"]:
                        btn_del.disable()

    def _on_search_changed(self, e) -> None:
        """
        Handle search input change.

        Args:
            e: NiceGUI event with `.value` holding current input text.
        """
        self.state["search"] = e.value or ""
        ui.timer(0.05, self.refresh_once, once=True)

    def render_table(self, rows: List[dict]) -> None:
        """
        Render favorites table (same style as quotes) plus alert columns.

        Args:
            rows: Prepared row dicts for the table.
        """
        self.table_card.clear()

        with self.table_card:
            with ui.element("div").classes("card-body w-full"):
                cols = [
                    {"name": "symbol", "label": "Symbol", "field": "symbol", "sortable": True, "align": "left",
                     "style": "width:120px;white-space:nowrap;", "headerStyle": "white-space:nowrap;"},
                    {"name": "name", "label": "Nazwa", "field": "name", "align": "left",
                     "style": "max-width:280px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;",
                     "headerStyle": "white-space:nowrap;"},
                    {"name": "last_price_fmt", "label": "Kurs", "field": "last_price_fmt", "align": "right",
                     "style": "width:120px;white-space:nowrap;", "headerStyle": "white-space:nowrap;"},
                    {"name": "change_pct", "label": "Zmiana %", "field": "change_pct", "sortable": True, "align": "right",
                     "style": "width:120px;white-space:nowrap;", "headerStyle": "white-space:nowrap;"},
                    {"name": "volume", "label": "Wolumen", "field": "volume", "align": "right",
                     "style": "width:120px;white-space:nowrap;", "headerStyle": "white-space:nowrap;"},
                    {"name": "last_trade_at", "label": "Ostatni handel", "field": "last_trade_at", "align": "left",
                     "style": "width:180px;white-space:nowrap;", "headerStyle": "white-space:nowrap;"},

                    {"name": "alert_enabled", "label": "Alert", "field": "alert_enabled", "sortable": True, "align": "center",
                     "style": "width:110px;white-space:nowrap;", "headerStyle": "white-space:nowrap;"},
                    {"name": "alert_below", "label": "Below", "field": "alert_below", "align": "center",
                     "style": "width:110px;white-space:nowrap;", "headerStyle": "white-space:nowrap;"},
                    {"name": "alert_above", "label": "Above", "field": "alert_above", "align": "center",
                     "style": "width:110px;white-space:nowrap;", "headerStyle": "white-space:nowrap;"},
                    {"name": "alert_expires", "label": "Wygasa", "field": "alert_expires", "align": "center",
                     "style": "width:160px;white-space:nowrap;", "headerStyle": "white-space:nowrap;"},

                    {"name": "actions", "label": "", "field": "symbol", "align": "right",
                     "style": "width:80px;white-space:nowrap;", "headerStyle": "white-space:nowrap;"},
                ]

                self.table = ui.table(
                    columns=cols,
                    rows=rows,
                    row_key="symbol",
                    pagination={"page": 1, "rowsPerPage": 100, "sortBy": "symbol", "descending": False},
                ).props(
                    'flat separator=horizontal wrap-cells '
                    'table-style="width:100%;table-layout:auto" '
                    "rows-per-page-options=[20,50,100,200,0]"
                ).classes("q-mt-none w-full table-modern")

                self.table.add_slot("body-cell-change_pct", """
                <q-td :props="props" :class="(parseFloat(props.row.change_pct || 0) >= 0 ? 'text-positive' : 'text-negative')">
                  <q-icon :name="parseFloat(props.row.change_pct || 0) >= 0 ? 'trending_up' : 'trending_down'" size="16px" class="q-mr-xs" />
                  {{ props.row.change_pct_fmt || '—' }}
                </q-td>
                """)

                self.table.add_slot("body-cell-last_trade_at", """
                <q-td :props="props">
                  <div class="text-no-wrap">
                    <span class="text-grey-7">{{ props.row.last_trade_date_fmt || '—' }}</span>
                    <span class="q-ml-sm text-weight-bold text-primary">{{ props.row.last_trade_time_fmt || '' }}</span>
                  </div>
                </q-td>
                """)

                self.table.add_slot("body-cell-alert_enabled", """
                <q-td :props="props" class="text-center">
                  <q-chip dense square
                    :color="props.row.alert_exists ? (props.row.alert_enabled === 'ON' ? 'positive' : 'grey-6') : 'grey-4'"
                    text-color="white">
                    {{ props.row.alert_exists ? props.row.alert_enabled : '—' }}
                  </q-chip>
                </q-td>
                """)

                self.table.add_slot("body-cell-actions", """
                <q-td :props="props" class="text-right">
                  <q-btn flat round dense icon="more_vert" color="primary">
                    <q-menu anchor="bottom right" self="top right">
                      <q-list style="min-width: 190px">
                        <q-item clickable v-close-popup @click.stop="$parent.$emit('fav_remove', props.row)">
                          <q-item-section avatar><q-icon name="delete_outline"/></q-item-section>
                          <q-item-section>Usuń z listy</q-item-section>
                        </q-item>

                        <q-separator />

                        <q-item clickable v-close-popup @click.stop="$parent.$emit('fav_alert_edit', props.row)">
                          <q-item-section avatar><q-icon name="add_alert"/></q-item-section>
                          <q-item-section>{{ props.row.alert_exists ? 'Edytuj alert' : 'Dodaj alert' }}</q-item-section>
                        </q-item>

                        <q-item clickable v-close-popup :disable="!props.row.alert_exists"
                                @click.stop="$parent.$emit('fav_alert_delete', props.row)">
                          <q-item-section avatar><q-icon name="notification_important"/></q-item-section>
                          <q-item-section>Usuń alert</q-item-section>
                        </q-item>
                      </q-list>
                    </q-menu>
                  </q-btn>
                </q-td>
                """)

                self.table.on("fav_remove", self._on_remove_item)
                self.table.on("fav_alert_edit", self._on_edit_alert)
                self.table.on("fav_alert_delete", self._on_delete_alert)

    async def refresh_once(self) -> None:
        """
        Reload selected list items and merge with latest quotes.

        Returns:
            None. Updates the table rows and triggers UI refresh.
        """
        list_id = self.state.get("list_id")
        if not list_id:
            self.table.rows = []
            self.table.update()
            return

        logger.info(f"FavoritesAlerts.refresh_once: list_id={list_id!r}")

        items = await self.wallet_client.list_favorite_items_with_alerts(
            user_id=self.user_id,
            list_id=to_uuid(list_id),
        )
        items = items or []

        s = (self.state.get("search") or "").strip().lower()
        if s:
            items = [
                it for it in items
                if s in str(it.get("symbol", "")).lower()
                or s in str(it.get("name", "")).lower()
            ]

        rows = await self._merge_items_with_quotes(items)

        self.table.rows = rows
        self.table.update()

    async def _merge_items_with_quotes(self, items: list[dict]) -> list[dict]:
        """
        Merge wallet items (symbol/name/alert) with live quote data.

        Strategy:
          - Group symbols by MIC (default XWAR if missing)
          - Load quotes using Redis hash `latest_quote:{mic}` when available
          - Fallback: stock_client.get_all_quotes(mic)

        Args:
            items: Wallet items list (dict payloads).

        Returns:
            Prepared table rows list.
        """
        symbols = [str(it.get("symbol") or "").upper().strip() for it in items if it.get("symbol")]
        symbols = [s for s in symbols if s]

        if not symbols:
            return []

        mic_by_symbol: Dict[str, str] = {}
        for it in items:
            sym = str(it.get("symbol") or "").upper().strip()
            mic = str(it.get("mic") or "XWAR").strip() 
            if sym:
                mic_by_symbol[sym] = mic

        grouped: Dict[str, List[str]] = {}
        for sym in symbols:
            mic = mic_by_symbol.get(sym, "XWAR")
            grouped.setdefault(mic, []).append(sym)

        quote_map: Dict[str, QuoteRow] = {}

        for mic, syms in grouped.items():
            qmap = await self._load_quotes_map(mic=mic, symbols=syms)
            quote_map.update(qmap)

        rows: List[dict] = []

        for it in items:
            sym = str(it.get("symbol") or "").upper().strip()
            nm = str(it.get("name") or "").strip() or "—"
            mic = mic_by_symbol.get(sym, "XWAR")

            q = quote_map.get(sym)

            alert = it.get("alert") if isinstance(it.get("alert"), dict) else None
            alert_exists = bool(alert)
            alert_enabled = "ON" if alert_exists and bool(alert.get("enabled", True)) else ("OFF" if alert_exists else "—")

            row: Dict[str, Any] = {
                "symbol": sym or "—",
                "name": nm,
                "mic": mic,

                "last_price_fmt": q.last_price_fmt if q else "—",
                "change_pct": str(q.change_pct) if q and q.change_pct is not None else "0",
                "change_pct_fmt": q.change_pct_fmt if q else "—",
                "volume": q.volume if q else "—",

                "last_trade_at": q.last_trade_at if q else "—",
                "last_trade_date_fmt": getattr(q, "last_trade_date_fmt", None) if q else "—",
                "last_trade_time_fmt": getattr(q, "last_trade_time_fmt", None) if q else "",

                "alert_exists": alert_exists,
                "alert_enabled": alert_enabled,
                "alert_below": _safe_dec_str(alert.get("below_price") if alert else None),
                "alert_above": _safe_dec_str(alert.get("above_price") if alert else None),
                "alert_expires": _fmt_dt(alert.get("expires_at") if alert else None),

                "_alert": alert or None,
                "_list_id": str(self.state.get("list_id") or ""),
            }
            rows.append(row)

        return rows

    async def _load_quotes_map(self, mic: str, symbols: list[str]) -> Dict[str, QuoteRow]:
        """
        Load latest quotes for given MIC + symbols.

        Prefer Redis hash:
          - key = f"latest_quote:{mic}"
          - fields = symbol -> payload

        Fallback:
          - stock_client.get_all_quotes(mic) and pick only requested symbols.

        Args:
            mic: MIC code (e.g. XWAR).
            symbols: List of symbols (uppercase).

        Returns:
            Mapping: symbol -> QuoteRow
        """
        out: Dict[str, QuoteRow] = {}

        key = f"latest_quote:{mic}"
        if await app.storage.stock.exists(key):
            for sym in symbols:
                try:
                    payload = await app.storage.stock.hget(key, sym)
                    if not payload:
                        continue
                    out[sym] = QuoteRow.from_redis(sym, payload)
                except Exception:
                    logger.exception(f"_load_quotes_map: failed for sym={sym!r} mic={mic!r}")
            return out

        try:
            all_rows = await self.stock_client.get_all_quotes(mic)
            m = {r.symbol.upper(): r for r in all_rows}
            for sym in symbols:
                if sym in m:
                    out[sym] = m[sym]
        except Exception:
            logger.exception(f"_load_quotes_map: fallback get_all_quotes failed mic={mic!r}")

        return out

    def _open_create_list_dialog(self) -> None:
        """
        Open dialog for creating a new favorite list.
        """
        dlg = ui.dialog()
        with dlg:
            with ui.card().style("""
                width: 520px;
                max-width: 95vw;
                border-radius: 18px;
                padding: 18px 18px 14px;
                background: #ffffff;
                border: 1px solid rgba(148,163,184,.35);
                box-shadow: 0 8px 20px rgba(15,23,42,.06);
            """):
                ui.label("Dodaj listę ulubionych").classes("text-h6 text-weight-medium")
                ui.separator().classes("q-my-sm")

                name_in = ui.input("Nazwa *").props("outlined dense clearable").classes("w-full")
                desc_in = ui.input("Opis").props("outlined dense clearable").classes("w-full")

                async def _create() -> None:
                    """
                    Create a list using wallet-service, then refresh manage+table UI.
                    """
                    nm = (name_in.value or "").strip()
                    if not nm:
                        ui.notify("Podaj nazwę listy", type="warning")
                        return

                    created = await self.wallet_client.create_favorite_list(
                        user_id=self.user_id,
                        name=nm,
                        description=(desc_in.value or "").strip() or None,
                    )
                    if not created:
                        ui.notify("Nie udało się utworzyć listy", type="negative")
                        return

                    ui.notify("Lista utworzona", type="positive")
                    dlg.close()

                    self.state["list_id"] = str(created.id)
                    await self.render_manage()
                    await self.refresh_once()

                with ui.row().classes("justify-end q-gutter-sm q-mt-md w-full"):
                    ui.button("Anuluj", on_click=dlg.close).props("flat no-caps")
                    ui.button("Utwórz", on_click=_create).props("unelevated color=primary no-caps") \
                        .style("min-width: 120px; height: 40px;")

        dlg.open()

    def _open_delete_list_dialog(self) -> None:
        """
        Open dialog for deleting the currently selected favorite list.
        """
        list_id = self.state.get("list_id")
        if not list_id:
            ui.notify("Wybierz listę", type="warning")
            return

        name = "Lista"
        for lst in self._lists_cache:
            if str(lst.id) == str(list_id):
                name = lst.name or "Lista"
                break

        dlg = ui.dialog()
        with dlg:
            with ui.card().style("""
                width: 520px;
                max-width: 95vw;
                border-radius: 18px;
                padding: 18px 18px 14px;
                background: #ffffff;
                border: 1px solid rgba(148,163,184,.35);
                box-shadow: 0 8px 20px rgba(15,23,42,.06);
            """):
                ui.label("Usuń listę?").classes("text-h6 text-weight-medium")
                ui.label(f"Ta operacja usunie listę: {name!r}").classes("text-body2 text-grey-7")

                ui.separator().classes("q-my-sm")

                async def _delete() -> None:
                    ok = await self.wallet_client.delete_favorite_list(
                        user_id=self.user_id,
                        list_id=to_uuid(list_id),
                    )
                    if not ok:
                        ui.notify("Nie udało się usunąć listy", type="negative")
                        return

                    ui.notify("Lista usunięta", type="positive")
                    dlg.close()

                    self.state["list_id"] = None
                    await self.render_manage()
                    await self.refresh_once()

                with ui.row().classes("justify-end q-gutter-sm q-mt-md w-full"):
                    ui.button("Anuluj", on_click=dlg.close).props("flat no-caps")
                    ui.button("Usuń", on_click=_delete).props("unelevated color=negative no-caps") \
                        .style("min-width: 120px; height: 40px;")

        dlg.open()

    async def _on_remove_item(self, e) -> None:
        """
        Handle "remove from list" action from the table.

        Args:
            e: NiceGUI event, expects `e.args` to be the row dict.
        """
        row = e.args or {}
        list_id = row.get("_list_id") or self.state.get("list_id")
        symbol = row.get("symbol")

        if not list_id or not symbol:
            ui.notify("Brak danych (list_id/symbol)", type="negative")
            return

        ok = await self.wallet_client.remove_favorite_item(
            user_id=self.user_id,
            list_id=to_uuid(list_id),
            symbol=str(symbol),
        )
        if not ok:
            ui.notify("Nie udało się usunąć z listy", type="negative")
            return

        _ = await self.wallet_client.delete_alert(user_id=self.user_id, symbol=str(symbol))

        ui.notify("Usunięto z listy (i alert jeżeli był)", type="positive")
        await self.refresh_once()

    async def _on_edit_alert(self, e) -> None:
        """
        Handle "edit/add alert" action from the table.

        Args:
            e: NiceGUI event with row dict in `e.args`.
        """
        row = e.args or {}
        symbol = row.get("symbol")
        name = row.get("name")
        alert = row.get("_alert") if isinstance(row.get("_alert"), dict) else None

        if not symbol:
            ui.notify("Missing symbol", type="negative")
            return

        await self._open_alert_editor(symbol=str(symbol), name=str(name or ""), initial_alert=alert)

    async def _on_delete_alert(self, e) -> None:
        """
        Handle "delete alert" action from the table.

        Args:
            e: NiceGUI event with row dict in `e.args`.
        """
        row = e.args or {}
        symbol = row.get("symbol")

        if not symbol:
            ui.notify("Missing symbol", type="negative")
            return

        ok = await self.wallet_client.delete_alert(user_id=self.user_id, symbol=str(symbol))
        if ok:
            ui.notify("Alert usunięty", type="positive")
        else:
            ui.notify("Nie udało się usunąć alertu", type="negative")

        await self.refresh_once()

    async def _open_alert_editor(
        self,
        symbol: str,
        name: str = "",
        initial_alert: Optional[dict] = None,
    ) -> None:
        """
        Open alert editor dialog for a given symbol.

        Allows creating/updating/deleting a price alert.

        Args:
            symbol: Instrument symbol.
            name: Optional display name.
            initial_alert: Existing alert payload dict (if any).
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
                ui.label("Alert cenowy").classes("text-h6 text-weight-medium")
                ui.label(f"{symbol} — {name or '—'}").classes("text-caption text-grey-7")

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
                    below_in = ui.input(label="Below price", placeholder="np. 100.00") \
                        .props("outlined dense clearable").classes("grow")
                    above_in = ui.input(label="Above price", placeholder="np. 120.00") \
                        .props("outlined dense clearable").classes("grow")

                if init_below is not None:
                    below_in.value = str(init_below)
                if init_above is not None:
                    above_in.value = str(init_above)

                expires_in = ui.input("Expires at (optional)").props("outlined dense clearable").classes("w-full")
                attach_date_time_popups(expires_in)
                if init_expires:
                    expires_in.value = str(init_expires)

                async def _save() -> None:
                    """
                    Validate inputs and upsert alert via wallet-service.
                    """
                    try:
                        below = parse_decimal(below_in.value)
                        above = parse_decimal(above_in.value)
                    except Exception:
                        ui.notify("Niepoprawny format ceny", type="negative")
                        return

                    if below is None and above is None:
                        ui.notify("Podaj below i/lub above", type="warning")
                        return

                    if below is not None and below < 0:
                        ui.notify("below_price musi być >= 0", type="warning")
                        return
                    if above is not None and above < 0:
                        ui.notify("above_price musi być >= 0", type="warning")
                        return
                    if below is not None and above is not None and below >= above:
                        ui.notify("below_price musi być < above_price", type="warning")
                        return

                    expires_at = None
                    raw_exp = str(expires_in.value or "").strip()
                    if raw_exp:
                        try:
                            expires_at = datetime.fromisoformat(raw_exp)
                        except Exception:
                            ui.notify("Niepoprawna data (ISO)", type="warning")
                            return

                    logger.info(
                        "FavoritesAlerts.alert_save: "
                        f"user_id={self.user_id} symbol={symbol} below={below} above={above} "
                        f"enabled={bool(enabled_cb.value)} one_shot={bool(one_shot_cb.value)} expires_at={expires_at}"
                    )

                    res = await self.wallet_client.upsert_alert(
                        user_id=self.user_id,
                        symbol=symbol,
                        below_price=below,
                        above_price=above,
                        enabled=bool(enabled_cb.value),
                        one_shot=bool(one_shot_cb.value),
                        expires_at=expires_at,
                    )
                    if not res:
                        ui.notify("Nie udało się zapisać alertu", type="negative")
                        return

                    ui.notify("Alert zapisany", type="positive")
                    adlg.close()
                    await self.refresh_once()

                async def _delete() -> None:
                    """
                    Delete the existing alert via wallet-service.
                    """
                    ok = await self.wallet_client.delete_alert(user_id=self.user_id, symbol=symbol)
                    if ok:
                        ui.notify("Alert usunięty", type="positive")
                    else:
                        ui.notify("Nie udało się usunąć alertu", type="negative")
                    adlg.close()
                    await self.refresh_once()

                with ui.row().classes("justify-end q-gutter-sm q-mt-md w-full"):
                    if initial_alert:
                        ui.button("Usuń", on_click=_delete).props("flat no-caps color=negative")

                    ui.button("Anuluj", on_click=adlg.close).props("flat no-caps")
                    ui.button("Zapisz", on_click=_save) \
                        .props("unelevated color=primary no-caps") \
                        .style("min-width: 120px; height: 40px;")

        adlg.open()


@ui.page("/user/favorites")
async def favorites_route(request: Request):
    add_style()
    add_user_style()
    add_table_style()
    FavoritesAlerts(request)
