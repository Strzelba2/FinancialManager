from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Optional
from types import SimpleNamespace
import logging

from nicegui import ui

from clients.wallet_client import WalletClient
from clients.stock_client import StockClient
from clients.nbp_client import NBPClient
from static.style import add_style, add_user_style
from components.context.nav_context import NavContextBase
from components.navbar_footer import footer
from components.wallet import render_rename_wallet_dialog
from components.transaction import render_add_transaction_dialog
from components.account import render_delete_account_dialog
from components.brokerage_event import render_add_event_dialog
from components.investments import render_add_metal_dialog, render_add_property_dialog
from schemas.wallet import Currency, AccountType
from utils.money import (
    dec, change_currency_to, share_pct_str, pct_change, fmt_pct, pct_color
)
from utils.utils import fmt_money
from utils.dates import month_key, prev_month_key

logger = logging.getLogger(__name__)


class WalletManager(NavContextBase):
    """
    Wallet Manager page/controller.

    Responsibilities:
    - Fetch wallet-manager tree data from wallet-service
    - Fetch currency rates (NBP client)
    - Render the NiceGUI UI (header + wallet tree)
    - Provide dialog openers (rename wallet, add transaction/event, delete account, etc.)

    Notes:
        - UI is built after async initialization (`_init_async`) scheduled by `ui.timer`.
        - On service failure, the manager falls back to demo data.
    """
    def __init__(self) -> None:
        """
        Initialize clients, dialog factories, UI state, and schedule async init.
        """
        logger.info("Request: WalletManager.__init__")
        self.wallet_client = WalletClient()
        self.stock_client = StockClient()
        self.nbp_client = NBPClient()
        
        self.open_rename_wallet_dialog = render_rename_wallet_dialog(self)
        self.open_add_transaction_dialog = render_add_transaction_dialog(self)
        self.open_delete_account_dialog = render_delete_account_dialog(self)
        self.open_add_event_dialog = render_add_event_dialog(self)
        self.open_add_metal_buy_dialog = render_add_metal_dialog(self)
        self.open_add_property_dialog = render_add_property_dialog(self)

        self.state = {
            "view_ccy": "PLN",
        }

        self.header_card = None
        self.tree_card = None
        
        ui.timer(0.01, self._init_async, once=True)
        
    async def fetch_data(self):
        """
        Fetch required data for rendering (rates + wallet tree).

        On failures, the method falls back to demo data.

        Returns:
            None
        """
        logger.info("Request: WalletManager.fetch_data")
        try:
            self.currency_rate = await self.nbp_client.get_usd_eur_pln()
            self.user_id = self.get_user_id()

            data = await self.wallet_client.get_wallet_manager_tree(user_id=self.user_id, currency_rate=self.currency_rate, months=2)
            
            if data:
                logger.info(f"Response: WalletManager.fetch_data ok wallets_count={len(data)}")
                self.data = data
            else:
                logger.warning("Response: WalletManager.fetch_data -> using demo data (tree=None/empty)")
                self.data = self._demo_data()
        except Exception as ex:
            logger.exception(f"Error: WalletManager.fetch_data ex={ex!r} -> using demo data")
            self.data = self._demo_data()
    
    async def _init_async(self):
        """
        Async initializer scheduled from `__init__`.
        """
        await self.fetch_data()    
        self._build()

    def _demo_data(self) -> list[dict[str, Any]]:
        """
        Return local demo data used when wallet-service is unavailable.

        Returns:
            A list of wallet dictionaries in the same format as `/wallet/manager/tree`.
        """
        return [
            {
                "id": str(uuid.uuid4()),
                "name": "Main Wallet",
                "base_ccy": "PLN",
                "health": {"needs_review": False},
                "deposit_accounts": [
                    {
                        "id": str(uuid.uuid4()),
                        "name": "mBank · Personal",
                        "ccy": "PLN",
                        "available": dec("12850.20"),
                        "tx_per_month": 42,
                        "health": {},
                        "snapshots": {
                            "2025-12": {"ccy": "PLN", "available": dec("12000.00")},
                        },
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "name": "PKO · Savings",
                        "ccy": "PLN",
                        "available": dec("56000.00"),
                        "tx_per_month": 3,
                        "health": {},
                        "snapshots": {
                            "2025-12": {"ccy": "PLN", "available": dec("12000.00")},
                        },
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "name": "Revolut · EUR",
                        "ccy": "EUR",
                        "available": dec("920.15"),
                        "tx_per_month": 11,
                        "health": {"needs_review": True},
                        "snapshots": {
                            "2025-12": {"ccy": "EUR", "available": dec("12000.00")},
                        },
                    },
                ],
                "brokerage_accounts": [
                    {
                        "id": "BRO-1",
                        "name": "XTB Main",
                        "ccy": "PLN", 
                        "cash_accounts": [
                            {"deposit_account_id": "DEP-PLN", "name": "Cash PLN", "ccy": "PLN", "available": dec("12000.00")},
                            {"deposit_account_id": "DEP-EUR", "name": "Cash EUR", "ccy": "EUR", "available": dec("1500.00")},
                            {"deposit_account_id": "DEP-USD", "name": "Cash USD", "ccy": "USD", "available": dec("800.00")},
                        ],
                        "sum_cash_accounts": dec("20400.00"),  
                        "positions": [
                            {"symbol": "AAPL", "mic": "XNAS", "value": dec("950.00"), "value_default_ccy": dec("3800.00"),
                             "pnl_pct": dec("0.12"), "currency": "USD"},
                            {"symbol": "ASML", "mic": "XAMS", "value": dec("600.00"), "value_default_ccy": dec("2700.00"),
                             "pnl_pct": dec("-0.04"), "currency": "EUR"},
                        ],
                        "positions_count": 2,
                        "positions_value": dec("6500.00"),     
                        "events_per_month": 14,
                        "health": {"missing_quotes": 0},
                        "snapshots": {
                            "2025-12": {"ccy": "PLN", "cash": dec("19000.00"), "stocks": dec("6100.00")}
                        },
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "name": "mBank · Brokerage",
                        "ccy": "PLN",
                        "cash_account": [{
                            "deposit_account_id": str(uuid.uuid4()),
                            "name": "mBank Brokerage Cash",
                            "ccy": "PLN",
                            "available": dec("1200.00"),
                        }],
                        "sum_cash_accounts": dec("1200.00"),
                        "positions": [
                            {"symbol": "CDR", "mic": "XWAR", "value": dec("8400.00"), 
                             "value_default_ccy": dec("8400.00"), "pnl_pct": dec("-0.12"), "currency": "EUR"},
                            {"symbol": "PKO", "mic": "XWAR", "value": dec("2250.00"), 
                             "value_default_ccy": dec("2250.00"), "pnl_pct": dec("0.08"), "currency": "EUR"},
                        ],
                        "positions_count": 2,
                        "positions_value": dec("10650.00"),
                        "events_per_month": 2,
                        "health": {"missing_quotes": 0, "stale_quotes": True, "projection_mismatch": True},
                        "snapshots": {
                            "2025-12": {"ccy": "USD", "cash": dec("380.00"), "stocks": dec("2400.00")},
                        },
                    },
                ],
                "metals": {
                    "count": 2,
                    "value": dec("18900.00"),
                    "ccy": "PLN",
                    "health": {},
                },
                "real_estate": {
                    "count": 1,
                    "value": dec("410000.00"),
                    "ccy": "PLN",
                    "health": {},
                },
                "snapshots": {
                    "2025-12": {
                        "ccy": "PLN",
                        "cash_deposit": dec("64000"),
                        "cash_broker": dec("3500"),
                        "stocks": dec("12000"),
                        "metals": dec("17500"),
                        "real_estate": dec("405000"),
                    }
                },
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Business Wallet",
                "base_ccy": "EUR",
                "health": {"needs_review": True},
                "deposit_accounts": [
                    {
                        "id": str(uuid.uuid4()),
                        "name": "ING · Company EUR",
                        "ccy": "EUR",
                        "available": dec("15400.00"),
                        "tx_per_month": 58,
                        "health": {},
                        "snapshots": {
                            "2025-12": {"ccy": "EUR", "available": dec("12000.00")},
                        },
                    },
                ],
                "brokerage_accounts": [],
                "metals": {"count": 0, "value": dec("0"), "ccy": "EUR", "health": {}},
                "real_estate": {"count": 0, "value": dec("0"), "ccy": "EUR", "health": {}},
                "snapshots": {
                    "2025-12": {
                        "ccy": "PLN",
                        "cash_deposit": dec("64000"),
                        "cash_broker": dec("3500"),
                        "stocks": dec("12000"),
                        "real_estate": dec("405000"),
                    }
                },
            },
        ]
        
    def _make_group_expansion(
        self,
        icon: str,
        title: str,
        count: int,
        total_view: Optional[Decimal] = None,
        mom: Optional[Decimal] = None,
        opened: bool = True,
    ):
        """
        Create a Quasar expansion item header for a group section (e.g., Deposit accounts, Brokerage accounts).

        Args:
            icon: Quasar icon name.
            title: Group title displayed in the header.
            count: Number of items in the group.
            total_view: Group total value already converted to view currency.
            mom: Month-over-month change (fraction, e.g. 0.05 for +5%) or None.
            opened: If True, the expansion is opened by default.

        Returns:
            A NiceGUI element representing a `q-expansion-item`.
        """
        view = self.state["view_ccy"]
        total_txt = fmt_money(total_view, view)
        mom_txt = fmt_pct(mom)
        mom_col = pct_color(mom)

        exp = ui.element("q-expansion-item").classes("w-full").props(
            f"dense icon={icon} {'default-opened' if opened else ''}"
        )

        exp.add_slot(
            "header",
            rf"""
            <q-item-section avatar>
                <q-icon name="{icon}" />
            </q-item-section>

            <q-item-section>
                <div class="text-weight-medium">{title}</div>
            </q-item-section>

            <q-item-section side class="wm-side-stretch">
                <div class="row items-stretch wm-right">
                <div class="wm-pill"><b>Count</b>: {count}</div>
                <div class="wm-pill"><b>Balance</b>: {total_txt}</div>

                <q-chip
                    square
                    class="wm-chip-stretch"
                    color="{mom_col}"
                    text-color="white"
                >
                    {mom_txt}
                </q-chip>
                </div>
            </q-item-section>
            """,
            )
        return exp
    
    def _make_broker_account_expansion(
        self,
        b: dict,
        cash_view: Optional[Decimal] = None,
        pos_view: Optional[Decimal] = None,
        icon: str = "trending_up",
        mom: Optional[Decimal] = None,
        opened: bool = False,
    ):
        """
        Create an expansion header for a single brokerage account.

        Args:
            b: Brokerage account dict (expects fields like `name`, `positions_count`).
            cash_view: Cash value already converted to view currency.
            pos_view: Positions value already converted to view currency.
            icon: Quasar icon name.
            mom: Month-over-month change (fraction) or None.
            opened: If True, the expansion is opened by default.

        Returns:
            A NiceGUI element representing a `q-expansion-item`.
        """
        view = self.state["view_ccy"]

        name = b.get("name", "Brokerage")
        cash_txt = fmt_money(cash_view, view)
        pos_cnt = int(b.get("positions_count", 0) or 0)
        pos_txt = fmt_money(pos_view, view)

        total_view = None if (cash_view is None or pos_view is None) else (cash_view + pos_view)
        total_txt = fmt_money(total_view, view)

        mom_txt = fmt_pct(mom)
        mom_col = pct_color(mom)

        exp = ui.element("q-expansion-item").classes("w-full").props(
            f"dense icon={icon} {'default-opened' if opened else ''}"
        )

        exp.add_slot(
            "header",
            f"""
            <q-item-section avatar>
            <q-icon name="{icon}" />
            </q-item-section>

            <q-item-section>
            <div class="text-weight-medium">{name}</div>
            </q-item-section>

            <q-item-section side class="wm-side-stretch">
            <div class="row items-stretch wm-right">
                <div class="wm-pill"><b>Cash</b>: {cash_txt}</div>
                <div class="wm-pill"><b>Positions</b>: {pos_cnt} ({pos_txt})</div>
                <div class="wm-pill"><b>Total</b>: {total_txt}</div>

                <q-chip square class="wm-chip-stretch" color="{mom_col}" text-color="white">
                {mom_txt}
                </q-chip>
            </div>
            </q-item-section>
            """,
        )
        return exp
    
    def _make_wallet_expansion(
        self,
        w: dict,
        cur: dict,              
        prev: Optional[dict] = None, 
        opened: bool = False,
    ):
        """
        Create an expansion header for a wallet summary row.

        Args:
            w: Wallet dict (expects at least `name`).
            cur: Current wallet breakdown dict (expects `total`, `cash_total`, `stocks`, `metals`, `real_estate`).
            prev: Previous snapshot breakdown dict in view currency (optional).
            opened: If True, the expansion is opened by default.

        Returns:
            A NiceGUI element representing a `q-expansion-item`.
        """
        view = self.state["view_ccy"]

        total = cur.get("total")
        cash = cur.get("cash_total")
        stocks = cur.get("stocks")
        metals = cur.get("metals")
        re = cur.get("real_estate")

        title = w.get("name", "Wallet")

        total_txt = fmt_money(total, view) 
        cash_sh = share_pct_str(cash, total)
        stocks_sh = share_pct_str(stocks, total)
        metals_sh = share_pct_str(metals, total)
        re_sh = share_pct_str(re, total)

        mom = None
        if prev and prev.get("total") is not None and total is not None:
            mom = pct_change(total, prev.get("total"))

        mom_txt = fmt_pct(mom)
        mom_col = pct_color(mom)

        exp = ui.element("q-expansion-item").classes("w-full").props(
            f"dense icon=account_balance_wallet {'default-opened' if opened else ''}"
        )

        exp.add_slot(
            "header",
            f"""
            <q-item-section avatar>
            <q-icon name="account_balance_wallet" />
            </q-item-section>

            <q-item-section>
            <div class="text-weight-medium">{title}</div>
            </q-item-section>

            <q-item-section side class="wm-side-stretch">
            <div class="row items-stretch wm-right" style="flex-wrap:wrap; gap:8px;">
                <div class="wm-pill"><b>Total</b>: {total_txt}</div>
                <div class="wm-pill"><b>Cash</b> {cash_sh}</div>
                <div class="wm-pill"><b>Stocks</b> {stocks_sh}</div>
                <div class="wm-pill"><b>Metals</b> {metals_sh}</div>
                <div class="wm-pill"><b>RE</b> {re_sh}</div>

                <q-chip square class="wm-chip-stretch" color="{mom_col}" text-color="white">
                {mom_txt}
                </q-chip>
            </div>
            </q-item-section>
            """,
        )
        return exp
    
    def _build(self) -> None:
        """
        Build the page UI skeleton (cards) and render header + tree.
        """
        self.render_navbar()
        with ui.column().classes("w-[100vw] gap-3"):
            self.header_card = ui.card().classes("wm-card wm-wrap") \
                .style("width:min(1600px,98vw); margin:0 auto 1px; padding: 14px 30px;")
            self.tree_card = ui.card().classes("wm-card wm-wrap") \
                .style("width:min(1600px,70vw); margin:0 auto 1px; padding: 40px 12px;  min-height:68vh;")
            
        self._render_header()
        self._render_tree()
        footer()

    def _render_header(self) -> None:
        """
        Render the header card (title, snapshot button, currency selector).
        """
        logger.debug("Request: WalletManager._render_header")
        
        self.header_card.clear()
        with self.header_card:
            with ui.row().classes("w-full items-center").style("gap:12px;"):
                with ui.column().style("gap:2px;"):
                    ui.label("Wallet Manager").classes("wm-title")
                    ui.label("One view: wallets → accounts → brokerage package → metals/real estate (summary only).") \
                        .classes("wm-sub")

                with ui.row().style("margin-left:auto;"):
                    ui.button("Create monthly snapshot", icon="photo_camera") \
                        .props("unelevated no-caps color=primary") \
                        .on_click(self.create_monthly_snapshot)
                    
                    self.view_currency = (
                        ui.select([c.value for c in Currency], value=self.state.get("currency", "PLN"), label="Waluta")
                        .classes("filter-field min-w-[160px] w-[180px]") 
                        .props("outlined dense options-dense clearable color=primary popup-content-class=filter-popup")
                    )
                    with self.view_currency.add_slot("prepend"):
                        ui.icon("currency_exchange").classes("text-primary")

                    self.view_currency.on("update:model-value", self.on_currency_change)
        
    async def on_currency_change(self):
        """
        Update view currency and re-render the tree.
        """
        logger.info("Request: on_currency_change")

        self.state["view_ccy"] = self.view_currency.value
        self._render_tree()
    
    def _deposit_group_header(self, w: dict, view: str, cur, prev) -> str:
        """
        Build header inputs for the "Deposit accounts" group.

        Args:
            w: Wallet dict containing `deposit_accounts`.
            view: View currency code (currently not used, but kept for symmetry/future use).
            cur: Current wallet breakdown in view currency (expects key `cash_deposit`).
            prev: Previous snapshot breakdown in view currency (expects key `cash_deposit`) or None.

        Returns:
            Tuple: (deposit_accounts, current_value, mom_change)
            - deposit_accounts: list of deposit account dicts
            - current_value: current cash deposit value in view currency (may be None)
            - mom_change: month-over-month change fraction (e.g. 0.05 for +5%), or None
        """
        cur_val = cur["cash_deposit"]
        prev_val = prev["cash_deposit"] if prev else None

        mom = pct_change(cur_val, prev_val)
        dep = (w.get("deposit_accounts") or [])
        return dep, cur_val, mom

    def _brokerage_group_header(self, w: dict, view: str, cur, prev) -> str:
        """
        Build header inputs for the "Brokerage accounts" group.

        The group total is `stocks + cash_broker` in view currency when both parts are available.

        Args:
            w: Wallet dict containing `brokerage_accounts`.
            view: View currency code (currently not used, but kept for symmetry/future use).
            cur: Current wallet breakdown in view currency (expects keys `stocks`, `cash_broker`).
            prev: Previous snapshot breakdown in view currency (expects keys `stocks`, `cash_broker`) or None.

        Returns:
            Tuple: (brokerage_accounts, current_value, mom_change)
            - brokerage_accounts: list of brokerage account dicts
            - current_value: current brokerage total in view currency (may be None)
            - mom_change: month-over-month change fraction (e.g. -0.02 for -2%), or None
        """
        cur_val = None if (cur["stocks"] is None or cur["cash_broker"] is None) else (cur["stocks"] + cur["cash_broker"])
        prev_val = None if not prev else (prev["stocks"] + prev["cash_broker"])

        mom = pct_change(cur_val, prev_val)
        bro = (w.get("brokerage_accounts") or [])
        return bro, cur_val, mom
        
    def _render_tree(self) -> None:
        """
        Render the full wallet tree into `tree_card` based on current view currency.
        """
        
        self.tree_card.clear()
        view = self.state["view_ccy"]

        with self.tree_card:
            for w in self.data:
                dep_cnt = len(w.get("deposit_accounts", []))
                bro_cnt = len(w.get("brokerage_accounts", []))
                cur = self._wallet_breakdown(w, view)
                key = month_key()
                prev_key = prev_month_key(key)
                prev = self._snapshot_breakdown_in_view(w, prev_key, view)

                with ui.card().classes("wm-exp-card wm-exp-wrap"):
                    wallet_exp = self._make_wallet_expansion(w=w, cur=cur, prev=prev, opened=False)
                    with wallet_exp:
                        with ui.card().classes("wm-inner-card").style("width:100%; margin-top:10px;"):
                            with ui.row().classes("w-full items-center").style("justify-content:space-between; gap:12px;"):
                                with ui.row().style("display:flex; gap:10px; align-items:center; flex-wrap:wrap;"):
                                    ui.html(f'<div class="wm-pill"><b>Deposit</b>: {dep_cnt}</div>')
                                    ui.html(f'<div class="wm-pill"><b>Brokerage</b>: {bro_cnt}</div>')
                                self._wallet_menu_button(w)

                        with ui.card().classes("wm-subexp-card wm-exp-wrap").style("width:100%; margin-top:10px;"): 
                            dep, dep_total, dep_mom = self._deposit_group_header(w, view, cur, prev)
                            dep_exp = self._make_group_expansion(
                                icon="account_balance",
                                title="Deposit accounts",
                                count=len(dep),
                                total_view=dep_total,
                                mom=dep_mom,
                                opened=True,
                            )
                            with dep_exp:
                                self._render_deposit_nodes(w) 

                        with ui.card().classes("wm-subexp-card wm-exp-wrap").style("width:100%; margin-top:10px;"):
                            bro, bro_total, bro_mom = self._brokerage_group_header(w, view, cur, prev)
                            bro_exp = self._make_group_expansion(
                                icon="show_chart",
                                title="Brokerage accounts",
                                count=len(bro),
                                total_view=bro_total,
                                mom=bro_mom,
                                opened=True,
                            )
                            with bro_exp:
                                self._render_brokerage_nodes(w)
                                alloc = self._broker_mic_allocation(w, view)
                                self._render_market_allocation_mic_footer(alloc=alloc)
                                
                        with ui.card().classes("wm-subexp-card wm-exp-wrap").style("width:100%; margin-top:10px;"):
                            met_total, met_mom = self._metals_header(w, view, cur["metals"], prev)
                            m_exp = self._make_group_expansion(
                                icon="savings",
                                title="Metals",
                                count=int((w.get("metals") or {}).get("count", 0)),
                                total_view=met_total,
                                mom=met_mom,
                                opened=False,
                            )
                            with m_exp:
                                self._render_metals_node(w)

                        with ui.card().classes("wm-subexp-card wm-exp-wrap").style("width:100%; margin-top:10px;"):
                            re_total, re_mom = self._real_estate_header(w, view, cur["real_estate"], prev)
                            re_exp = self._make_group_expansion(
                                icon="home",
                                title="Real estate",
                                count=int((w.get("real_estate") or {}).get("count", 0)),
                                total_view=re_total,
                                mom=re_mom,
                                opened=False,
                            )
                            with re_exp:
                                self._render_real_estate_node(w)
                            
    def _menu_button(self, items: list[tuple[str, str, callable]]) -> None:
        """
        Render a three-dots menu button with given menu items.

        Args:
            items: List of tuples: (label, icon, callback).
                - label: Text shown in the menu.
                - icon: Quasar icon name.
                - callback: A no-arg callable executed on click.
        """

        with ui.button(icon="more_vert").props("flat round dense").classes("text-grey-8"):
            with ui.menu().props("auto-close transition-show=none transition-hide=none").classes("wm-menu"):

                for label, icon, cb in items:
                    with ui.element("q-item").props("clickable v-ripple dense").classes("wm-menu-item").on("click", lambda e, _cb=cb: _cb()):
                        with ui.element("q-item-section").props("avatar"):
                            ui.icon(icon).classes("wm-menu-ic")
                        with ui.element("q-item-section"):
                            ui.label(label).classes("text-body2")

                ui.separator()
                    
    def health_chips(self, health: dict[str, Any]) -> list[tuple[str, str]]:
        """
        Build a list of (label, color) chips for a node health dict.

        Args:
            health: A dictionary with health flags/counters (e.g. missing_quotes, stale_quotes).

        Returns:
            A list of `(label, color)` tuples suitable for rendering UI chips.
        """
        chips: list[tuple[str, str]] = []
        if health.get("missing_quotes", 0):
            chips.append((f'Missing quotes: {health["missing_quotes"]}', "negative"))
        if health.get("stale_quotes"):
            chips.append(("Stale quotes", "warning"))
        if health.get("projection_mismatch"):
            chips.append(("Mismatch", "negative"))
        if health.get("needs_review"):
            chips.append(("Review", "warning"))
        return chips
    
    def _render_health_chips_inline(self, health: dict) -> None:
        """
        Render health chips inline.

        Args:
            health: Health dict passed to `health_chips()`.
        """
        for lbl, col in self.health_chips(health or {}):
            ui.chip(lbl, color=col, text_color="white").props("dense square")

    def _wallet_menu_button(self, w: dict) -> None:
        """
        Render the wallet-level context menu button.

        Args:
            w: Wallet dict (used to pass the selected wallet to rename dialog).
        """
        self._menu_button([
            ("Add account", "add", lambda: self.open_create_account_dialog()),
            ("Rename wallet", "edit", lambda ww=w: self.open_rename_wallet_dialog(ww)),
        ])

    def _render_deposit_nodes(self, w: dict) -> None:
        """
        Render deposit account nodes for a given wallet.

        For each deposit account:
        - converts current and previous snapshot balance into view currency
        - calculates MoM percentage change
        - renders balance + health chips + context menu

        Args:
            w: Wallet dict containing `deposit_accounts`.
        """
        view = self.state["view_ccy"]
        dep = w.get("deposit_accounts", []) or []
        if not dep:
            ui.label("No deposit accounts.").classes("text-body2 text-grey-7 q-ml-sm q-mt-sm")
            return

        for a in dep:
            chips = self.health_chips(a.get("health", {}))
            bal_view = change_currency_to(
                amount=dec(a["available"]),
                view_currency=view,
                transaction_currency=a["ccy"],
                rates=self.currency_rate,
            )
            
            key = month_key()
            prev_key = prev_month_key(key)

            cur_raw = dec(a["available"])
            prev_snap = (a.get("snapshots") or {}).get(prev_key)
            prev_raw = dec(prev_snap["available"]) if prev_snap else None

            cur_view = change_currency_to(
                amount=cur_raw,
                view_currency=view,
                transaction_currency=a["ccy"],
                rates=self.currency_rate,
            )
            if prev_raw:
                prev_view = change_currency_to(
                    amount=prev_raw,
                    view_currency=view,
                    transaction_currency=prev_snap.get("ccy", a["ccy"]),
                    rates=self.currency_rate,
                )
            else:
                prev_view = None
   
            mom = pct_change(cur_view, prev_view)

            with ui.card().classes("wm-inner-card").style("width:100%; padding:10px 12px; margin:10px 0;"):
                with ui.row().classes("w-full items-center").style("justify-content:space-between; gap:12px;"):
                    with ui.column().style("gap:2px;"):
                        ui.label(a["name"]).classes("text-weight-medium")
                        ui.label(f'Tx/month: {a["tx_per_month"]} · Currency: {a["ccy"]}').classes("text-caption text-grey-7")

                    with ui.row().style("align-items:center; gap:8px; flex-wrap:wrap;"):
                        ui.html(f'<div class="wm-pill"><b>Balance</b>: {fmt_money(bal_view, view)}</div>')
                        for lbl, col in chips:
                            ui.chip(lbl, color=col, text_color="white").props("dense square")
                        if mom:
                            ui.chip(
                                f"MoM {fmt_pct(mom)}", 
                                color=("positive" if (mom or 0) >= 0 else "negative"), 
                                text_color="white"
                                ).props("dense square")

                        self._menu_button([
                            ("Add transaction", "add", lambda aa=a: self.open_add_transaction_dialog(aa)),
                            ("Delete account", 
                             "delete", 
                             lambda aa=a: self.open_delete_account_dialog(aa, kind=AccountType.CURRENT.name)
                             ),
                        ])
                        
    def _render_brokerage_nodes(self, w: dict) -> None:
        """
        Render brokerage account nodes for a given wallet.

        For each brokerage account:
        - computes cash/positions totals in view currency
        - computes MoM change based on previous snapshot (if available)
        - renders an expansion section containing:
            - header with totals and health chips
            - cash accounts table (if present)
            - top positions chips (by value)

        Args:
            w: Wallet dict containing `brokerage_accounts`.
        """
        view = self.state["view_ccy"]
        bro = w.get("brokerage_accounts", []) or []
        if not bro:
            ui.label("No brokerage accounts.").classes("text-body2 text-grey-7 q-ml-sm q-mt-sm")
            return

        for b in bro:
            cash_accounts = b.get("cash_accounts") or []
            
            cash_view = change_currency_to(
                amount=dec(b.get("sum_cash_accounts", 0)),
                view_currency=view,
                transaction_currency=b.get("ccy", view),
                rates=self.currency_rate,
            )
            pos_view = change_currency_to(
                amount=dec(b.get("positions_value", 0)),
                view_currency=view,
                transaction_currency=b.get("ccy", view),
                rates=self.currency_rate,
            )

            key = month_key()
            prev_key = prev_month_key(key)
            cur_total = None if (cash_view is None or pos_view is None) else (cash_view + pos_view)

            prev_snap = (b.get("snapshots") or {}).get(prev_key)
            prev_total = None
            if prev_snap:
                src = prev_snap.get("ccy", b.get("ccy", view))
                prev_cash = change_currency_to(dec(prev_snap.get("cash", 0)), view, src, self.currency_rate)
                prev_stk = change_currency_to(dec(prev_snap.get("stocks", 0)), view, src, self.currency_rate)
                if prev_cash is not None and prev_stk is not None:
                    prev_total = prev_cash + prev_stk

            mom = pct_change(cur_total, prev_total)

            with ui.card().classes("wm-inner-card").style("width:100%; padding:10px 12px; margin:10px 0;"):
                acc_exp = self._make_broker_account_expansion(
                    b=b,
                    cash_view=cash_view,
                    pos_view=pos_view,
                    mom=mom,
                    opened=False,
                )
                with acc_exp:
                    with ui.row().classes("w-full items-center").style("justify-content:space-between; gap:12px; padding: 6px 0;"):
                        with ui.row().style("display:flex; gap:10px; align-items:center; flex-wrap:wrap;"):
                            ui.html(f'<div class="wm-pill"><b>Events/month</b>: {int(b.get("events_per_month", 0))}</div>')
                            ui.html(f'<div class="wm-pill"><b>Reporting</b>: {b.get("ccy", "")}</div>')
                            self._render_health_chips_inline(b.get("health", {}))
                            if mom is not None:
                                ui.chip(
                                    f"MoM {fmt_pct(mom)}",
                                    color=("positive" if (mom or 0) >= 0 else "negative"),
                                    text_color="white",
                                ).props("dense square")

                        self._menu_button([
                            ("Add event", "add", lambda bb=b: self.open_add_event_dialog(bb)),
                            ("Delete brokerage account",
                             "delete", 
                             lambda bb=b: self.open_delete_account_dialog(bb, kind=AccountType.BROKERAGE.name),
                             )
                        ])

                    with ui.card().classes("wm-subexp-card").style("width:100%; padding:10px 12px; margin-top:6px;"):
                        ui.label("Cash accounts").classes("text-caption text-grey-7 q-mb-sm")

                        if not cash_accounts:
                            ui.label("No linked cash accounts.").classes("text-body2 text-grey-7")
                        else:
                            rows = [
                                {"name": ca.get("name", "—"), "ccy": ca.get("ccy", "—"), "available": ca.get("available", 0)}
                                for ca in cash_accounts
                            ]
                            cols = [
                                {"name": "name", "label": "Account", "field": "name", "align": "left"},
                                {"name": "ccy", "label": "CCY", "field": "ccy", "align": "left"},
                                {"name": "available", "label": "Available", "field": "available", "align": "right"},
                            ]
                            tbl = ui.table(columns=cols, rows=rows, row_key="name").classes("w-full")
                            tbl.props("dense flat bordered hide-bottom")

                            tbl.add_slot("body-cell-available", r"""
                            <q-td :props="props" class="num">
                            <span>
                                {{ Number(props.row.available).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}
                                {{ ' ' + props.row.ccy }}
                            </span>
                            </q-td>
                            """)

                        ui.html(f'<div class="wm-pill q-mt-sm"><b>Total cash</b>: {fmt_money(cash_view, view)}</div>')

                    ui.label("Top positions (by value)").classes("text-caption text-grey-7 q-mt-md q-mb-xs")
                    positions = b.get("positions", []) or []
                    if not positions:
                        ui.label("No positions.").classes("text-body2 text-grey-7")
                    else:
                        with ui.row().style("gap:8px; flex-wrap:wrap;"):
                            for p in positions[:8]:
                                pnl = dec(p.get("pnl_pct", 0))
                                col = "positive" if pnl >= 0 else "negative"
                                ui.chip(f'{p.get("symbol", "?")} · {fmt_pct(pnl)}', 
                                        color=col, text_color="white").props("dense square")
                                
    def _broker_mic_allocation(self, w: dict, view: str) -> list[tuple[str, Decimal]]:
        """
        Render brokerage account nodes for a given wallet.

        For each brokerage account:
        - computes cash/positions totals in view currency
        - computes MoM change based on previous snapshot (if available)
        - renders an expansion section containing:
            - header with totals and health chips
            - cash accounts table (if present)
            - top positions chips (by value)

        Args:
            w: Wallet dict containing `brokerage_accounts`.
        """
        sums: dict[str, Decimal] = {}
        total = Decimal("0")

        for b in (w.get("brokerage_accounts") or []):
            for p in (b.get("positions") or []):
                mic = p.get("mic") or "—"
                v = change_currency_to(
                    amount=dec(p.get("value", 0)),
                    view_currency=view,
                    transaction_currency=p.get("currency", 0),
                    rates=self.currency_rate,
                )
                if v is None:
                    continue
                sums[mic] = sums.get(mic, Decimal("0")) + v
                total += v

        if total <= 0:
            return []

        out = []
        for mic, v in sorted(sums.items(), key=lambda kv: kv[1], reverse=True):
            out.append((mic, (v / total)))
        return out

    def _metals_header(self, w: dict, view: str, cur, prev) -> str:
        """
        Compute header values for the Metals group.

        Args:
            w: Wallet dict (kept for symmetry/future use).
            view: View currency code (kept for symmetry/future use).
            cur: Current metals total in view currency (or None).
            prev: Previous snapshot breakdown in view currency (or None).

        Returns:
            Tuple: (current_value, mom_change)
        """
        prev_val = prev["metals"] if prev else None
        mom = pct_change(cur, prev_val)
        return cur, mom

    def _real_estate_header(self, w: dict, view: str, cur, prev) -> str:
        """
        Compute header values for the Real estate group.

        Args:
            w: Wallet dict (kept for symmetry/future use).
            view: View currency code (kept for symmetry/future use).
            cur: Current real estate total in view currency (or None).
            prev: Previous snapshot breakdown in view currency (or None).

        Returns:
            Tuple: (current_value, mom_change)
        """
        prev_val = prev["real_estate"] if prev else None
        mom = pct_change(cur, prev_val)
        return cur, mom
    
    def _adapter_for_metal_dialog(self, ww: dict):
        """
        Build a lightweight adapter object for the metal buy dialog.

        The dialog expects:
        - selected_wallet: list with an object having `id`, `name`, and `accounts` (with `account_type`)
        - view_currency: object with `.value`
        - wallet_client, get_user_id for service calls

        Args:
            ww: Wallet dict.

        Returns:
            A SimpleNamespace compatible with the metal dialog expectations.
        """
        view_ccy = (self.state.get("view_ccy") or "PLN")

        accounts_src = ww.get("accounts") or ww.get("deposit_accounts") or []
        acc_objs = []
        for a in accounts_src:
            at = a.get("account_type") or a.get("type") or "CURRENT"
            acc_objs.append(SimpleNamespace(account_type=at))

        if not acc_objs:
            acc_objs = [SimpleNamespace(account_type="CURRENT")]

        w_obj = SimpleNamespace(
            id=uuid.UUID(str(ww["id"])),
            name=ww.get("name", str(ww["id"])),
            accounts=acc_objs,
        )

        return SimpleNamespace(
            selected_wallet=[w_obj],
            view_currency=SimpleNamespace(value=view_ccy),
            wallet_client=self.wallet_client,
            get_user_id=self.get_user_id,
        )
        
    def _adapter_for_property(self, ww: dict):
        """
        Build a lightweight adapter object for the property dialog.

        The dialog expects:
        - wallets: list with an object having `id`, `name`, and `accounts` (with `account_type`)
        - wallet_client, get_user_id for service calls

        Args:
            ww: Wallet dict.

        Returns:
            A SimpleNamespace compatible with the property dialog expectations.
        """
        accounts_src = ww.get("accounts") or ww.get("deposit_accounts") or []
        acc_objs = [SimpleNamespace(account_type=a.get("account_type") or a.get("type") or "CURRENT") for a in accounts_src]
        if not acc_objs:
            acc_objs = [SimpleNamespace(account_type="CURRENT")]

        w_obj = SimpleNamespace(
            id=uuid.UUID(str(ww["id"])),
            name=ww.get("name", str(ww["id"])),
            accounts=acc_objs,
        )

        return SimpleNamespace(
            wallets=[w_obj],              
            wallet_client=self.wallet_client, 
            get_user_id=self.get_user_id,   
        )

    def _render_metals_node(self, w: dict) -> None:
        """
        Render the Metals node for a wallet (summary + holdings table).

        Args:
            w: Wallet dict containing a `metals` section.
        """
        view = self.state["view_ccy"]
        metals = w.get("metals", {}) or {}
        cnt = int(metals.get("count", 0))

        total_view = change_currency_to(
            amount=dec(metals.get("value", 0)),
            view_currency=view,
            transaction_currency=metals.get("ccy", view),
            rates=self.currency_rate,
        )

        items = metals.get("items", []) or []

        rows = []
        for it in items:
            name = it.get("name") or it.get("metal") or it.get("type") or "—"
            qty = dec(it.get("quantity", 0))
            unit = it.get("qty_unit") or "g"
            val = dec(it.get("value", 0))
            src_ccy = it.get("ccy") or metals.get("ccy", view)

            val_view = change_currency_to(
                amount=val,
                view_currency=view,
                transaction_currency=src_ccy,
                rates=self.currency_rate,
            )

            rows.append({
                "id": it.get("id") or f"{name}-{len(rows)}",
                "name": name,
                "qty": qty,
                "unit": unit,
                "value_src": val,
                "ccy_src": src_ccy,
                "value_view": val_view,
            })

        with ui.card().classes("wm-inner-card").style("width:100%; padding:10px 12px; margin:10px 0;"):
            with ui.row().classes("w-full items-center").style("justify-content:space-between; gap:12px;"):
                with ui.row().style("gap:10px; flex-wrap:wrap; align-items:center;"):
                    ui.html(f'<div class="wm-pill"><b>Count</b>: {cnt}</div>')
                    ui.html(f'<div class="wm-pill"><b>Total</b>: {fmt_money(total_view, view)}</div>')
                    self._render_health_chips_inline(metals.get("health", {}))

                self._menu_button([
                    ("Add metal buy", "add", lambda ww=w: self.open_add_metal_buy_dialog(ww)),
                ])

            ui.label("Holdings").classes("text-caption text-grey-7 q-mt-sm q-mb-xs")

            if not rows:
                ui.label("No metal holdings.").classes("text-body2 text-grey-7")
                return

            cols = [
                {"name": "name", "label": "Metal", "field": "name", "align": "left", "sortable": True},
                {"name": "qty", "label": "Qty", "field": "qty", "align": "right", "sortable": True},
                {"name": "value_view", "label": f"Value ({view})", "field": "value_view", "align": "right", "sortable": True},
            ]

            tbl = ui.table(columns=cols, rows=rows, row_key="id").classes("w-full")
            tbl.props("dense flat bordered hide-bottom")

            tbl.add_slot("body-cell-qty", r"""
            <q-td :props="props" class="num">
            <span>
                {{ Number(props.row.qty).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}
                {{ ' ' + props.row.unit }}
            </span>
            </q-td>
            """)

            tbl.add_slot("body-cell-value_view", r"""
            <q-td :props="props" class="num">
            <span>
                {{
                (props.row.value_view != null)
                    ? Number(props.row.value_view).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) 
                    : Number(props.row.value_src).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) 
                }}
            </span>
            </q-td>
            """)

    def _render_real_estate_node(self, w: dict) -> None:
        """
        Render the Metals node for a wallet (summary + holdings table).

        Args:
            w: Wallet dict containing a `metals` section.
        """
        view = self.state["view_ccy"]
        re = w.get("real_estate", {}) or {}
        cnt = int(re.get("count", 0))

        total_view = change_currency_to(
            amount=dec(re.get("value", 0)),
            view_currency=view,
            transaction_currency=re.get("ccy", view),
            rates=self.currency_rate,
        )

        items = re.get("items", []) or []

        rows = []
        for it in items:
            name = it.get("name") or it.get("type") or "—"
            city = it.get("city") or "—"
            val = dec(it.get("value", 0))
            src_ccy = it.get("ccy") or re.get("ccy", view)

            val_view = change_currency_to(
                amount=val,
                view_currency=view,
                transaction_currency=src_ccy,
                rates=self.currency_rate,
            )

            rows.append({
                "id": it.get("id") or f"{name}-{city}-{len(rows)}",
                "name": name,
                "city": city,
                "value_src": val,
                "ccy_src": src_ccy,
                "value_view": val_view,
            })

        with ui.card().classes("wm-inner-card").style("width:100%; padding:10px 12px; margin:10px 0;"):
            with ui.row().classes("w-full items-center").style("justify-content:space-between; gap:12px;"):
                with ui.row().style("gap:10px; flex-wrap:wrap; align-items:center;"):
                    ui.html(f'<div class="wm-pill"><b>Count</b>: {cnt}</div>')
                    ui.html(f'<div class="wm-pill"><b>Total</b>: {fmt_money(total_view, view)}</div>')
                    self._render_health_chips_inline(re.get("health", {}))

                self._menu_button([
                    ("Add property", "add", lambda ww=w: self.open_add_property_dialog(ww)),
                ])

            ui.label("Properties").classes("text-caption text-grey-7 q-mt-sm q-mb-xs")

            if not rows:
                ui.label("No properties.").classes("text-body2 text-grey-7")
                return

            cols = [
                {"name": "name", "label": "Name", "field": "name", "align": "left", "sortable": True},
                {"name": "city", "label": "City", "field": "city", "align": "left", "sortable": True},
                {"name": "value_view", "label": f"Value ({view})", "field": "value_view", "align": "right", "sortable": True},
            ]

            tbl = ui.table(columns=cols, rows=rows, row_key="id").classes("w-full")
            tbl.props("dense flat bordered hide-bottom")

            tbl.add_slot("body-cell-value_view", r"""
            <q-td :props="props" class="num">
            <span>
                {{
                (props.row.value_view != null)
                    ? Number(props.row.value_view).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) 
                    : Number(props.row.value_src).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) 
                }}
            </span>
            </q-td>
            """)

    def _snapshot_for_month(self, w: dict, month_key: str) -> Optional[dict]:
        """
        Get a wallet snapshot dict for a given month key.

        Args:
            w: Wallet dict containing `snapshots`.
            month_key: Month key in format "YYYY-MM".

        Returns:
            Snapshot dict if present, otherwise None.
        """
        snaps = w.get("snapshots") or {}
        return snaps.get(month_key) 
                       
    def _snapshot_breakdown_in_view(self, w: dict, month_key: str, view_ccy: str) -> Optional[dict[str, Optional[Decimal]]]:
        """
        Convert snapshot fields into view currency and compute totals.

        Args:
            w: Wallet dict containing snapshots.
            month_key: Month key to pick from `w["snapshots"]`.
            view_ccy: Target currency to convert into.

        Returns:
            Breakdown dict with:
                cash_deposit, cash_broker, stocks, metals, real_estate, cash_total, total
            Returns None if snapshot is missing or any conversion failed.
        """
        s = self._snapshot_for_month(w, month_key)
        if not s:
            return None
        src = s.get("ccy", view_ccy)

        def cv(field: str) -> Optional[Decimal]:
            v = change_currency_to(
                    amount=dec(s.get(field, 0)),
                    view_currency=view_ccy,
                    transaction_currency=src,
                    rates=self.currency_rate,
                )
            return v

        cash_deposit = cv("cash_deposit")
        cash_broker = cv("cash_broker")
        stocks = cv("stocks")
        metals = cv("metals")
        real_estate = cv("real_estate")

        if None in (cash_deposit, cash_broker, stocks, metals, real_estate):
            return None

        cash_total = cash_deposit + cash_broker
        total = cash_total + stocks + metals + real_estate
        return {
            "cash_deposit": cash_deposit,
            "cash_broker": cash_broker,
            "stocks": stocks,
            "metals": metals,
            "real_estate": real_estate,
            "cash_total": cash_total,
            "total": total,
        }
                
    async def create_monthly_snapshot(self) -> None:
        """
        Create a monthly snapshot in wallet-service and refresh the tree.
        """
        logger.info("Request: WalletManager.create_monthly_snapshot")
        
        res = await self.wallet_client.create_monthly_snapshot(
            user_id=self.user_id,
            currency_rate=self.currency_rate,
            month_key=month_key(),
        )
        if not res or not res.ok:
            ui.notify("Snapshot failed", type="negative")
            return

        ui.notify(f"Snapshot saved for {res.month_key}", type="positive")

        data = await self.wallet_client.get_wallet_manager_tree(user_id=self.user_id, currency_rate=self.currency_rate, months=2)
        if data:
            self.demo = data
        self._render_tree()  

    def _wallet_breakdown(self, w: dict, target_ccy: str) -> dict[str, Optional[Decimal]]:
        """
        Compute wallet breakdown in `target_ccy`.

        Breakdown fields:
            cash_deposit, cash_broker, stocks, metals, real_estate, cash_total, total

        Args:
            w: Wallet dict containing deposit accounts, brokerage accounts, metals, and real estate summaries.
            target_ccy: Currency code to convert values into (e.g. "PLN", "EUR").

        Returns:
            A dict of breakdown values in `target_ccy`.
            If any required conversion fails, returns all fields as None.
        """
        cash_deposit = Decimal("0")
        cash_broker = Decimal("0")
        stocks = Decimal("0")
        metals = Decimal("0")
        real_estate = Decimal("0")
        ok = True

        for a in (w.get("deposit_accounts") or []):
            v = change_currency_to(
                    amount=dec(a["available"]),
                    view_currency=target_ccy,
                    transaction_currency=a["ccy"],
                    rates=self.currency_rate,
                )
            if v is None:
                ok = False
            else:
                cash_deposit += v

        for b in (w.get("brokerage_accounts") or []):
            cash_default = dec(b.get("sum_cash_accounts", 0))
            pos_default = dec(b.get("positions_value", 0))
            src = b.get("ccy", target_ccy)
            cv = change_currency_to(
                amount=dec(cash_default),
                view_currency=target_ccy,
                transaction_currency=src,
                rates=self.currency_rate,
            )
            pv = change_currency_to(
                amount=dec(pos_default),
                view_currency=target_ccy,
                transaction_currency=src,
                rates=self.currency_rate,
            )
            if cv is None or pv is None:
                ok = False
            else:
                cash_broker += cv
                stocks += pv

        m = w.get("metals") or {}
        r = w.get("real_estate") or {}
        
        mv = change_currency_to(
                amount=dec(m.get("value", 0)),
                view_currency=target_ccy,
                transaction_currency=m.get("ccy", target_ccy),
                rates=self.currency_rate,
            )
        
        rv = change_currency_to(
                amount=dec(r.get("value", 0)),
                view_currency=target_ccy,
                transaction_currency=r.get("ccy", target_ccy),
                rates=self.currency_rate,
            )

        if mv is None or rv is None:
            ok = False
        else:
            metals += mv
            real_estate += rv

        if not ok:
            return {
                "cash_deposit": None, "cash_broker": None, "stocks": None, "metals": None, "real_estate": None,
                "cash_total": None, "total": None,
            }

        cash_total = cash_deposit + cash_broker
        total = cash_total + stocks + metals + real_estate
        return {
            "cash_deposit": cash_deposit,
            "cash_broker": cash_broker,
            "stocks": stocks,
            "metals": metals,
            "real_estate": real_estate,
            "cash_total": cash_total,
            "total": total,
        }
        
    def _render_market_allocation_mic_footer(self, alloc: list[tuple[str, Decimal]]) -> None:
        """
        Render a MIC allocation footer bar (stacked segments) and legend chips.

        Args:
            alloc: List of (mic, value) pairs in view currency. Values do not need to be normalized.
        """
        if not alloc:
            return

        total = sum((f for _, f in alloc), Decimal("0"))
        if total <= 0:
            return
        alloc_norm = [(mic, f / total) for mic, f in alloc]

        alloc_sorted = sorted(alloc_norm, key=lambda x: x[1], reverse=True)
        top_n = 6
        top = alloc_sorted[:top_n]
        other = sum((f for _, f in alloc_sorted[top_n:]), Decimal("0"))

        palette = ["primary", "info", "teal", "indigo", "purple", "cyan", "deep-orange", "blue-grey"]
        segments: list[tuple[str, Decimal, str]] = [
            (mic, frac, palette[i % len(palette)]) for i, (mic, frac) in enumerate(top)
        ]
        if other > Decimal("0.005"):
            segments.append(("Other", other, "grey-6"))

        with ui.card().classes("w-full q-mt-md").style(
            """
            border-radius: 16px;
            border: 1px solid rgba(2,6,23,.06);
            box-shadow: none;
            padding: 14px 14px 12px;
            background: #ffffff;
            """
        ):
            ui.label("Market allocation (MIC)").classes("text-caption text-grey-7")

            bar = ui.element("div").classes("w-full").style(
                """
                margin-top:10px;
                height:16px;
                border-radius:999px;
                overflow:hidden;
                display:flex;
                background: rgba(15,23,42,.08);
                border: 1px solid rgba(15,23,42,.10);
                """
            )

            with bar:
                for mic, frac, color in segments:
                    pct = float(frac * Decimal("100"))
                    if pct <= 0:
                        continue

                    seg = ui.element("div").classes(f"bg-{color}").style(
                        f"flex: 0 0 {pct}%; max-width:{pct}%; height:100%;"
                    )
                    with seg:
                        ui.tooltip(mic)

            with ui.row().classes("items-center q-gutter-xs q-mt-sm").style("flex-wrap:wrap;"):
                for mic, frac, color in segments:
                    ui.chip(f"{mic} · {fmt_pct(frac)}", color=color, text_color="white").props("dense square")
                    
    async def _after(self):
        """
        Post-action hook: refresh data from services and rerender the wallet manager tree.
        """
        logger.info("Request: WalletManager._after")
        await self.fetch_data()
        self._render_tree()


@ui.page("/wallet-manager")
def wallet_manager_demo_page() -> None:
    add_style()
    add_user_style()
    WalletManager()
