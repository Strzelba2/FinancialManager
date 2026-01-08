from nicegui import ui
from fastapi import Request
from datetime import datetime, timedelta
import uuid
from decimal import Decimal
from typing import Any, Optional
from enum import StrEnum
import logging

from static.style import add_style, add_user_style, add_table_style
from components.context.nav_context import NavContextBase
from clients.wallet_client import WalletClient
from clients.nbp_client import NBPClient
from schemas.wallet import AccountOut, BatchUpdateTransactionsRequest, Currency
from components.navbar_footer import footer
from components.transaction import render_manual_transaction_form
from utils.utils import fmt_money, parse_date
from utils.money import dec, change_currency_to

logger = logging.getLogger(__name__)


class TransactionStatus(StrEnum):
    INCOME = "Przychód"
    EXPENSE = "Wydatek"
    INTERNAL = "Wewnętrzny"


class TransactionCategory(StrEnum):
    FOOD = "Żywność"
    FUEL = "Paliwo"
    ENTERTAINMENT = "Rozrywka"
    CAR = "Samochód"
    HOME = "Mieszkanie"
    BILLS = "Rachunki"
    HEALTH = "Zdrowie"
    CLOTHES = "Ubrania"
    EDUCATION = "Edukacja"
    TRAVEL = "Podróże"
    SUBSCRIPTIONS = "Subskrypcje"
    GIFTS = "Prezenty"
    CHILDREN = "Dzieci"
    SPORT = "Sport"
    INVESTMENTS = "Inwestycje"
    MEDICINES = "Lekarstwa"
    PHONE = "Telefony"
    BEAUTY = "Uroda"
    OTHER = "Inne"


STATUS_OPTIONS: list[str] = {x.value: x.name for x in TransactionStatus}
CATEGORY_OPTIONS_DEFAULT: list[str] = {x.value: x.name for x in TransactionCategory}

STATUS_COLOR: dict[str, str] = {
    TransactionStatus.INCOME.value: "positive",
    TransactionStatus.EXPENSE.value: "negative",
    TransactionStatus.INTERNAL.value: "info",
}

CATEGORY_COLOR: dict[str, str] = {
    TransactionCategory.FOOD.value: "orange",
    TransactionCategory.FUEL.value: "warning",
    TransactionCategory.ENTERTAINMENT.value: "accent",
    TransactionCategory.CAR.value: "primary",
    TransactionCategory.HOME.value: "secondary",
    TransactionCategory.BILLS.value: "negative",
    TransactionCategory.HEALTH.value: "red",
    TransactionCategory.CLOTHES.value: "purple",
    TransactionCategory.EDUCATION.value: "teal",
    TransactionCategory.TRAVEL.value: "indigo",
    TransactionCategory.SUBSCRIPTIONS.value: "blue-grey",
    TransactionCategory.GIFTS.value: "pink",
    TransactionCategory.CHILDREN.value: "cyan",
    TransactionCategory.SPORT.value: "green",
    TransactionCategory.INVESTMENTS.value: "lime",
    TransactionCategory.OTHER.value: "grey",
}


class Transactions(NavContextBase):
    """
    NiceGUI page/controller to display and edit wallet transactions.

    Expectations about backend/client:
    - list_accounts_for_user(user_id) -> list[AccountOut]
    - list_transactions_page(...) -> page object with .items, .total, optional .sum_by_ccy
    - batch_update_transactions(user_id, req) -> bool
    - delete_transaction(user_id, transaction_id) -> bool

    Important UX note:
    - Row numeric fields are displayed and edited in *view currency*.
      `_load_page` converts backend amounts from transaction currency to view currency.
      Therefore:
        - `_on_tx_change` should store decimals directly (NO additional FX conversion)
        - `_sum_rows_in_view_ccy` should sum displayed values directly (NO conversion)
        - `_sum_all_in_view_ccy` uses backend aggregates by currency and converts them to view currency
    """

    ALL_TOKEN = "__ALL__"

    def __init__(self, request: Request):
        super().__init__()
        self.request = request
        self.wallet_client = WalletClient()
        self.nbp_client = NBPClient()

        self.category_options: list[str] = list(CATEGORY_OPTIONS_DEFAULT)
        self.status_options: list[str] = list(STATUS_OPTIONS)

        self.accounts: list[AccountOut] = []
        self.account_options: dict[str, str] = {"Wszystkie": self.ALL_TOKEN} 

        self.state: dict[str, Any] = {
            "account_values": [self.ALL_TOKEN],  
            "categories": [],                   
            "statuses": [],                    
            "from": "",                      
            "to": "",                        
            "page": 1,
            "size": 40,
            "currency": Currency.PLN.value
        }

        self.rows: list[dict[str, Any]] = []
        self.total_rows: int = 0

        self._orig: dict[str, dict[str, Any]] = {}            
        self._dirty: dict[str, dict[str, Any]] = {}   
        self.total_sum_by_ccy: dict[str, Decimal] = {}

        self.range_state = {"value": "ALL"}
        self.range_labels = {"ALL": "All", "1M": "Last Month", "3M": "Last 3 Months", "1Y": "Last Year", "CUSTOM": "Date"}

        self.header_card = None
        self.manage_card = None
        self.table_card = None
        self.pager_card = None
        self.range_btn = None
        self.custom_row = None
        self.save_btn = None
        self.pager_label = None
        self.view_currency = Currency.PLN

        ui.timer(0.01, self._init_async, once=True)

    @staticmethod
    def _color_for_category(cat: Optional[str]) -> str:
        """Return chip color for category label."""
        if not cat:
            return "grey"
        return CATEGORY_COLOR.get(cat, "info")

    @staticmethod
    def _color_for_status(st: Optional[str]) -> str:
        """Return chip color for status label."""
        if not st:
            return "grey"
        return STATUS_COLOR.get(st, "grey")

    async def _init_async(self) -> None:
        """Async init: navbar, FX, layout, initial load, render."""
        self.render_navbar()
        
        self.currency_rate = await self.nbp_client.get_usd_eur_pln()

        with ui.column().classes("w-[100vw] gap-1"):
            self.header_card = ui.card().classes("elevated-card q-pa-sm q-mb-md").style("width:min(1600px,98vw); margin:0 auto 1px;")
            self.manage_card = ui.card().classes("elevated-card q-pa-sm q-mb-md").style("width:min(1600px,98vw); margin:0 auto 1px;")
            self.table_card = ui.card().classes("elevated-card q-pa-sm q-mb-md").style("width:min(1600px,98vw); margin:0 auto 1px;")
            self.pager_card = ui.card().classes("elevated-card q-pa-sm q-mb-md").style("width:min(1600px,98vw); margin:0 auto 1px;")
            
        await self._load_accounts()
        await self._load_page()
        self._render_all()

        footer()

    async def _load_accounts(self) -> None:
        """Load accounts for the current user and build select options."""
        user_id = self.get_user_id()

        self.accounts = await self.wallet_client.list_accounts_for_user(user_id=user_id)
        self.account_options = {"Wszystkie": self.ALL_TOKEN}
        for a in self.accounts:
            self.account_options[a.id] = str(a.name)

    def _selected_account_ids(self) -> Optional[list[uuid.UUID]]:
        """
        Convert selected account values into UUIDs.

        Returns:
            None -> no filtering (ALL)
            list[UUID] -> selected accounts
        """
        vals: list[str] = list(self.state.get("account_values") or [])
        if not vals or self.ALL_TOKEN in vals:
            return None
        out: list[uuid.UUID] = []
        for v in vals:
            if v == self.ALL_TOKEN:
                continue
            try:
                out.append(v)
            except Exception:
                logger.info("exception")
                pass
        return out or None

    async def _load_page(self) -> None:
        """
        Load one page of transactions based on filters and convert numeric fields to view currency.

        Populates:
        - self.rows
        - self.total_rows
        - self.total_sum_by_ccy (backend aggregates)
        - resets _orig / _dirty
        """
        user_id = self.get_user_id()

        account_ids = self._selected_account_ids()
        categories = list(self.state.get("categories") or []) or None
        statuses = list(self.state.get("statuses") or []) or None

        d_from = parse_date(self.state.get("from"))
        d_to = parse_date(self.state.get("to"))

        page = int(self.state.get("page") or 1)
        size = int(self.state.get("size") or 40)

        page_out = await self.wallet_client.list_transactions_page(
            user_id=user_id,
            account_ids=account_ids,
            categories=categories,
            statuses=statuses,
            date_from=d_from,
            date_to=d_to,
            page=page,
            size=size,
        )
        
        if page_out is None:
            self.rows = []
            self.total_rows = 0
            self._dirty.clear()
            self._orig.clear()
            return
        
        rows = page_out.items
        total = page_out.total
        
        self.total_sum_by_ccy = {k: dec(v) for k, v in (getattr(page_out, "sum_by_ccy", None) or {}).items()}

        self.total_rows = int(total or 0)
        self._dirty.clear()
        self._orig.clear()

        prepared: list[dict[str, Any]] = []
        for r in rows or []:

            tx_id = str(r.id)
            dt = r.date_transaction 
            if isinstance(dt, str):
                try:
                    dt_obj = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                except Exception:
                    dt_obj = None
            elif isinstance(dt, datetime):
                dt_obj = dt
            else:
                dt_obj = None

            amount = dec(r.amount)
            bb = dec(r.balance_before)
            ba = dec(r.balance_after)
            ccy = (r.ccy or "").strip()
            
            amount_by_ccy = change_currency_to(
                    amount=amount,
                    view_currency=self.view_currency.value,
                    transaction_currency=ccy,
                    rates=self.currency_rate,
                )
            bb_by_cc = change_currency_to(
                    amount=bb,
                    view_currency=self.view_currency.value,
                    transaction_currency=ccy,
                    rates=self.currency_rate,
                )
            ba_by_cc = change_currency_to(
                    amount=ba,
                    view_currency=self.view_currency.value,
                    transaction_currency=ccy,
                    rates=self.currency_rate,
                )

            category_view = (m := TransactionCategory.__members__.get(str(r.category))) and m.value or "—"
            status_view = (m := TransactionStatus.__members__.get(str(r.status))) and m.value or "—"
            account_name = (r.account_name or "").strip()

            row = {
                "id": tx_id,
                "date_disp": dt_obj.strftime("%Y-%m-%d %H:%M") if dt_obj else "",
                "description": r.description or "",
                "account_name": account_name,
                "category": category_view,
                "status": status_view,
                "amount": amount_by_ccy,
                "balance_before": bb_by_cc,
                "balance_after": ba_by_cc,
                "ccy": ccy,

                "category_color": self._color_for_category(category_view),
                "status_color": self._color_for_status(status_view),

                "category_options": list(self.category_options),
                "status_options": list(self.status_options),
            }

            prepared.append(row)

            self._orig[tx_id] = {
                "description": row["description"],
                "category": row["category"],
                "status": row["status"],
                "amount": row["amount"],
                "balance_before": row["balance_before"],
                "balance_after": row["balance_after"],
            }

        self.rows = prepared

    def _render_all(self) -> None:
        """Render header, filters, table and pager."""
        self._render_header()
        self._render_manage()
        self._render_table()
        self._render_pager()

    def _render_header(self) -> None:
        """Render totals (page/all) and action buttons."""
        self.header_card.clear()

        view_ccy = self.view_currency.value 
        page_total = self._sum_rows_in_view_ccy()
        all_total = self._sum_all_in_view_ccy()
        sign_cls_page = "pos" if page_total >= 0 else "neg"
        sign_cls_all = "pos" if all_total >= 0 else "neg"

        with self.header_card:
            with ui.row().style(
                "display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; width:100%; padding:1px 20px;"
            ):
                ui.label("Transakcje").classes("header-title")

                with ui.row().style("display:flex; align-items:center; flex-wrap:wrap; gap:10px;"):
                    ui.html(
                        f'<div class="balance-pill {sign_cls_page}">'
                        f'<span class="label">Sum (page): </span>'
                        f'<span class="amount">{fmt_money(page_total, view_ccy)}</span>'
                        f"</div>"
                    )
                    if page_total != all_total:
                        ui.html(
                            f'<div class="balance-pill {sign_cls_all}">'
                            f'<span class="label">Sum (all): </span>'
                            f'<span class="amount">{fmt_money(all_total, view_ccy)}</span>'
                            f"</div>"
                        )

                    self.save_btn = ui.button("Save changes", icon="save", on_click=self._on_save_clicked)
                    ui.button("Add transaction", icon="add", on_click=self._open_add_transaction_dialog).props("unelevated color=primary")
                    self.save_btn.props("unelevated color=primary")
                    self._refresh_save_btn()

    def _render_manage(self) -> None:
        """Render filters: accounts, view currency, categories, statuses, date range."""
        self.manage_card.clear()

        with self.manage_card:
            with ui.row().style(
                "display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; width:100%; padding:1px 30px;"
            ):
                with ui.row().style("display:flex; align-items:center; flex-wrap:wrap; gap:10px;"):
                    sel_accounts = (
                        ui.select(self.account_options, multiple=True, value=self.state["account_values"], label="Konta")
                        .classes("filter-field min-w-[200px] w-[260px]")
                        .props("outlined dense use-chips options-dense clearable color=primary popup-content-class=filter-popup")
                    )
                    with sel_accounts.add_slot("prepend"):
                        ui.icon("account_balance").classes("text-primary")
                    sel_accounts.on("update:model-value", self._on_accounts_change)
                    
                    self.view_currency = (
                        ui.select([c.value for c in Currency], value=self.state.get("currency", "PLN"), label="Waluta")
                        .classes("filter-field min-w-[160px] w-[180px]") 
                        .props("outlined dense options-dense clearable color=primary popup-content-class=filter-popup")
                    )
                    with self.view_currency.add_slot("prepend"):
                        ui.icon("currency_exchange").classes("text-primary")

                    self.view_currency.on("update:model-value", self.on_currency_change)

                    sel_categories = (
                        ui.select(self.category_options, multiple=True, value=self.state["categories"], label="Kategorie")
                        .classes("filter-field min-w-[260px] w-[240px]")
                        .props("outlined dense use-chips options-dense clearable color=primary popup-content-class=filter-popup")
                    )
                    with sel_categories.add_slot("prepend"):
                        ui.icon("label").classes("text-primary")
                    sel_categories.on("update:model-value", self._on_categories_change)

                    sel_statuses = (
                        ui.select(self.status_options, multiple=True, value=self.state["statuses"], label="Status")
                        .classes("filter-field min-w-[180px] w-[220px]")
                        .props("outlined dense use-chips options-dense clearable color=primary popup-content-class=filter-popup")
                    )
                    with sel_statuses.add_slot("prepend"):
                        ui.icon("swap_vert").classes("text-primary")
                    sel_statuses.on("update:model-value", self._on_statuses_change)

                with ui.row().style("display:flex; align-items:center; flex-wrap:wrap; gap:10px;"):
                    self.range_btn = ui.button(f"{self.range_labels.get(self.range_state.get('value'))} ▾", icon="event")
                    self.range_btn.props("flat color=primary")
                    with self.range_btn:
                        with ui.menu() as m:
                            m.props("offset=[0,8]")
                            ui.menu_item("Last Month", on_click=lambda: self._set_range("1M"))
                            ui.menu_item("Last 3 Months", on_click=lambda: self._set_range("3M"))
                            ui.menu_item("Last Year", on_click=lambda: self._set_range("1Y"))
                            ui.menu_item("All", on_click=lambda: self._set_range("ALL"))
                            ui.separator()
                            ui.menu_item("Zakres dat…", on_click=lambda: self._set_range("CUSTOM"))

                    self.custom_row = ui.row().classes("items-center gap-1").style("display:none")
                    with self.custom_row:
                        ui.button("FROM", icon="event", on_click=lambda: self._open_date_picker("From date", "from")).props("flat color=primary")
                        ui.button("TO", icon="event", on_click=lambda: self._open_date_picker("To date", "to")).props("flat color=primary")

    def _render_table(self) -> None:
        """Render editable table (description/category/status/amount/balances)."""
        self.table_card.clear()

        with self.table_card:
            with ui.element("div").classes("card-body w-full"):
                cols = [
                    {"name": "date_disp", "label": "Date", "field": "date_disp", "sortable": False, "align": "left",
                     "style": "width:140px;white-space:nowrap;", "headerStyle": "white-space:nowrap;"},
                    {"name": "description", "label": "Description", "field": "description", "align": "left",
                     "style": "min-width:260px;max-width:520px;white-space: normal; word-break: break-word; overflow-wrap: anywhere;",
                     "headerStyle": "white-space:nowrap;"},
                    {"name": "account_name", "label": "Account", "field": "account_name", "align": "center",
                     "style": "width:180px;white-space:nowrap;", "headerStyle": "white-space:nowrap;"},
                    {"name": "category", "label": "Category", "field": "category", "align": "center",
                     "style": "width:190px;white-space:nowrap;", "headerStyle": "white-space:nowrap;"},
                    {"name": "status", "label": "Status", "field": "status", "align": "center",
                     "style": "width:160px;white-space:nowrap;", "headerStyle": "white-space:nowrap;"},
                    {"name": "amount", "label": "Amount", "field": "amount", "align": "center",
                     "classes": "num", "style": "width:160px;white-space:nowrap;", "headerStyle": "white-space:nowrap;"},
                    {"name": "balance_before", "label": "Balance_before", "field": "balance_before", "align": "center",
                     "classes": "num", "style": "width:160px;white-space:nowrap;", "headerStyle": "white-space:nowrap;"},
                    {"name": "balance_after", "label": "Balance_after", "field": "balance_after", "align": "center",
                     "classes": "num", "style": "width:160px;white-space:nowrap;", "headerStyle": "white-space:nowrap;"},
                    {"name": "actions", "label": "", "field": "actions", "align": "right", "style": "width:60px;white-space:nowrap;"}
                ]

                tbl = (
                    ui.table(columns=cols, rows=self.rows, row_key="id")
                    .props('flat separator=horizontal wrap-cells table-style="width:100%;table-layout:auto" rows-per-page=0')
                    .classes("q-mt-none w-full table-modern")
                )

                tbl.add_slot("body-cell-amount", r"""
                    <q-td :props="props" class="num">
                    <div class="editable-cell">
                        <span :class="(Number(props.row.amount) >= 0 ? 'text-positive' : 'text-negative')">
                        {{ Number(props.row.amount).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}
                        {{ props.row.view_ccy }}
                        </span>

                        <q-popup-edit v-model="props.row.amount"
                                    v-slot="scope"
                                    buttons label-set="OK" label-cancel="Cancel"
                                    @save="val => $parent.$emit('tx_change', {id: props.row.id, field: 'amount', value: val})">
                        <q-input dense outlined type="number" step="0.01"
                                v-model="scope.value" autofocus
                                @keyup.enter="scope.set" />
                        </q-popup-edit>
                    </div>
                    </q-td>
                    """)

                tbl.add_slot("body-cell-description", r"""
                    <q-td :props="props">
                    <div class="editable-cell" style="width:100%; align-items:flex-start;">
                        <span style="white-space: normal; word-break: break-word; overflow-wrap:anywhere;">
                        {{ props.row.description }}
                        </span>

                        <q-popup-edit v-model="props.row.description"
                                    v-slot="scope"
                                    buttons
                                    label-set="OK"
                                    label-cancel="Cancel"
                                    @save="val => $parent.$emit('tx_change', {id: props.row.id, field: 'description', value: val})">
                        <q-input dense outlined type="text"
                                v-model="scope.value"
                                autofocus
                                autogrow
                                @keyup.enter="scope.set" />
                        </q-popup-edit>
                    </div>
                    </q-td>
                    """)

                tbl.add_slot("body-cell-category", r"""
                    <q-td :props="props">
                    <div class="editable-cell">
                        <q-chip dense square class="chip-soft"
                                :color="props.row.category_color"
                                text-color="white">
                        {{ props.row.category || '—' }}
                        </q-chip>

                        <q-popup-edit v-model="props.row.category"
                                    v-slot="scope"
                                    buttons
                                    label-set="OK"
                                    label-cancel="Cancel"
                                    @save="val => $parent.$emit('tx_change', {id: props.row.id, field: 'category', value: val})">
                        <q-select dense outlined options-dense clearable use-input
                                    :options="props.row.category_options"
                                    v-model="scope.value"
                                    @new-value="(val, done) => { $parent.$emit('tx_new_category', {value: val}); done(val, 'add-unique'); }"
                                    new-value-mode="add-unique"
                                    />
                        </q-popup-edit>
                    </div>
                    </q-td>
                    """)

                tbl.add_slot("body-cell-status", r"""
                    <q-td :props="props">
                    <div class="editable-cell">
                        <q-chip dense square class="chip-soft"
                                :color="props.row.status_color"
                                text-color="white">
                        {{ props.row.status || '—' }}
                        </q-chip>

                        <q-popup-edit v-model="props.row.status"
                                    v-slot="scope"
                                    buttons
                                    label-set="OK"
                                    label-cancel="Cancel"
                                    @save="val => $parent.$emit('tx_change', {id: props.row.id, field: 'status', value: val})">
                        <q-select dense outlined options-dense clearable
                                    :options="props.row.status_options"
                                    v-model="scope.value" />
                        </q-popup-edit>
                    </div>
                    </q-td>
                    """)

                tbl.add_slot("body-cell-balance_before", r"""
                    <q-td :props="props" class="num">
                    <div class="editable-cell">
                        <span>
                        {{ Number(props.row.balance_before).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}
                        {{ props.row.view_ccy }}
                        </span>

                        <q-popup-edit v-model="props.row.balance_before"
                                    v-slot="scope"
                                    buttons label-set="OK" label-cancel="Cancel"
                                    @save="val => $parent.$emit('tx_change', {id: props.row.id, field: 'balance_before', value: val})">
                        <q-input dense outlined type="number" step="0.01"
                                v-model="scope.value" autofocus
                                @keyup.enter="scope.set" />
                        </q-popup-edit>
                    </div>
                    </q-td>
                    """)
  
                tbl.add_slot("body-cell-balance_after", r"""
                    <q-td :props="props" class="num">
                    <div class="editable-cell">
                         <span>
                        {{ Number(props.row.balance_after).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}
                        {{ props.row.view_ccy }}
                        </span>

                        <q-popup-edit v-model="props.row.balance_after"
                                    v-slot="scope"
                                    buttons label-set="OK" label-cancel="Cancel"
                                    @save="val => $parent.$emit('tx_change', {id: props.row.id, field: 'balance_after', value: val})">
                        <q-input dense outlined type="number" step="0.01"
                                v-model="scope.value" autofocus
                                @keyup.enter="scope.set" />
                        </q-popup-edit>
                    </div>
                    </q-td>
                    """)
                
                tbl.add_slot("body-cell-actions", r"""
                <q-td :props="props" class="text-right">
                <q-btn dense flat round icon="delete" color="negative"
                        @click="$parent.$emit('tx_delete', props.row.id)" />
                </q-td>
                """)
                tbl.on("tx_delete", self._on_delete_transaction)

                tbl.on("tx_change", self._on_tx_change)
                tbl.on("tx_new_category", self._on_tx_new_category)

    def _render_pager(self) -> None:
        """Render pager with size selector and prev/next buttons."""
        if not self.pager_card:
            return

        self.pager_card.clear()

        size = int(self.state.get("size") or 40)
        page = int(self.state.get("page") or 1)
        total_pages = max(1, (self.total_rows + size - 1) // size)

        with self.pager_card:
            with ui.row().style(
                "display:flex; justify-content:center; align-items:center; flex-wrap:wrap; gap:15px; width:100%; padding: 1px 20px;"
            ):
                sel_size = (
                    ui.select([20, 40, 80, 120], value=size, label="Page size")
                    .classes("filter-field min-w-[140px] w-[160px]")
                    .props("outlined dense options-dense clearable color=primary popup-content-class=filter-popup")
                )
                sel_size.on("update:model-value", self._on_size_change)

                ui.label(f"Page {page} / {total_pages}  ({self.total_rows} rows)").classes("text-caption text-grey-7")

                prev_btn = ui.button(icon="chevron_left", on_click=self._prev_page).props("round flat color=primary")
                next_btn = ui.button(icon="chevron_right", on_click=self._next_page).props("round flat color=primary")

                prev_btn.set_enabled(page > 1)
                next_btn.set_enabled(page < total_pages)

    def _find_row(self, tx_id: str) -> Optional[dict[str, Any]]:
        """Find a row by transaction id."""
        for r in self.rows:
            if r.get("id") == tx_id:
                return r
        return None

    def _mark_dirty(self, tx_id: str, field: str, value: Any) -> None:
        """
        Track dirty edits relative to `_orig`. If the new value equals the original, remove the dirty patch.
        """
        orig = self._orig.get(tx_id)
        if not orig:
            return

        if field in {"amount", "balance_before", "balance_after"}:
            value_norm = dec(value)
        else:
            value_norm = (value if value is not None else None)

        orig_val = orig.get(field)

        changed = (value_norm != orig_val)
        if changed:
            self._dirty.setdefault(tx_id, {})
            self._dirty[tx_id][field] = value_norm
        else:
            if tx_id in self._dirty and field in self._dirty[tx_id]:
                del self._dirty[tx_id][field]
                if not self._dirty[tx_id]:
                    del self._dirty[tx_id]

        self._refresh_save_btn()

    def _refresh_save_btn(self) -> None:
        """Enable/disable save button based on dirty state."""
        if not self.save_btn:
            return
        if self._dirty:
            self.save_btn.props("unelevated color=primary")
            self.save_btn.enable()
            self.save_btn.text = f"Save changes ({len(self._dirty)})"
        else:
            self.save_btn.disable()
            self.save_btn.text = "Save changes"
            
    async def on_currency_change(self):
        """Handle view currency change from the UI select."""
        self.state["currency"] = self.view_currency.value
        await self._load_page()
        self._render_all()

    async def _on_tx_change(self, e) -> None:
        """
        Inline edit handler from the table.
        Numeric fields are edited in view currency -> store as Decimal directly.
        """
        payload = e.args or {}
        tx_id = str(payload.get("id") or "")
        field = str(payload.get("field") or "")
        value = payload.get("value")

        if not tx_id or not field:
            return

        row = self._find_row(tx_id)
        if not row:
            return

        if field in {"balance_before", "balance_after", "amount"}:
            view_val = dec(value)

            row[field] = change_currency_to(
                    amount=view_val,
                    view_currency=row.get("ccy") or "",
                    transaction_currency=self.view_currency.value,
                    rates=self.currency_rate,
                )
        else:
            row[field] = value if value != "" else None

        if field == "category":
            row["category_color"] = self._color_for_category(row.get("category"))
        if field == "status":
            row["status_color"] = self._color_for_status(row.get("status"))

        self._mark_dirty(tx_id, field, row.get(field))

    async def _on_tx_new_category(self, e) -> None:
        """Allow user to add a new category label on the fly (client-side only)."""      
        payload = e.args or {}
        val = (payload.get("value") or "").strip()
        if not val:
            return
        if val not in self.category_options:
            self.category_options.append(val)

        for r in self.rows:
            r["category_options"] = list(self.category_options)

    async def _on_save_clicked(self) -> None:
        """
        Save all dirty changes via batch update.

        Converts UI labels back into backend enum names:
        - TransactionCategory("Ubrania").name -> "CLOTHES"
        - TransactionStatus("Wydatek").name -> "EXPENSE"
        """
        if not self._dirty:
            ui.notify("No changes", type="info")
            return

        items: list[dict[str, Any]] = []
        for tx_id, patch in self._dirty.items():
            out: dict[str, Any] = {"id": str(tx_id)}
            for k, v in patch.items():
                if v is None:
                    continue
                
                if k == "category":
                    v = TransactionCategory(v).name   
                if k == "status":
                    v = TransactionStatus(v).name
                    
                out[k] = v
            items.append(out)
            
        req = BatchUpdateTransactionsRequest(items=items)

        ok = await self.wallet_client.batch_update_transactions(
            user_id=self.get_user_id(),
            req=req,
        )

        if not ok:
            ui.notify("Update failed", type="negative")
            return

        ui.notify("Saved", type="positive")
        await self._load_page()
        self._render_all()

    async def _on_accounts_change(self, e) -> None:
        """Accounts filter change handler."""
        vals = list(e.sender.value or [])
        if not vals:
            vals = [self.ALL_TOKEN]

        if self.ALL_TOKEN in vals and len(vals) > 1:
            vals = [self.ALL_TOKEN]

        self.state["account_values"] = vals
        self.state["page"] = 1
        await self._load_page()
        self._render_all()
        e.sender.run_method("hidePopup")

    async def _on_categories_change(self, e) -> None:
        """Category filter change handler."""
        self.state["categories"] = list(e.sender.value or [])
        self.state["page"] = 1
        await self._load_page()
        self._render_all()
        e.sender.run_method("hidePopup")

    async def _on_statuses_change(self, e) -> None:
        """Status filter change handler."""
        self.state["statuses"] = list(e.sender.value or [])
        self.state["page"] = 1
        await self._load_page()
        self._render_all()
        e.sender.run_method("hidePopup")

    async def _on_size_change(self, e) -> None:
        """Pager size changed."""
        v = e.sender.value
        try:
            self.state["size"] = int(v or 40)
        except Exception:
            self.state["size"] = 40
        self.state["page"] = 1
        await self._load_page()
        self._render_all()
        
    async def _on_delete_transaction(self, e) -> None:
        """Confirm and delete a transaction."""
        tx_id = str(e.args or "")
        if not tx_id:
            return

        dlg = ui.dialog()
        with dlg, ui.card().classes("w-[min(420px,95vw)]"):
            ui.label("Delete this transaction?").classes("text-base font-semibold q-mb-sm")
            ui.label("This cannot be undone.").classes("text-body2 text-grey-7")

            with ui.row().classes("justify-end gap-2 q-mt-sm"):
                ui.button("Cancel", on_click=dlg.close).props("flat")

                async def _do():
                    dlg.close()
                    ok = await self.wallet_client.delete_transaction(
                        user_id=self.get_user_id(),
                        transaction_id=uuid.UUID(tx_id),
                    )
                    if not ok:
                        ui.notify("Delete failed", type="negative")
                        return
                    ui.notify("Deleted", type="positive")
                    await self._load_page()
                    self._render_all()

                ui.button("Delete", on_click=_do).props("unelevated color=negative")

        dlg.open()

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
        """Set date range presets or enable custom date pickers."""
        self.range_state["value"] = mode

        if mode == "CUSTOM":
            if self.custom_row:
                self.custom_row.style("display:flex")
            return

        if self.custom_row:
            self.custom_row.style("display:none")

        today = datetime.now()
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

        ui.timer(0.01, self._reload_after_range, once=True)

    async def _reload_after_range(self) -> None:
        """Reload after changing date range."""
        self.state["page"] = 1
        await self._load_page()
        self._render_all()

    def _open_date_picker(self, title: str, which: str) -> None:
        """Open date picker to set 'from' or 'to' filter."""
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
                    ui.timer(0.01, self._reload_after_range, once=True)

                ui.button("OK", on_click=_ok).props("unelevated color=primary")

        dlg.open()
        
    def _sum_rows_in_view_ccy(self) -> Decimal:
        """
        Sum amounts of currently visible rows.
        """
        view_ccy = self.view_currency.value  
        total = Decimal("0")

        for r in self.rows:
            tx_ccy = (r.get("ccy") or "").strip()
            amt = r.get("amount") or Decimal("0")  
            if not tx_ccy:
                continue

            converted = change_currency_to(
                amount=amt,
                view_currency=view_ccy,
                transaction_currency=tx_ccy,
                rates=self.currency_rate,
            )
            total += converted

        return total

    def _sum_all_in_view_ccy(self) -> Decimal:
        """Uses backend aggregate: self.total_sum_by_ccy = { 'PLN': Decimal(...), 'EUR': Decimal(...), ... }"""
        view_ccy = self.view_currency.value  
        total = Decimal("0")

        for tx_ccy, amt in (self.total_sum_by_ccy or {}).items():
            tx_ccy = (tx_ccy or "").strip()
            if not tx_ccy:
                continue

            converted = change_currency_to(
                amount=Decimal(str(amt or "0")),
                view_currency=view_ccy,
                transaction_currency=tx_ccy,
                rates=self.currency_rate,
            )
            total += converted

        return total
    
    async def _open_add_transaction_dialog(self) -> None:
        """Open manual transaction creation dialog and refresh after success."""
        dlg = ui.dialog()
        with dlg:
            with ui.card().style('''
                max-width: 720px; width: 92vw;
                min-height:92vh;
                padding: 28px 24px;
                border-radius: 24px;
                background: linear-gradient(180deg, #ffffff 0%, #f6f9ff 100%);
                box-shadow: 0 10px 24px rgba(15,23,42,.06);
                border: 1px solid rgba(2,6,23,.06);
            '''):
                ui.icon('receipt_long').style(
                    'font-size:44px;color:#2563eb;background:#e0ecff;'
                    'padding:16px;border-radius:50%'
                )
                ui.label('Add transaction').classes('text-h5 text-weight-medium q-mb-xs text-center')
                ui.label('Create a manual transaction.').classes('text-body2 text-grey-8 q-mb-md text-center')

                with ui.element('div').style('max-height: 680px; overflow-y: auto; width:100%;'):
                    with ui.row().classes('w-full justify-center'):
                        body = ui.column().classes('q-gutter-sm').style('width:420px; max-width:100%;')

        async def _after():
            dlg.close()
            await self._load_page()
            self._render_all()

        accounts = {
            uuid.UUID(str(a.id)): a.name
            for a in (self.accounts or [])
        }

        await render_manual_transaction_form(
            self=self,
            container=body,
            accounts=accounts,
            on_success=_after,
            on_cancel=dlg.close,
        )
        dlg.open()


@ui.page('/transactions')
def transactions_page(request: Request):
    
    add_style()
    add_user_style()
    add_table_style()
    Transactions(request)
    
    
