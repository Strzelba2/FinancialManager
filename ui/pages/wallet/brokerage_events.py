import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional
import logging

from nicegui import ui
from fastapi import Request

from static.style import add_style, add_user_style, add_table_style
from components.context.nav_context import NavContextBase
from components.navbar_footer import footer
from components.brokerage_event import render_brokerage_event_form
from clients.wallet_client import WalletClient
from clients.stock_client import StockClient
from clients.nbp_client import NBPClient

from schemas.wallet import (
    Currency, BatchUpdateBrokerageEventsRequest, BrokerageEventKind
    )
from utils.utils import fmt_money, parse_date
from utils.money import dec, change_currency_to

logger = logging.getLogger(__name__)

KIND_LABEL = {k.name: (k.value if isinstance(k.value, str) else k.name.title()) for k in BrokerageEventKind}
KIND_OPTIONS = [{"label": v, "value": k} for k, v in KIND_LABEL.items()]

KIND_COLOR: dict[str, str] = {
    "BUY": "primary",
    "SELL": "negative",
    "DIVIDEND": "positive",
    "SPLIT": "info",
    "FEE": "warning",
    "TAX": "warning",
}


class BrokerageEvents(NavContextBase):
    """
    NiceGUI page/controller for browsing and editing brokerage events.

    Responsibilities:
    - Load exchange rates (NBP) and brokerage accounts
    - Fetch paginated brokerage event data from wallet API
    - Render header, filters, table, pager
    - Track edits via `_orig` + `_dirty` and submit batch updates
    - Allow deleting events and adding a new event via dialog
    """
    ALL_TOKEN = "__ALL__"

    def __init__(self, request: Request):
        super().__init__()
        self.request = request
        self.wallet_client = WalletClient()
        self.stock_client = StockClient()
        self.nbp_client = NBPClient()

        self.currency_rate = {}
        self.view_currency: Currency = Currency.PLN

        self.brokerage_accounts: list[dict[str, Any]] = []
        self.brokerage_account_options: dict[str, str] = {"Wszystkie": self.ALL_TOKEN}  # label -> value (uuid str)

        self.state: dict[str, Any] = {
            "brokerage_account_values": [self.ALL_TOKEN],
            "kinds": [],
            "currencies": [],
            "q": "",
            "from": "",
            "to": "",
            "page": 1,
            "size": 40,
            "view_ccy": Currency.PLN.value,
        }

        self.rows: list[dict[str, Any]] = []
        self.total_rows: int = 0
        self.total_sum_by_ccy: dict[str, Decimal] = {}

        self._orig: dict[str, dict[str, Any]] = {}
        self._dirty: dict[str, dict[str, Any]] = {}

        self.header_card = None
        self.manage_card = None
        self.table_card = None
        self.pager_card = None
        self.save_btn = None

        logger.info("BrokerageEvents: init -> scheduling async init")
        ui.timer(0.01, self._init_async, once=True)

    @staticmethod
    def _kind_label(code: Optional[str]) -> str:
        """Return human label for a kind code (fallback: title-case or '—')."""
        if not code:
            return "—"
        return KIND_LABEL.get(code, code.title())

    @staticmethod
    def _kind_color(code: Optional[str]) -> str:
        """Return chip color for a kind code (fallback: 'grey')."""
        if not code:
            return "grey"
        return KIND_COLOR.get(code, "grey")

    def _selected_brokerage_account_ids(self) -> Optional[list[uuid.UUID]]:
        """
        Convert selected brokerage account values into UUIDs.

        Returns:
            - None: means 'all' (when ALL_TOKEN selected or empty)
            - list[UUID]: selected account ids
        """
        vals: list[str] = list(self.state.get("brokerage_account_values") or [])
        if not vals or self.ALL_TOKEN in vals:
            return None
        out: list[uuid.UUID] = []
        for v in vals:
            try:
                out.append(uuid.UUID(str(v)))
            except Exception:
                pass
        return out or None

    async def _init_async(self) -> None:
        """Async init: navbar, rates, layout cards, load accounts + first page, then render."""
        logger.info("_init_async: start")
        self.render_navbar()
        self.currency_rate = await self.nbp_client.get_usd_eur_pln()

        with ui.column().classes("w-[100vw] gap-1"):
            self.header_card = ui.card().classes("elevated-card q-pa-sm q-mb-md").style("width:min(1600px,98vw); margin:0 auto 1px;")
            self.manage_card = ui.card().classes("elevated-card q-pa-sm q-mb-md").style("width:min(1600px,98vw); margin:0 auto 1px;")
            self.table_card = ui.card().classes("elevated-card q-pa-sm q-mb-md").style("width:min(1600px,98vw); margin:0 auto 1px;")
            self.pager_card = ui.card().classes("elevated-card q-pa-sm q-mb-md").style("width:min(1600px,98vw); margin:0 auto 1px;")

        await self._load_brokerage_accounts()
        await self._load_page()
        self._render_all()
        footer()

    async def _load_brokerage_accounts(self) -> None:
        """Load brokerage accounts and build select options."""
        user_id = self.get_user_id()
        raw = await self.wallet_client.list_brokerage_accounts_for_user(user_id=user_id)

        self.brokerage_accounts = raw or []
        self.brokerage_account_options = {"Wszystkie": self.ALL_TOKEN}

        for a in self.brokerage_accounts:
            name = a.get("name") or "Account"
            _id = a.get("id")
            if _id:
                self.brokerage_account_options[str(_id)] = str(name)

    async def _load_page(self) -> None:
        """
        Load a page of brokerage events based on current filters in `self.state`,
        then prepare UI rows and reset dirty/orig tracking.
        """
        user_id = self.get_user_id()

        brokerage_ids = self._selected_brokerage_account_ids()
        kinds = list(self.state.get("kinds") or []) or None
        currencies = list(self.state.get("currencies") or []) or None
        q = (self.state.get("q") or "").strip() or None

        d_from = parse_date(self.state.get("from"))
        d_to = parse_date(self.state.get("to"))

        page = int(self.state.get("page") or 1)
        size = int(self.state.get("size") or 40)

        try:
            page_out = await self.wallet_client.list_brokerage_events_page(
                user_id=user_id,
                brokerage_account_ids=brokerage_ids,
                kinds=kinds,
                currencies=currencies,
                date_from=d_from,
                date_to=d_to,
                q=q,
                page=page,
                size=size,
            )
        except Exception as e:
            logger.exception(f"_load_page: API error: {e}")
            page_out = None
            
        if page_out is None:
            self.rows = []
            self.total_rows = 0
            self.total_sum_by_ccy = {}
            self._dirty.clear()
            self._orig.clear()
            return

        self.total_rows = int(page_out.total or 0)
        self.total_sum_by_ccy = {k: dec(v) for k, v in (page_out.sum_by_ccy or {}).items()}
        self._dirty.clear()
        self._orig.clear()

        view_ccy = self.view_currency.value

        prepared: list[dict[str, Any]] = []
        for r in page_out.items or []:
            tx_id = str(r.id)
            trade_at = r.trade_at
            trade_at_disp = trade_at.strftime("%Y-%m-%d %H:%M") if isinstance(trade_at, datetime) else ""

            qty = dec(r.quantity)
            price = dec(r.price)
            ccy = (r.currency or "").strip()

            notional = qty * price  
            notional_view = change_currency_to(
                amount=notional,
                view_currency=view_ccy,
                transaction_currency=ccy,
                rates=self.currency_rate,
            )
            
            price_by_cc = change_currency_to(
                amount=price,
                view_currency=view_ccy,
                transaction_currency=ccy,
                rates=self.currency_rate,
            )

            kind_code = str(r.kind) if r.kind else None

            row = {
                "id": tx_id,
                "trade_at_disp": trade_at_disp,
                "brokerage_account_name": r.brokerage_account_name,
                "instrument": f"{r.instrument_symbol} — {r.instrument_name or ''}".strip(" —"),
                "kind": kind_code,
                "kind_label": self._kind_label(kind_code),
                "kind_color": self._kind_color(kind_code),

                "quantity": qty,
                "price": price_by_cc,
                "currency": ccy,

                "notional_view": notional_view,
                "notional_view_fmt": fmt_money(notional_view, view_ccy),

                "split_ratio": dec(r.split_ratio),

                "kind_options": list(KIND_OPTIONS),
            }
            prepared.append(row)

            self._orig[tx_id] = {
                "kind": row["kind"],
                "quantity": row["quantity"],
                "price": row["price"],
                "split_ratio": row["split_ratio"],
            }

        self.rows = prepared

    def _render_all(self) -> None:
        """Render all main UI sections: header, manage/filters, table, pager."""
        self._render_header()
        self._render_manage()
        self._render_table()
        self._render_pager()

    def _sum_rows_notional_in_view_ccy(self) -> Decimal:
        """Sum notional for currently visible rows (already in view currency)."""
        total = Decimal("0")
        for r in self.rows:
            total += dec(r.get("notional_view") or 0)
        return total

    def _sum_all_notional_in_view_ccy(self) -> Decimal:
        """Convert and sum notional totals across all currencies from API aggregate to view currency."""
        view_ccy = self.view_currency.value
        total = Decimal("0")
        for tx_ccy, amt in (self.total_sum_by_ccy or {}).items():
            tx_ccy = (tx_ccy or "").strip()
            if not tx_ccy:
                continue
            total += change_currency_to(
                amount=Decimal(str(amt or "0")),
                view_currency=view_ccy,
                transaction_currency=tx_ccy,
                rates=self.currency_rate,
            )
        return total

    def _render_header(self) -> None:
        """Render header card: title, totals, save button, add button."""
        self.header_card.clear()

        view_ccy = self.view_currency.value
        page_total = self._sum_rows_notional_in_view_ccy()
        all_total = self._sum_all_notional_in_view_ccy()

        with self.header_card:
            with ui.row().style("display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; width:100%; padding:1px 20px;"):
                ui.label("Brokerage events").classes("header-title")

                with ui.row().style("display:flex; align-items:center; flex-wrap:wrap; gap:10px;"):
                    ui.html(
                        f'<div class="balance-pill pos">'
                        f'<span class="label">Notional (page): </span>'
                        f'<span class="amount">{fmt_money(page_total, view_ccy)}</span>'
                        f"</div>"
                    )
                    if page_total != all_total:
                        ui.html(
                            f'<div class="balance-pill pos">'
                            f'<span class="label">Notional (all): </span>'
                            f'<span class="amount">{fmt_money(all_total, view_ccy)}</span>'
                            f"</div>"
                        )

                    self.save_btn = ui.button("Save changes", icon="save", on_click=self._on_save_clicked)
                    self.save_btn.props("unelevated color=primary")
                    ui.button("Add event", icon="add", on_click=self._open_add_event_dialog).props("unelevated color=primary")
                    self._refresh_save_btn()

    def _render_manage(self) -> None:
        """Render filter controls (account/kind/currency/search/view currency/date range)."""
        self.manage_card.clear()

        with self.manage_card:
            with ui.row().style("display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; width:100%; padding:1px 30px;"):
                with ui.row().style("display:flex; align-items:center; flex-wrap:wrap; gap:10px;"):
                    sel_acc = (
                        ui.select(self.brokerage_account_options, 
                                  multiple=True, 
                                  value=self.state["brokerage_account_values"], 
                                  label="Brokerage accounts")
                        .classes("filter-field min-w-[220px] w-[260px]")
                        .props("outlined dense use-chips options-dense clearable color=primary popup-content-class=filter-popup")
                    )
                    with sel_acc.add_slot("prepend"):
                        ui.icon("account_balance").classes("text-primary")
                    sel_acc.on("update:model-value", self._on_accounts_change)

                    sel_kind = (
                        ui.select([o["value"] for o in KIND_OPTIONS], multiple=True, value=self.state["kinds"], label="Kind")
                        .classes("filter-field min-w-[140px] w-[180px]")
                        .props("outlined dense use-chips options-dense clearable color=primary popup-content-class=filter-popup")
                    )
                    with sel_kind.add_slot("prepend"):
                        ui.icon("label").classes("text-primary")
                    sel_kind.on("update:model-value", self._on_kinds_change)

                    sel_ccy = (
                        ui.select([c.value for c in Currency], multiple=True, value=self.state["currencies"], label="Event currency")
                        .classes("filter-field min-w-[180px] w-[220px]")
                        .props("outlined dense use-chips options-dense clearable color=primary popup-content-class=filter-popup")
                    )
                    with sel_ccy.add_slot("prepend"):
                        ui.icon("currency_exchange").classes("text-primary")
                    sel_ccy.on("update:model-value", self._on_currencies_change)

                    q_in = ui.input(
                        value=self.state.get("q", ""), 
                        label="Instrument search",
                        on_change=lambda e: self._on_q_change(e),
                        ).classes("filter-field min-w-[220px] w-[280px]")
                    q_in.props("outlined dense clearable")

                    view_ccy_sel = (
                        ui.select([c.value for c in Currency], value=self.state.get("view_ccy", "PLN"), label="View currency")
                        .classes("filter-field min-w-[150px] w-[180px]")
                        .props("outlined dense options-dense clearable color=primary popup-content-class=filter-popup")
                    )
                    with view_ccy_sel.add_slot("prepend"):
                        ui.icon("currency_exchange").classes("text-primary")
                    view_ccy_sel.on("update:model-value", self._on_view_ccy_change)

                with ui.row().style("display:flex; align-items:center; flex-wrap:wrap; gap:10px;"):
                    rng = ui.button("Date ▾", icon="event").props("flat color=primary")
                    with rng:
                        with ui.menu() as m:
                            m.props("offset=[0,8]")
                            ui.menu_item("Last Month", on_click=lambda: self._set_range("1M"))
                            ui.menu_item("Last 3 Months", on_click=lambda: self._set_range("3M"))
                            ui.menu_item("Last Year", on_click=lambda: self._set_range("1Y"))
                            ui.menu_item("All", on_click=lambda: self._set_range("ALL"))
                            ui.separator()
                            ui.menu_item("Custom…", on_click=lambda: self._set_range("CUSTOM"))

                    self.custom_row = ui.row().classes("items-center gap-1").style("display:none")
                    with self.custom_row:
                        ui.button("FROM", icon="event", on_click=lambda: self._open_date_picker("From date", "from")).props("flat color=primary")
                        ui.button("TO", icon="event", on_click=lambda: self._open_date_picker("To date", "to")).props("flat color=primary")

    def _render_table(self) -> None:
        """Render the main editable table."""
        self.table_card.clear()

        with self.table_card:
            cols = [
                {"name": "trade_at_disp", "label": "Trade at", "field": "trade_at_disp", "align": "left", "style": "width:140px;white-space:nowrap;"},
                {"name": "brokerage_account_name", "label": "Account", "field": "brokerage_account_name", "align": "center", "style": "width:220px;white-space:nowrap;"},
                {"name": "instrument", "label": "Instrument", "field": "instrument", "align": "left", "style": "min-width:260px;white-space:normal; word-break:break-word;"},
                {"name": "kind", "label": "Kind", "field": "kind", "align": "center", "style": "width:140px;white-space:nowrap;"},
                {"name": "quantity", "label": "Qty", "field": "quantity", "align": "center", "style": "width:120px;white-space:nowrap;"},
                {"name": "price", "label": "Price", "field": "price", "align": "center", "style": "width:140px;white-space:nowrap;"},
                {"name": "notional_view_fmt", "label": "Notional", "field": "notional_view_fmt", "align": "center", "style": "width:170px;white-space:nowrap;"},
                {"name": "actions", "label": "", "field": "actions", "align": "center", "style": "width:60px;white-space:nowrap;"}
            ]

            tbl = (
                ui.table(columns=cols, rows=self.rows, row_key="id")
                .props('flat separator=horizontal wrap-cells table-style="width:100%;table-layout:auto" rows-per-page=0')
                .classes("q-mt-none w-full table-modern")
            )

            tbl.add_slot("body-cell-kind", r"""
            <q-td :props="props">
            <q-chip dense square class="chip-soft"
                    :color="props.row.kind_color"
                    text-color="white">
                {{ props.row.kind_label }}
            </q-chip>
            </q-td>
            """)

            tbl.add_slot("body-cell-quantity", r"""
            <q-td :props="props" class="num">
              <div class="editable-cell">
                <span>{{ Number(props.row.quantity).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</span>
                <q-popup-edit v-model="props.row.quantity"
                              v-slot="scope"
                              buttons label-set="OK" label-cancel="Cancel"
                              @save="val => $parent.$emit('ev_change', {id: props.row.id, field:'quantity', value: val})">
                  <q-input dense outlined type="number" step="0.01" v-model="scope.value" autofocus @keyup.enter="scope.set" />
                </q-popup-edit>
              </div>
            </q-td>
            """)

            tbl.add_slot("body-cell-price", r"""
            <q-td :props="props" class="num">
              <div class="editable-cell">
                <span>{{ Number(props.row.price).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</span>
                <q-popup-edit v-model="props.row.price"
                              v-slot="scope"
                              buttons label-set="OK" label-cancel="Cancel"
                              @save="val => $parent.$emit('ev_change', {id: props.row.id, field:'price', value: val})">
                  <q-input dense outlined type="number" step="0.01" v-model="scope.value" autofocus @keyup.enter="scope.set" />
                </q-popup-edit>
              </div>
            </q-td>
            """)

            tbl.add_slot("body-cell-split_ratio", r"""
            <q-td :props="props" class="num">
              <div class="editable-cell">
                <span>{{ Number(props.row.split_ratio).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</span>
                <q-popup-edit v-model="props.row.split_ratio"
                              v-slot="scope"
                              buttons label-set="OK" label-cancel="Cancel"
                              @save="val => $parent.$emit('ev_change', {id: props.row.id, field:'split_ratio', value: val})">
                  <q-input dense outlined type="number" step="0.01" v-model="scope.value" autofocus @keyup.enter="scope.set" />
                </q-popup-edit>
              </div>
            </q-td>
            """)
            tbl.add_slot("body-cell-actions", r"""
            <q-td :props="props" class="text-center">
            <q-btn dense flat round icon="delete" color="negative"
                    @click="$parent.$emit('ev_delete', props.row.id)" />
            </q-td>
            """)
            tbl.on("ev_delete", self._on_delete_event)

            tbl.on("ev_change", self._on_ev_change)

    def _render_pager(self) -> None:
        """Render pager controls and page-size selector."""
        
        self.pager_card.clear()
        size = int(self.state.get("size") or 40)
        page = int(self.state.get("page") or 1)
        total_pages = max(1, (self.total_rows + size - 1) // size)

        with self.pager_card:
            with ui.row().style("display:flex; justify-content:center; align-items:center; flex-wrap:wrap; gap:15px; width:100%; padding: 1px 20px;"):
                sel_size = ui.select([20, 40, 80, 120], value=size, label="Page size").classes("filter-field min-w-[140px] w-[160px]")
                sel_size.props("outlined dense options-dense clearable color=primary popup-content-class=filter-popup")
                sel_size.on("update:model-value", self._on_size_change)

                ui.label(f"Page {page} / {total_pages}  ({self.total_rows} rows)").classes("text-caption text-grey-7")

                prev_btn = ui.button(icon="chevron_left", on_click=self._prev_page).props("round flat color=primary")
                next_btn = ui.button(icon="chevron_right", on_click=self._next_page).props("round flat color=primary")
                prev_btn.set_enabled(page > 1)
                next_btn.set_enabled(page < total_pages)

    def _find_row(self, ev_id: str) -> Optional[dict[str, Any]]:
        """Find prepared row by event id."""
        for r in self.rows:
            if r.get("id") == ev_id:
                return r
        return None

    def _mark_dirty(self, ev_id: str, field: str, value: Any) -> None:
        """
        Mark a field as dirty if it differs from original snapshot.
        Updates save button state.
        """
        orig = self._orig.get(ev_id)
        if not orig:
            return

        value_norm = dec(value) if field in {"quantity", "price", "split_ratio"} else value
        changed = (value_norm != orig.get(field))

        if changed:
            self._dirty.setdefault(ev_id, {})
            self._dirty[ev_id][field] = value_norm
        else:
            if ev_id in self._dirty and field in self._dirty[ev_id]:
                del self._dirty[ev_id][field]
                if not self._dirty[ev_id]:
                    del self._dirty[ev_id]

        self._refresh_save_btn()

    def _refresh_save_btn(self) -> None:
        """Enable/disable save button based on dirty map."""
        if not self.save_btn:
            return
        if self._dirty:
            self.save_btn.enable()
            self.save_btn.text = f"Save changes ({len(self._dirty)})"
        else:
            self.save_btn.disable()
            self.save_btn.text = "Save changes"

    async def _on_ev_change(self, e) -> None:
        """Handle inline edit events from the table (quantity/price/split_ratio)."""
        payload = e.args or {}
        ev_id = str(payload.get("id") or "")
        field = str(payload.get("field") or "")
        value = payload.get("value")

        row = self._find_row(ev_id)
        if not row or not field:
            return
        
        if field in {"quantity", "split_ratio"}:
            row[field] = dec(value)
        else:
            row[field] = value if value != "" else None

        if field == "kind":
            row["kind_label"] = self._kind_label(row.get("kind"))
            row["kind_color"] = self._kind_color(row.get("kind"))
            
        if field == "price":
            view_val = dec(value)

            row[field] = change_currency_to(
                    amount=view_val,
                    view_currency=row.get("currency") or "",
                    transaction_currency=self.view_currency.value,
                    rates=self.currency_rate,
                )

        view_ccy = self.view_currency.value
        notional = dec(row.get("quantity")) * dec(row.get("price"))
        row["notional_view"] = change_currency_to(notional, view_ccy, row.get("currency") or "", self.currency_rate)
        row["notional_view_fmt"] = fmt_money(dec(row["notional_view"]), view_ccy)

        self._mark_dirty(ev_id, field, row.get(field))
        
    async def _on_delete_event(self, e) -> None:
        """Ask for confirmation and delete the selected event."""
        ev_id = str(e.args or "")
        if not ev_id:
            return

        dlg = ui.dialog()
        with dlg, ui.card().classes("w-[min(420px,95vw)]"):
            ui.label("Czy usunąć tą operację?").classes("text-base font-semibold q-mb-sm")
            ui.label("Ta czynność ma wpływ na stan posiadania").classes("text-body2 text-grey-7")
            ui.label("Pamiętaj aby usunąć Transakcję tyczącą się tej operacji").classes("text-body2 text-grey-7")

            with ui.row().classes("justify-end gap-2 q-mt-sm"):
                ui.button("Cancel", on_click=dlg.close).props("flat")
                
                async def _do():
                    dlg.close()
                    ok = await self.wallet_client.delete_brokerage_event(
                        user_id=self.get_user_id(),
                        event_id=uuid.UUID(ev_id),
                    )
                    if not ok:
                        ui.notify("Delete failed", type="negative")
                        return
                    ui.notify("Deleted", type="positive")
                    await self._load_page()
                    self._render_all()
                ui.button("Delete", on_click=_do).props("unelevated color=negative")

        dlg.open()

    async def _on_save_clicked(self) -> None:
        """Batch update all dirty rows."""
        if not self._dirty:
            ui.notify("No changes", type="info")
            return

        items: list[dict[str, Any]] = []
        for ev_id, patch in self._dirty.items():
            out: dict[str, Any] = {"id": str(ev_id)}
            for k, v in patch.items():
                out[k] = str(v) if isinstance(v, Decimal) else v
            items.append(out)

        req = BatchUpdateBrokerageEventsRequest(items=items)
        ok = await self.wallet_client.batch_update_brokerage_events(user_id=self.get_user_id(), req=req)
        if not ok:
            ui.notify("Update failed", type="negative")
            return

        ui.notify("Saved", type="positive")
        await self._load_page()
        self._render_all()

    async def _on_accounts_change(self, e) -> None:
        """Filter: brokerage accounts changed."""
        vals = list(e.sender.value or [])
        if not vals:
            vals = [self.ALL_TOKEN]
        if self.ALL_TOKEN in vals and len(vals) > 1:
            vals = [self.ALL_TOKEN]
        self.state["brokerage_account_values"] = vals
        self.state["page"] = 1
        await self._load_page()
        self._render_all()

    async def _on_kinds_change(self, e) -> None:
        """Filter: kinds changed."""
        self.state["kinds"] = list(e.sender.value or [])
        self.state["page"] = 1
        await self._load_page()
        self._render_all()

    async def _on_currencies_change(self, e) -> None:
        """Filter: currencies changed."""
        self.state["currencies"] = list(e.sender.value or [])
        self.state["page"] = 1
        await self._load_page()
        self._render_all()
        
    def _on_q_change(self, e) -> None:
        """Debounced search input change."""
        self.state["q"] = (e.value or "").strip()
        
        if hasattr(self, "_q_timer") and self._q_timer:
            self._q_timer.cancel()

        self._q_timer = ui.timer(1, self._reload_after, once=True)

    async def _on_view_ccy_change(self, e) -> None:
        """View currency changed: update currency and reload values."""
        v = e.sender.value or "PLN"
        try:
            self.view_currency = Currency(v)
        except Exception:
            self.view_currency = Currency.PLN
        self.state["view_ccy"] = self.view_currency.value
        await self._load_page()
        self._render_all()

    async def _on_size_change(self, e) -> None:
        """Page size changed."""
        self.state["size"] = int(e.sender.value or 40)
        self.state["page"] = 1
        await self._load_page()
        self._render_all()

    async def _prev_page(self) -> None:
        """Go to previous page."""
        if int(self.state["page"]) <= 1:
            return
        self.state["page"] = int(self.state["page"]) - 1
        await self._load_page()
        self._render_all()

    async def _next_page(self) -> None:
        """Go to next page."""
        size = int(self.state["size"])
        total_pages = max(1, (self.total_rows + size - 1) // size)
        if int(self.state["page"]) >= total_pages:
            return
        self.state["page"] = int(self.state["page"]) + 1
        await self._load_page()
        self._render_all()

    def _set_range(self, mode: str) -> None:
        """Set date range filter by preset or show custom controls."""
        today = datetime.now()
        if mode == "CUSTOM":
            self.custom_row.style("display:flex")
            return
        self.custom_row.style("display:none")

        if mode == "ALL":
            self.state["from"] = ""
            self.state["to"] = ""
        elif mode == "1M":
            self.state["from"] = (today - timedelta(days=30)).strftime("%Y-%m-%d")
            self.state["to"] = today.strftime("%Y-%m-%d")
        elif mode == "3M":
            self.state["from"] = (today - timedelta(days=90)).strftime("%Y-%m-%d")
            self.state["to"] = today.strftime("%Y-%m-%d")
        elif mode == "1Y":
            self.state["from"] = (today - timedelta(days=365)).strftime("%Y-%m-%d")
            self.state["to"] = today.strftime("%Y-%m-%d")

        ui.timer(0.01, self._reload_after, once=True)

    async def _reload_after(self) -> None:
        """Reload after custom selection."""
        self.state["page"] = 1
        await self._load_page()
        self._render_all()

    def _open_date_picker(self, title: str, which: str) -> None:
        """Open a date picker dialog to set either 'from' or 'to' filter."""
        dlg = ui.dialog()
        with dlg, ui.card().classes("w-[min(360px,95vw)]"):
            ui.label(title).classes("text-base font-semibold q-mb-sm")
            val = self.state.get(which) or datetime.now().strftime("%Y-%m-%d")
            picker = ui.date(value=val).classes("w-full")

            with ui.row().classes("justify-end gap-2 q-mt-sm"):
                ui.button("Cancel", on_click=dlg.close).props("flat")

                def _ok():
                    self.state[which] = picker.value
                    dlg.close()
                    ui.timer(0.01, self._reload_after, once=True)

                ui.button("OK", on_click=_ok).props("unelevated color=primary")
        dlg.open()
        
    async def _open_add_event_dialog(self) -> None:
        """Open dialog with `render_brokerage_event_form` and refresh after success."""
        dlg = ui.dialog()
        with dlg:
            with ui.card().style('''
                max-width: 620px;
                width: 80vw;
                padding: 28px 24px;
                border-radius: 24px;
                background: linear-gradient(180deg, #ffffff 0%, #f6f9ff 100%);
                box-shadow: 0 10px 24px rgba(15,23,42,.06);
                border: 1px solid rgba(2,6,23,.06);
            '''):
                ui.icon('show_chart').style(
                    'font-size:44px;color:#2563eb;background:#e0ecff;'
                    'padding:16px;border-radius:50%'
                )
                ui.label('Add brokerage event').classes('text-h5 text-weight-medium q-mb-xs text-center')
                ui.label('Choose account, market and instrument, then post the event.') \
                    .classes('text-body2 text-grey-8 q-mb-md text-center')

                with ui.element('div').style('max-height: 520px; overflow-y: auto; width:100%;'):
                    with ui.row().classes('w-full justify-center'):
                        body = ui.column().classes('q-gutter-sm').style('width:420px; max-width:100%;')

                with ui.row().classes('justify-end q-gutter-sm q-mt-md').style('width:100%;'):
                    ui.button('Cancel').props('no-caps flat').style('min-width:110px;height:44px').on_click(dlg.close)

        async def _after():
            dlg.close()
            await self._load_page()
            self._render_all()

        dep_brokerage_accounts = {
            uuid.UUID(str(a["id"])): a.get("name", str(a["id"]))
            for a in (self.brokerage_accounts or [])
        }

        await render_brokerage_event_form(
                self=self,
                container=body,
                brokerage_accounts=dep_brokerage_accounts,
                on_success=_after,
            )

        dlg.open()


@ui.page("/brokerage/events")
def brokerage_events_page(request: Request):
    add_style()
    add_user_style()
    add_table_style()
    BrokerageEvents(request)
