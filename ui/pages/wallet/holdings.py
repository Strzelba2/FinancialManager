import uuid
from decimal import Decimal
from typing import Any, Optional
import logging

from nicegui import ui
from fastapi import Request

from static.style import add_style, add_user_style, add_table_style
from components.context.nav_context import NavContextBase
from components.navbar_footer import footer

from clients.wallet_client import WalletClient
from clients.nbp_client import NBPClient
from clients.stock_client import StockClient  

from schemas.wallet import Currency
from utils.money import dec, change_currency_to
from utils.utils import fmt_money

logger = logging.getLogger(__name__)


class HoldingsPage(NavContextBase):
    """
    NiceGUI page/controller for brokerage holdings.

    Features:
    - Loads brokerage accounts + holdings for the user (optionally filtered)
    - Aggregates holdings by SYMBOL or ACCOUNT+SYMBOL
    - Fetches latest quotes and computes value + PnL (and view currency conversions)
    - Renders header KPIs, filters, and a table
    """
    ALL_TOKEN = "__ALL__"

    def __init__(self, request: Request):
        super().__init__()
        self.request = request

        self.wallet_client = WalletClient()
        self.nbp_client = NBPClient()
        self.stock_client = StockClient()

        self.currency_rate: dict[str, Any] = {}
        self.view_currency: Currency = Currency.PLN

        self.brokerage_accounts: list[dict[str, Any]] = []
        self.brokerage_account_options: dict[str, str] = {"All": self.ALL_TOKEN}

        self.state: dict[str, Any] = {
            "brokerage_account_values": [self.ALL_TOKEN],
            "q": "",
            "view_ccy": Currency.PLN.value,
            "group_mode": "SYMBOL",  
            "auto_refresh": False,
        }

        self.rows: list[dict[str, Any]] = []
        self._q_timer = None
        self._refresh_timer = None

        self.header_card = None
        self.manage_card = None
        self.table_card = None

        ui.timer(0.01, self._init_async, once=True)

    def _selected_brokerage_account_ids(self) -> Optional[list[uuid.UUID]]:
        """
        Convert selected brokerage account values into UUIDs.

        Returns:
            - None when ALL is selected (meaning no filtering)
            - list[UUID] for specific accounts
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
        """Async init: navbar, FX rates, build layout containers, load initial data, render."""
        self.render_navbar()
        self.currency_rate = await self.nbp_client.get_usd_eur_pln()

        with ui.column().classes("w-[100vw] gap-1"):
            self.header_card = ui.card().classes("elevated-card q-pa-sm q-mb-md").style(
                "width:min(1600px,98vw); margin:0 auto 1px;"
            )
            self.manage_card = ui.card().classes("elevated-card q-pa-sm q-mb-md").style(
                "width:min(1600px,98vw); margin:0 auto 1px;"
            )
            self.table_card = ui.card().classes("elevated-card q-pa-sm q-mb-md").style(
                "width:min(1600px,98vw); margin:0 auto 1px;"
            )

        await self._load_brokerage_accounts()
        await self._load_page()
        self._render_all()
        footer()

    async def _load_brokerage_accounts(self) -> None:
        """Load brokerage accounts and build select options."""
        user_id = self.get_user_id()
        raw = await self.wallet_client.list_brokerage_accounts_for_user(user_id=user_id) or []
        self.brokerage_accounts = raw

        self.brokerage_account_options = {"All": self.ALL_TOKEN}
        for a in raw:
            _id = a.get("id")
            name = a.get("name") or str(_id) or "Account"
            if _id:
                self.brokerage_account_options[str(_id)] = str(name)

    async def _load_page(self) -> None:
        """
        Load holdings list based on filters, aggregate them, load latest quotes,
        compute PnL and (optionally) view currency conversions.
        """
        
        user_id = self.get_user_id()
        brokerage_ids = self._selected_brokerage_account_ids()
        q = (self.state.get("q") or "").strip() or None
        group_mode = self.state.get("group_mode") or "SYMBOL"
        view_ccy = self.view_currency.value

        holdings_raw = await self.wallet_client.list_holdings_for_user(
            user_id=user_id,
            brokerage_account_ids=brokerage_ids,
            q=q,
        ) or []

        agg: dict[str, dict[str, Any]] = {}
        for h in holdings_raw:
            symbol = (h.instrument_symbol or "").strip()
            if not symbol:
                continue

            account_name = h.account_name or "Account"
            name = h.instrument_name or ""
            ccy = (h.instrument_currency or "").strip() or "—"

            qty = dec(h.quantity or 0)
            avg_cost = dec(h.avg_cost or 0)

            if group_mode == "ACCOUNT":
                key = f'{h.account_id}::{symbol}'
            else:
                key = symbol

            rec = agg.get(key)
            if rec is None:
                rec = agg[key] = {
                    "key": key,
                    "symbol": symbol,
                    "name": name,
                    "currency": ccy,
                    "accounts": set(),
                    "total_qty": Decimal("0"),
                    "total_cost": Decimal("0"),  
                }

            rec["accounts"].add(account_name)
            rec["total_qty"] += qty
            rec["total_cost"] += (qty * avg_cost)

        symbols = sorted({v["symbol"] for v in agg.values()})
        quotes_map = await self.stock_client.get_latest_quotes_for_symbols(symbols=symbols) if symbols else {}

        rows: list[dict[str, Any]] = []
        total_value_view = Decimal("0")
        total_cost_view = Decimal("0")

        for rec in agg.values():
            qty = dec(rec["total_qty"])
            cost = dec(rec["total_cost"])
            symbol = rec["symbol"]
            name = rec["name"]
            ccy = rec["currency"]

            quote = quotes_map.get(symbol)
            price = dec(getattr(quote, "price", None) if quote else 0)
            quote_ccy = getattr(quote, "currency", None) if quote else None
            if quote_ccy:
                ccy = str(quote_ccy)

            value = qty * price
            pnl_amount = value - cost
            pnl_pct = (pnl_amount / cost) if cost > 0 else Decimal("0")

            def _to_view(amount: Decimal, src_ccy: str) -> Optional[Decimal]:
                """Convert amount from src_ccy into view currency. Returns None if conversion is not possible."""
                src_ccy = (src_ccy or "").strip()
                if not src_ccy or src_ccy == "—":
                    return None
                try:
                    return change_currency_to(
                        amount=amount,
                        view_currency=view_ccy,
                        transaction_currency=src_ccy,
                        rates=self.currency_rate,
                    )
                except Exception:
                    logger.warning(f"No FX rate for {src_ccy}->{view_ccy}")
                    return None

            cost_view = _to_view(cost, ccy)
            value_view = _to_view(value, ccy)
            pnl_view = _to_view(pnl_amount, ccy)

            if value_view is not None:
                total_value_view += value_view
            if cost_view is not None:
                total_cost_view += cost_view
                
            if len(rec["accounts"]) > 1:
                accounts = len(rec["accounts"])
            else:
                accounts = next(iter(rec["accounts"]))

            rows.append(
                {
                    "id": rec["key"],
                    "symbol": symbol,
                    "name": name,
                    "accounts_disp": ", ".join(sorted(rec["accounts"])),
                    "accounts": accounts,
                    "currency": ccy,

                    "quantity": qty,
                    "avg_cost": (cost / qty) if qty > 0 else Decimal("0"),
                    "price": price,

                    "cost": cost,
                    "value": value,
                    "pnl_amount": pnl_amount,
                    "pnl_pct": pnl_pct,

                    "cost_view": cost_view,
                    "value_view": value_view,
                    "pnl_view": pnl_view,
                    "value_sort": float(value_view) if value_view is not None else float(value),
                    "pnl_pct_sort": float(pnl_pct),
                }
            )

        self.rows = rows

        self._total_value_view = total_value_view
        self._total_cost_view = total_cost_view

    def _render_all(self) -> None:
        """Render header, filter controls, and table."""
        self._render_header()
        self._render_manage()
        self._render_table()

    def _render_header(self) -> None:
        """Render total value + PnL KPI chips and top losers/gainers chips."""
        self.header_card.clear()
        view_ccy = self.view_currency.value

        total_value = getattr(self, "_total_value_view", Decimal("0"))
        total_cost = getattr(self, "_total_cost_view", Decimal("0"))
        total_pnl = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost) if total_cost > 0 else Decimal("0")

        losers, gainers = self._top_n(5)

        with self.header_card:
            with ui.row().style(
                "display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; width:100%; padding:1px 20px;"
            ):
                ui.label("Holdings").classes("header-title")

                with ui.row().style("display:flex; align-items:center; flex-wrap:wrap; gap:10px;"):
                    ui.html(
                        f'<div class="balance-pill pos">'
                        f'<span class="label">Value:</span>'
                        f'<span class="amount">{fmt_money(total_value, view_ccy)}</span>'
                        f"</div>"
                    )
                    pnl_class = "pos" if total_pnl >= 0 else "neg"
                    ui.html(
                        f'<div class="balance-pill {pnl_class}">'
                        f'<span class="label">PnL:</span>'
                        f'<span class="amount">{fmt_money(total_pnl, view_ccy)} '
                        f'({(total_pnl_pct * 100):.2f}%)</span>'
                        f"</div>"
                    )

                with ui.row().style("width:100%; display:flex; justify-content:center; align-items:center; flex-wrap:wrap; gap:8px;"):
                    if losers:
                        ui.label("Top losers:").classes("text-caption text-grey-7")
                        for r in losers:
                            ui.chip(f'{r["symbol"]} {(r["pnl_pct"]*100):.1f}%', color="negative", text_color="white").props("dense")
                    if gainers:
                        ui.label("Top gainers:").classes("text-caption text-grey-7 q-ml-md")
                        for r in gainers:
                            ui.chip(f'{r["symbol"]} {(r["pnl_pct"]*100):.1f}%', color="positive", text_color="white").props("dense")

    def _top_n(self, n: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Return (losers, gainers) based on pnl_pct among current rows."""
        if not self.rows:
            return [], []
        losers = sorted(self.rows, key=lambda r: r.get("pnl_pct", Decimal("0")))[:n]
        gainers = sorted(self.rows, key=lambda r: r.get("pnl_pct", Decimal("0")), reverse=True)[:n]
        return losers, gainers

    def _render_manage(self) -> None:
        """Render filters (accounts, search, view currency, grouping) and refresh button."""
        self.manage_card.clear()

        with self.manage_card:
            with ui.row().style(
                "display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; width:100%; padding:1px 30px;"
            ):
                with ui.row().style("display:flex; align-items:center; flex-wrap:wrap; gap:10px;"):
                    sel_acc = (
                        ui.select(
                            self.brokerage_account_options,
                            multiple=True,
                            value=self.state["brokerage_account_values"],
                            label="Brokerage accounts",
                        )
                        .classes("filter-field min-w-[220px] w-[300px]")
                        .props("outlined dense use-chips options-dense clearable color=primary popup-content-class=filter-popup")
                    )
                    sel_acc.on("update:model-value", self._on_accounts_change)

                    q_in = ui.input(
                        value=self.state.get("q", ""), 
                        label="Instrument search",
                        on_change=lambda e: self._on_q_typing(e)
                        ) \
                        .classes("filter-field min-w-[220px] w-[280px]")
                    q_in.props("outlined dense clearable")

                    view_ccy_sel = (
                        ui.select([c.value for c in Currency], value=self.state.get("view_ccy", "PLN"), label="View currency")
                        .classes("filter-field min-w-[150px] w-[180px]")
                        .props("outlined dense options-dense clearable color=primary popup-content-class=filter-popup")
                    )
                    view_ccy_sel.on("update:model-value", self._on_view_ccy_change)

                    group_sel = (
                        ui.select(["SYMBOL", "ACCOUNT"], value=self.state.get("group_mode", "SYMBOL"), label="Grouping")
                        .classes("filter-field min-w-[150px] w-[180px]")
                        .props("outlined dense options-dense color=primary popup-content-class=filter-popup")
                    )
                    group_sel.on("update:model-value", self._on_group_change)

                with ui.row().style("display:flex; align-items:center; flex-wrap:wrap; gap:10px;"):
                    ui.button("Refresh quotes", icon="refresh", on_click=self._reload).props("unelevated color=primary")

    def _render_table(self) -> None:
        """Render holdings table with formatted numeric cells and view-currency fallbacks."""
        self.table_card.clear()
        view_ccy = self.view_currency.value

        with self.table_card:
            cols = [
                {"name": "symbol", "label": "Symbol", "field": "symbol", "align": "left", "sortable": True, "style": "width:110px;white-space:nowrap;"},
                {"name": "name", "label": "Name", "field": "name", "align": "left", "sortable": True, "style": "min-width:260px;white-space:normal; word-break:break-word;"},
                {"name": "quantity", "label": "Qty", "field": "quantity", "align": "right", "sortable": True, "style": "width:130px;white-space:nowrap;"},
                {"name": "avg_cost", "label": "Avg buy", "field": "avg_cost", "align": "right", "sortable": True, "style": "width:150px;white-space:nowrap;"},
                {"name": "price", "label": "Price", "field": "price", "align": "right", "sortable": True, "style": "width:150px;white-space:nowrap;"},
                {"name": "value", "label": "Value", "field": "value_sort", "align": "right", "sortable": True, "style": "width:170px;white-space:nowrap;"},
                {"name": "pnl_pct", "label": "PnL %", "field": "pnl_pct_sort", "align": "right", "sortable": True, "style": "width:120px;white-space:nowrap;"},
                {"name": "accounts", "label": "Accounts", "field": "accounts", "align": "center", "sortable": True, "style": "width:110px;white-space:nowrap;"},
            ]

            tbl = (
                ui.table(columns=cols, rows=self.rows, row_key="id")
                .props('flat separator=horizontal wrap-cells table-style="width:100%;table-layout:auto" rows-per-page=0')
                .classes("q-mt-none w-full table-modern")
            )

            tbl.add_slot("body-cell-quantity", r"""
            <q-td :props="props" class="num">
              <span>{{ Number(props.row.quantity).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 6 }) }}</span>
            </q-td>
            """)

            tbl.add_slot("body-cell-avg_cost", rf"""
            <q-td :props="props" class="num">
            <span>
                {{{{
                (props.row.cost_view != null && props.row.quantity)
                    ? Number(props.row.cost_view / props.row.quantity).toLocaleString('pl-PL', {{ minimumFractionDigits: 2, maximumFractionDigits: 4 }}) + ' {view_ccy}'
                    : Number(props.row.avg_cost).toLocaleString('pl-PL', {{ minimumFractionDigits: 2, maximumFractionDigits: 4 }}) + ' ' + props.row.currency
                }}}}
            </span>
            </q-td>
            """)

            tbl.add_slot("body-cell-price", rf"""
            <q-td :props="props" class="num">
            <span>
                {{{{
                (props.row.value_view != null && props.row.quantity)
                    ? Number(props.row.value_view / props.row.quantity).toLocaleString('pl-PL', {{ minimumFractionDigits: 2, maximumFractionDigits: 4 }}) + ' {view_ccy}'
                    : Number(props.row.price).toLocaleString('pl-PL', {{ minimumFractionDigits: 2, maximumFractionDigits: 4 }}) + ' ' + props.row.currency
                }}}}
            </span>
            </q-td>
            """)

            tbl.add_slot("body-cell-value", rf"""
            <q-td :props="props" class="num">
            <span>
                {{{{
                (props.row.value_view != null)
                    ? Number(props.row.value_view).toLocaleString('pl-PL', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}) + ' {view_ccy}'
                    : Number(props.row.value).toLocaleString('pl-PL', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}) + ' ' + props.row.currency
                }}}}
            </span>
            </q-td>
            """)

            tbl.add_slot("body-cell-pnl_pct", r"""
            <q-td :props="props" class="num">
              <q-chip dense square class="chip-soft"
                      :color="(props.row.pnl_pct >= 0) ? 'positive' : 'negative'"
                      text-color="white">
                {{ (Number(props.row.pnl_pct) * 100).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}%
              </q-chip>
            </q-td>
            """)

    async def _reload(self) -> None:
        """Reload data and rerender UI."""
        await self._load_page()
        self._render_all()

    async def _on_accounts_change(self, e) -> None:
        """Handle brokerage account filter changes."""
        vals = list(e.sender.value or [])
        if not vals:
            vals = [self.ALL_TOKEN]
        if self.ALL_TOKEN in vals and len(vals) > 1:
            vals = [self.ALL_TOKEN]
        self.state["brokerage_account_values"] = vals
        await self._reload()

    def _on_q_typing(self, e) -> None:
        """Debounced search input handler."""
        self.state["q"] = (e.value or "").strip()

        if self._q_timer:
            self._q_timer.cancel()
        self._q_timer = ui.timer(0.8, self._reload, once=True)

    async def _on_view_ccy_change(self, e) -> None:
        """Change view currency and reload."""
        v = e.sender.value or "PLN"
        try:
            self.view_currency = Currency(v)
        except Exception:
            self.view_currency = Currency.PLN
        self.state["view_ccy"] = self.view_currency.value
        await self._reload()

    async def _on_group_change(self, e) -> None:
        """Change grouping mode (SYMBOL/ACCOUNT) and reload."""
        self.state["group_mode"] = e.sender.value or "SYMBOL"
        await self._reload()


@ui.page("/brokerage/holdings")
def holdings_page(request: Request):
    add_style()
    add_user_style()
    add_table_style()
    HoldingsPage(request)