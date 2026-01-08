from nicegui import ui
from fastapi import Request
from typing import List, Dict, Any, Iterable, Iterator, Tuple
from collections import defaultdict
from decimal import Decimal
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
import logging

from components.navbar_footer import footer
from components.panel.card import panel 
from static.style import add_style, add_user_style
from components.alerts import ALERTS, alerts_panel_card
from components.transaction import (
    transactions_table_card, cash_transactions_table_card, 
    render_create_transaction_dialog, render_lack_transactions
    )
from components.investments import show_investments_dialog, render_empty_assets_placeholder
from components.debts import show_debts_dialog
from components.cards import (
    render_top5_table_observer, render_top5_table, pie_card,
    line_card, kpi_card, bar_card, goals_bullet_card, 
    )
from components.expenses import recurring_expenses_panel_card
from components.notes import build_notes_dialog
from components.year_goal import show_goals_dialog
from utils.utils import export_csv, ccy_to_str
from utils.money import (
    cash_total_in_pln, cash_total_in_eur, cash_total_in_usd, cash_kpi_label, 
    change_currency_to, format_pl_amount, allocation_series_from_totals, dec,
    series_from_amounts
    )
from utils.dates import month_floor
from demo.factories import create_demo_wallet_payload
from clients.wallet_client import WalletClient
from clients.stock_client import StockClient
from clients.nbp_client import NBPClient
from schemas.wallet import ClientWalletSyncResponse, Currency, WalletListItem, YearGoalOut
from components.context.nav_context import NavContextBase
from services.current_user import get_current_user_or_create
from storage.session_state import set_wallets_from_payload, set_current_user_id, set_banks

logger = logging.getLogger(__name__)


class Wallet(NavContextBase):
    def __init__(self, request):
        """
        Initialize Wallet context with request, clients
        """
        
        self.request = request
        self.wallet_client = WalletClient()
        self.stock_client = StockClient()
        self.nbp_client = NBPClient()
        
        self.wallets = []          
        self.selected_wallet = [] 
        self.banks = []  

        ui.timer(0.01, self._init_async, once=True)
        
    async def _init_async(self):
        """
        Asynchronous initialization: 
        - Retrieves user and wallet data.
        - Sets up the navigation and UI.
        - Handles onboarding if no wallet/account is found.
        """
        logger.info("Running async wallet setup...")

        user = await get_current_user_or_create(self.request)
        if not user:
            logger.info("user do no exist")
            return

        data = await self.wallet_client.sync_user(user.model_dump(exclude_none=True))
        if not data:
            ui.notify('The user data is invalid. Please contact the administrator', color='negative')
            return
        
        logger.info("Wallet client returned user data successfully.")
        
        self.username = data.first_name
        self.user_id = data.user_id
        self.wallets: List[WalletListItem] = data.wallets
        self.selected_wallet = self.wallets
        self.banks = data.banks
        
        if getattr(data, "assets_8m_total", None):
            self.months = data.assets_8m_total.months
            self.revenue = data.assets_8m_total.values
        else:
            self.months, self.revenue = [], []

        if getattr(data, "cpi_8m", None):
            self.cpi_idx = data.cpi_8m.index_by_month
        else:
            self.cpi_idx = None
        
        set_wallets_from_payload(self.wallets)
        set_current_user_id(self.user_id)
        set_banks(self.banks)

        self.render_navbar()
        
        self.currency_rate = await self.nbp_client.get_usd_eur_pln()

        if not self.wallets:
            logger.warning("No wallets found. Rendering wallet onboarding.")
            self.render_no_wallet_onboarding(self.username)
        elif not [acc for w in self.selected_wallet for acc in w.accounts]:
            logger.warning("No accounts found. Rendering account onboarding.")
            self.render_no_accounts_onboarding(self.username)
        else:
            logger.info("Rendering dashboard.")
            self.build_header()
            self.build_body()
        footer()
        
    def create_demo_data(self) -> ClientWalletSyncResponse:
        """
        Generates a demo wallet payload for showcasing the dashboard.
        """
        logger.info("Creating demo wallet data.")
        
        self.data = create_demo_wallet_payload(first_name="Artur")
        
    def on_wallet_change(self) -> None:
        """
        Callback for wallet selection change. Updates the selected wallet
        and rebuilds the dashboard body.
        """
        selected_wallet = self.view_wallet.value or "Wszystkie"
        if selected_wallet == "Wszystkie":
            self.selected_wallet = self.wallets
        else:
            self.selected_wallet = [wallet for wallet in self.wallets if wallet.name == selected_wallet]
        self.build_body()
        
    def capture_cash_label(self):
        """
        Computes the current cash KPI label based on selected currency.

        :return: Formatted cash KPI label string.
        """
        cur = self.view_currency.value or 'PLN'
        if cur == Currency.PLN.value:
            total = cash_total_in_pln(self.wallets, self.currency_rate)
        elif cur == Currency.EUR.value:
            total = cash_total_in_eur(self.wallets, self.currency_rate)
        else:
            total = cash_total_in_usd(self.wallets, self.currency_rate)
            
        return total, cash_kpi_label(total, cur, decimals=0)

    def on_currency_change(self):
        """
        Callback triggered when the selected currency changes.
        Updates the displayed cash KPI label accordingly.
        """
        logger.info(f"Currency changed to: {self.view_currency.value}")
        self.build_body()

    def build_header(self):
        """
        Builds the top navigation card containing filters (wallet, currency, date range),
        actions (Add Transaction, Export, Notes), and control buttons.
        """
        logger.info("Building dashboard header...")
        with ui.card().classes('elevated-card q-pa-sm q-mb-md').style('width:min(1600px,98vw); margin:0 auto 12px;'):
            with ui.row().style(
                    'display:flex;'
                    'justify-content:space-between;'
                    'align-items:center;'
                    'flex-wrap:wrap;'
                    'gap:10px; width:100%;'):
                with ui.row().style('display:flex; align-items:center; flex-wrap:wrap; gap:10px;'):
                    ui.select(['Ostatni miesiąc', 'Ostatnie 3 mies.', 'Ostatni rok', 'Całość'],
                              value='Ostatni rok').props('label=Zakres dense outlined').style('flex:0 0 auto;')
                    ui.select(['Miesięczny', 'Tygodniowy'], value='Miesięczny'
                              ).props('label=Interwał dense outlined').style('flex:0 0 auto;')
                    names = ["Wszystkie"] + [w.name for w in self.wallets]
                    self.view_wallet = ui.select(names, value='Wszystkie'
                                                 ).props('label=Portfel dense outlined').style('flex:0 0 auto;')
                    
                    self.view_wallet.on_value_change(self.on_wallet_change)
                    
                    self.view_currency = ui.select([c.value for c in Currency], value='PLN'
                                                   ).props('label=Waluta dense outlined').style('flex:0 0 auto;')
                    self.view_currency.on_value_change(self.on_currency_change)
                    
                    open_add_transaction = render_create_transaction_dialog(self)

                    ui.button('Add Transaction', icon='add'
                              ).props('outline no-caps padding="xs lg"').style('flex:0 0 auto;').on_click(open_add_transaction)
                    ui.button('Raporty', icon='summarize'
                              ).props('color=primary unelevated no-caps padding="xs lg"').style('flex:0 0 auto;')

                with ui.row().style('display:flex; align-items:center; flex-wrap:wrap; gap:10px;'):
                    with ui.button('Eksport').props('outline no-caps padding="xs lg" icon=ios_share').style('flex:0 0 auto;'):
                        with ui.menu():
                            ui.menu_item('Eksport CSV', on_click=lambda: ui.download(export_csv(), filename='export.csv'))
                            ui.menu_item('Eksport PDF (drukuj)', on_click=lambda: ui.run_javascript('window.print()'))

                    open_notes = build_notes_dialog(self)
                    ui.button('Notatki', icon='edit_note'
                              ).props('color=primary unelevated no-caps padding="xs lg"'
                                      ).on_click(open_notes).style('flex:0 0 auto;')
                
    def build_body(self, demo: bool = False):
        """
        Builds the main body of the dashboard: KPIs, charts, and tables.

        Args:
            demo: If True, demo data is loaded instead of user data.
        """
        logger.info("Building dashboard body...")
        
        if demo:
            logger.info("Demo mode active. Creating demo data.")
            self.create_demo_data()

        if not hasattr(self, 'root') or self.root is None:
            self.root = ui.element('div').classes('dashboard-root').style('width:min(1500px,94vw); margin:0 auto;')
        else:
            self.root.clear() 
               
        with self.root:
            with ui.grid(columns=6).classes('gap-4'):
                cash_total, self.cash = self.capture_cash_label()
                investment_total, self.invest_label = self.capture_investments_label()
                debt_total, self.debt_label = self.capture_debts_label()
                
                kpi_card('Wartość netto', 
                         self.capture_netto_label(cash_total, investment_total, debt_total), 
                         '+2.4% m/m · +8.1% YTD'
                         )
                kpi_card('Gotówka', self.cash, '25% portfela and 5% free')
                kpi_card('Inwestycje', 
                         self.invest_label, 
                         'P/L YTD +8.1%', 
                         on_click=lambda: show_investments_dialog(self)
                         )
                kpi_card('Zobowiązania', 
                         self.debt_label, 
                         self.capture_debts_sub(), 
                         on_click=lambda: show_debts_dialog(self)
                         )
                kpi_card('Wydatki (mies.)', '7 890 PLN', 'Budżet 85%')
                self.capital_label = self.compute_capital_gains_ytd_label()
                kpi_card('Zyski Kapitałowe (mies.)', self.capital_label, '+2.1% YTD')
    
            ui.space().style('height:20px')
            
            with ui.grid(columns=4).classes('gap-3 w-full items-stretch q-mb-sm'):
                gainers_rows, losers_rows = self.get_top_tables_for_selected_wallets()
                
                with panel('Top Gaining Stocks'):
                    if gainers_rows:
                        render_top5_table(gainers_rows, tone='positive', currency=self.view_currency.value) 
                    else:
                        render_lack_transactions()

                with panel('Top Losing Stocks'):
                    if losers_rows:
                        render_top5_table(losers_rows, tone='negative', reverse=False, currency=self.view_currency.value) 
                    else:
                        render_lack_transactions()
                        
                with panel('Obserwed Stocks'):
                    render_top5_table_observer([
                        {'sym': 'PZU', 'pl_pct': 22, 'pl_abs': 19},
                        {'sym': 'ABC', 'pl_pct': 50, 'pl_abs': 38},
                        {'sym': 'UBER', 'pl_pct': 60, 'pl_abs': 22},
                        {'sym': 'GOOGL', 'pl_pct': 24, 'pl_abs': 55},
                        {'sym': 'META', 'pl_pct': 30, 'pl_abs': 80},
                    ], tone='negative') 

                alerts_panel_card(ALERTS, top=5)

            with ui.grid(columns=3).classes('gap-3 w-full items-stretch'):
                totals = self.compute_assets_by_currency()
                series = allocation_series_from_totals(totals)

                if not series:
                    render_empty_assets_placeholder("Brak aktywów do pokazania alokacji walutowej.")
                else:
                    pie_card("Portfolio Allocation", series)
                    
                totals = self.compute_capital_gains_totals_in_view_ccy()
                series = series_from_amounts(totals, as_percent=True) 
                pie_card('Capital Gains', series)

                data = self.compute_goals_ytd_inputs()

                goals_bullet_card(
                    "Cele YTD",
                    rev_target_year=data["rev_target_year"],
                    exp_budget_year=data["exp_budget_year"],
                    rev_actual_ytd=data["rev_actual_ytd"],
                    exp_actual_ytd=data["exp_actual_ytd"],
                    month_index=data["month_index"],
                    unit=data["unit"],
                    on_click=lambda: show_goals_dialog(self)
                )

                cash_transactions_table_card(self.selected_wallet, 
                                             top=5, 
                                             currency=self.view_currency.value, 
                                             rates=self.currency_rate)
                
                tx = self.build_brokerage_tx_rows_for_selected_wallet()
                if tx:
                    transactions_table_card(tx, top=5, sort_by='date', reverse=True)
                else:
                    with panel() as card:
                        card.classes('w-full max-w-none cursor-pointer p-0').style('width:100%')
                        (ui.label('Ostatnie transakcje maklerskie')
                         .classes('text-sm font-semibold')
                         .style('padding:6px 12px 2px 12px'))
                        render_lack_transactions()

                recurring_expenses_panel_card(self, top=5)

            ui.space().style('height:15px')
            
            with ui.grid(columns=2).classes('gap-3 w-full items-stretch'):    
                line_card(
                    'Aktywa: nominalnie vs realnie',
                    x=self.months, y=self.revenue,
                    cpi=self.cpi_idx, base='first',                 
                    y_suffix=' PLN'
                )    
                self.months, self.inc, self.exp, self.capi = self.compute_dash_flow_series_last_8m()
                
                bar_card('Dash Flow', x=self.months, inc=self.inc, exp=self.exp, cap=self.capi,
                         show_profit=True, show_capital=True, profit_includes_capital=True)

            ui.space().style('height:20px')
   
    def render_no_wallet_onboarding(self, display_name: str) -> None:
        """
        Renders a welcome onboarding screen when the user has no wallets.
        
        Includes an informational message, demo mode entry, and a CTA button to create a new wallet.
        
        Args:
            display_name: The name of the user to personalize the message.
        """
        logger.info("Rendering 'no wallet' onboarding screen.")
 
        if not hasattr(self, 'page_slot') or self.page_slot is None:
            self.page_slot = ui.element('div').style('width:100%; margin:0; padding:0; display:block;')
        else:
            self.page_slot.clear()

        with self.page_slot:
            with ui.card().classes('q-mt-xl shadow-2')\
                .style(
                    'max-width:680px; margin:40px auto; border-radius:24px;'
                    'background:linear-gradient(180deg,#ffffff 0%, #f6f9ff 100%);'
                    'box-shadow:0 10px 24px rgba(15,23,42,.06);'
                    'border:1px solid rgba(2,6,23,.06);'
                    'position:relative;'  
                    ):

                with ui.element('div').classes('q-pa-xl').style('text-align:center; padding-bottom:24px;'):
                    with ui.element('div').style(
                        'width:108px; height:108px; margin:25px auto 20px auto; border-radius:9999px;'
                        'display:flex; align-items:center; justify-content:center;'
                        'background:radial-gradient(60% 60% at 50% 50%, rgba(59,130,246,.18), rgba(59,130,246,.06));'
                        'box-shadow:inset 0 0 0 1px rgba(59,130,246,.25);'
                    ):
                        ui.icon('account_balance_wallet').classes('text-primary').style('font-size:56px;')

                    ui.label(f'Cześć, {display_name}!').classes('text-h5 text-weight-medium')
                    ui.label('Nie masz jeszcze portfela. Kliknij, aby go utworzyć – to zajmie mniej niż minutę.')\
                        .classes('text-body2 text-grey-7 q-mt-xs')

                ui.separator().style('margin: 185px auto 15px auto; width: calc(100% - 80px);')

                with ui.row().classes('items-center q-gutter-xs q-mb-md').style('padding:0 40px 0 40px;'):
                    ui.icon('visibility').classes('text-primary').style('font-size:18px;')
                    demo_link = ui.link('Show demo', '#').classes('text-primary')
                    demo_link.style('font-weight:500; text-decoration:none;')

                ui.html(
                    '<div style="padding:0 40px 35px 40px;">'
                    '<small class="text-grey-7">Dane demo możesz usunąć później w ustawieniach portfela.</small>'
                    '</div>'
                )

                create_btn = ui.button('Utwórz portfel', icon='add')\
                    .props('color=primary unelevated size=lg no-caps')\
                    .classes('text-weight-medium')\
                    .style(
                        'position:absolute; left:50%; bottom:125px; transform:translateX(-50%);'
                        'min-width:288px; padding:16px 38px; border-radius:9999px;'
                        'font-size:16px; letter-spacing:.2px;'
                        'box-shadow:0 16px 34px rgba(59,130,246,.28), 0 6px 12px rgba(59,130,246,.18);'
                        'transition:transform .15s ease, box-shadow .15s ease;'
                    )

                def lift(_=None):
                    create_btn.style(
                        'position:absolute; left:50%; bottom:125px; transform:translateX(-50%) translateY(-2px);'
                        'min-width:288px; padding:16px 38px; border-radius:9999px;'
                        'font-size:16px; letter-spacing:.2px;'
                        'box-shadow:0 22px 44px rgba(59,130,246,.34), 0 10px 18px rgba(59,130,246,.22);'
                        'transition:transform .15s ease, box-shadow .15s ease;'
                    )
                    
                def drop(_=None):
                    create_btn.style(
                        'position:absolute; left:50%; bottom:125px; transform:translateX(-50%);'
                        'min-width:288px; padding:16px 38px; border-radius:9999px;'
                        'font-size:16px; letter-spacing:.2px;'
                        'box-shadow:0 16px 34px rgba(59,130,246,.28), 0 6px 12px rgba(59,130,246,.18);'
                        'transition:transform .15s ease, box-shadow .15s ease;'
                    )
                create_btn.on('mouseenter', lift)
                create_btn.on('mouseleave', drop)
                
        def use_demo():
            logger.info("Switching to demo mode")
            self.page_slot.clear()
            with self.page_slot:
                self.build_header()
                self.build_body(demo=True) 

        create_btn.on_click(lambda: self.open_create_wallet_dialog())
        demo_link.on('click', lambda e: use_demo())
        
    def render_no_accounts_onboarding(self, display_name: str):
        """
        Renders onboarding screen when a wallet exists, but has no accounts.

        Encourages the user to add their first account (e.g., bank, cash, investment).
        
        Args:
            display_name: User's display name to personalize message.
        """
        logger.info("Rendering 'no accounts' onboarding screen.")

        if not hasattr(self, 'page_slot') or self.page_slot is None:
            self.page_slot = ui.element('div').style('width:100%; margin:0; padding:0; display:block;')
        else:
            self.page_slot.clear()

        with self.page_slot:
            with ui.card().classes('q-mt-xl shadow-2').style(
                'max-width:860px; margin:40px auto; border-radius:24px;'
                'background:linear-gradient(180deg,#ffffff 0%, #f6f9ff 100%);'
                'box-shadow:0 10px 24px rgba(15,23,42,.06);'
                'border:1px solid rgba(2,6,23,.06); position:relative;'
            ):
                with ui.element('div').classes('q-pa-xl').style('text-align:center; padding-bottom:24px;'):
                    with ui.element('div').style(
                        'width:108px; height:108px; margin:25px auto 20px auto; border-radius:9999px;'
                        'display:flex; align-items:center; justify-content:center;'
                        'background:radial-gradient(60% 60% at 50% 50%, rgba(59,130,246,.18), rgba(59,130,246,.06));'
                        'box-shadow:inset 0 0 0 1px rgba(59,130,246,.25);'
                    ):
                        ui.icon('account_balance').classes('text-primary').style('font-size:56px;')

                    ui.label(f'{display_name},'
                             ).classes('text-h5 text-weight-medium')
                    ui.label(f'Twój portfel „{self.wallets[0].name}” nie ma jeszcze żadnych kont.'
                             ).classes('text-h5 text-weight-medium')
                    ui.label('Dodaj pierwsze konto — bankowe, gotówkowe lub maklerskie — by zacząć śledzić saldo i transakcje.'
                             ).classes('text-body2 text-grey-7 q-mt-xs')

                ui.separator().style('margin: 185px auto 15px auto; width: calc(100% - 80px);')

                ui.html(
                    '<div style="padding:0 40px 35px 40px;">'
                    '<small class="text-grey-7">Możesz dodać konta w różnych walutach.</small>'
                    '</div>'
                )
                
                create_btn = ui.button('Dodaj konto', icon='add') \
                    .props('color=primary unelevated size=lg no-caps') \
                    .classes('text-weight-medium') \
                    .style(
                        'position:absolute; left:50%; bottom:78px; transform:translateX(-50%);'
                        'min-width:288px; padding:16px 38px; border-radius:9999px;'
                        'font-size:16px; letter-spacing:.2px;'
                        'box-shadow:0 16px 34px rgba(59,130,246,.28), 0 6px 12px rgba(59,130,246,.18);'
                        'transition:transform .15s ease, box-shadow .15s ease;'
                    ).on('click', lambda: self.open_create_account_dialog())

                def lift(_=None):
                    create_btn.style(
                        'position:absolute; left:50%; bottom:78px; transform:translateX(-50%) translateY(-2px);'
                        'min-width:288px; padding:16px 38px; border-radius:9999px;'
                        'font-size:16px; letter-spacing:.2px;'
                        'box-shadow:0 22px 44px rgba(59,130,246,.34), 0 10px 18px rgba(59,130,246,.22);'
                        'transition:transform .15s ease, box-shadow .15s ease;'
                    )

                def drop(_=None):
                    create_btn.style(
                        'position:absolute; left:50%; bottom:78px; transform:translateX(-50%);'
                        'min-width:288px; padding:16px 38px; border-radius:9999px;'
                        'font-size:16px; letter-spacing:.2px;'
                        'box-shadow:0 16px 34px rgba(59,130,246,.28), 0 6px 12px rgba(59,130,246,.18);'
                        'transition:transform .15s ease, box-shadow .15s ease;'
                    )

                create_btn.on('mouseenter', lift)
                create_btn.on('mouseleave', drop)
                
    def get_top_tables_for_selected_wallets(self) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Build "top gainers" and "top losers" tables across all currently selected wallets.

        Returns:
            (gainers_rows, losers_rows) where each row is:
                {"sym": <symbol>, "pl_pct": <pnl percent float>, "pl_abs": <pnl amount float in view currency>}
        """

        if not self.selected_wallet:
            return [], []

        all_perf = []
        for wallet in self.selected_wallet:
            if getattr(wallet, "top_gainers", None):
                all_perf.extend(wallet.top_gainers)
            if getattr(wallet, "top_losers", None):
                all_perf.extend(wallet.top_losers)

        if not all_perf:
            return [], []

        gainers_sorted = sorted(all_perf, key=lambda p: p.pnl_pct, reverse=True)
        losers_sorted = sorted(all_perf, key=lambda p: p.pnl_pct)

        top_gainers = gainers_sorted[:5]
        top_losers = losers_sorted[:5]

        def perf_to_row(p) -> Dict[str, Any]:
            """Convert performance object to a compact UI row."""
            pct = float(p.pnl_pct * Decimal("100")) if p.pnl_pct is not None else 0.0

            tx_ccy = p.currency.value if hasattr(p.currency, "value") else str(p.currency)
            pl_dec = change_currency_to(
                amount=p.pnl_amount,
                view_currency=self.view_currency.value,
                transaction_currency=tx_ccy,
                rates=self.currency_rate,
            )
            pl_abs = float(pl_dec)

            return {
                "sym": p.symbol,
                "pl_pct": pct,
                "pl_abs": pl_abs,
            }

        gainers_rows = [perf_to_row(p) for p in top_gainers]
        losers_rows = [perf_to_row(p) for p in top_losers]

        return gainers_rows, losers_rows
    
    def compute_stocks_total_in_view_ccy(self) -> Decimal:
        """
        Compute total value of all brokerage accounts across selected wallets,
        converted into the current view currency.

        Returns:
            Total as Decimal in view currency.
        """

        total = Decimal("0")

        for wallet in self.selected_wallet:
            for ba in wallet.brokerage_accounts:
                for ccy, amount in ba.totals_by_currency.items():
                    tx_ccy = ccy.value if hasattr(ccy, "value") else str(ccy)
                    if amount is None:
                        continue

                    converted = change_currency_to(
                        amount=amount,
                        view_currency=self.view_currency.value,
                        transaction_currency=tx_ccy,
                        rates=self.currency_rate,
                    )
                    total += converted

        return total
    
    def capture_investments_label(self) -> str:
        """
        Compute the total investments value (stocks + properties + metals) in view currency
        and return both the numeric total and a formatted KPI label.

        Returns:
            (total_investments, label)
        """

        cur = self.view_currency.value or "PLN"

        stocks = self.compute_stocks_total_in_view_ccy()
        props = self.compute_properties_total_in_view_ccy()
        metals = self.compute_metals_total_in_view_ccy()
        total = stocks + props + metals
        return total, cash_kpi_label(total, cur, decimals=0)
    
    def capture_netto_label(self, cash_total, investment_total, debt_total):
        """
        Compute net worth label: cash + investments - debts.

        Args:
            cash_total: Total cash in view currency
            investment_total: Total investments in view currency
            debt_total: Total debts in view currency

        Returns:
            Formatted KPI label string.
        """
        cur = self.view_currency.value or "PLN"
        total = cash_total + investment_total - debt_total
        return cash_kpi_label(total, cur, decimals=0)
    
    def compute_capital_gains_ytd_label(self) -> str:
        """
        Sum YTD capital gains across selected wallets and return a formatted KPI label.

        Returns:
            KPI label string (in view currency).
        """
        cur = self.view_currency.value or "PLN"
        total = Decimal("0")

        for w in self.selected_wallet:  
            for ccy, amount in w.capital_gains_deposit_ytd.items():
                total += change_currency_to(amount, cur, ccy.value, self.currency_rate)
            for ccy, amount in w.capital_gains_broker_ytd.items():
                total += change_currency_to(amount, cur, ccy.value, self.currency_rate)
            for ccy, amount in w.capital_gains_real_estate_ytd.items():
                total += change_currency_to(amount, cur, ccy.value, self.currency_rate)
            for ccy, amount in w.capital_gains_metal_ytd.items():
                total += change_currency_to(amount, cur, ccy.value, self.currency_rate)

        return cash_kpi_label(total, cur, decimals=0)
    
    def build_brokerage_tx_rows_for_selected_wallet(self) -> List[Dict[str, Any]]:
        """
        Build table rows for recent brokerage events across selected wallets.

        Each row contains:
            date, ts, sym, type, qty, price, value, ccy (view currency), account

        Returns:
            List of rows sorted by timestamp descending.
        """

        if not self.selected_wallet:
            return []
 
        rows: List[Dict[str, Any]] = []

        for wallet in self.selected_wallet:
            events = getattr(wallet, "last_brokerage_events", []) or []
            for ev in events:
                dt: datetime | None = getattr(ev, "date", None)
                sym: str = getattr(ev, "sym", "")
                typ = getattr(ev, "type", "")
                qty_dec = Decimal(str(getattr(ev, "qty", 0) or 0))
                price_dec = Decimal(str(getattr(ev, "price", 0) or 0))
                raw_value = getattr(ev, "value", None)
                tx_ccy = getattr(ev, "ccy", None)
                logger.info(f"tx_ccy: {tx_ccy}")

                tx_ccy = str(tx_ccy)

                if raw_value is not None:
                    value_dec = Decimal(str(raw_value))
                else:
                    value_dec = qty_dec * price_dec

                price_view = change_currency_to(
                    amount=price_dec,
                    view_currency=self.view_currency.value,
                    transaction_currency=tx_ccy,
                    rates=self.currency_rate,
                )
                value_view = change_currency_to(
                    amount=value_dec,
                    view_currency=self.view_currency.value,
                    transaction_currency=tx_ccy,
                    rates=self.currency_rate,
                )

                if isinstance(dt, datetime):
                    ts = int(dt.timestamp())
                    date_str = dt.strftime("%Y-%m-%d %H:%M")
                else:
                    ts = 0
                    date_str = str(getattr(ev, "date", ""))

                rows.append(
                    {
                        "date": date_str,
                        "ts": ts,
                        "sym": sym,
                        "type": typ,
                        "qty": float(qty_dec),
                        "price": float(price_view),
                        "value": float(value_view),
                        "ccy": self.view_currency.value,
                        "account": getattr(ev, "account", ""),
                    }
                )

        rows.sort(key=lambda r: r.get("ts", 0), reverse=True)
        return rows
    
    def compute_debts_total_in_view_ccy(self) -> Decimal:
        """
        Compute total debts across selected wallets converted to view currency.

        Returns:
            Total debts as Decimal in view currency (positive magnitude; sign handled by label funcs).
        """
        total = Decimal("0")
        cur = self.view_currency.value or "PLN"

        for w in (self.selected_wallet or []):
            for d in getattr(w, "debts", []) or []:
                if d.amount is None:
                    continue

                tx_ccy = d.currency.value if hasattr(d.currency, "value") else str(d.currency)

                total += change_currency_to(
                    amount=d.amount,
                    view_currency=cur,
                    transaction_currency=tx_ccy,
                    rates=self.currency_rate,
                )
        return total

    def capture_debts_label(self) -> str:
        """
        Create the debts KPI label.

        Returns:
            (total_debts, label)
            label includes a minus sign when total > 0 (because it's a liability KPI).
        """
        cur = self.view_currency.value or "PLN"
        total = self.compute_debts_total_in_view_ccy()
        if total == Decimal(0):
            return total, f"{format_pl_amount(abs(total), decimals=0)} {cur}"
        return total,  f"−{format_pl_amount(abs(total), decimals=0)} {cur}"

    def capture_debts_sub(self) -> str:
        """
        Build a subtitle string for debts KPI, describing count and average interest rate (if available).
        """
        items = []
        rates = []

        for w in (self.selected_wallet or []):
            for d in getattr(w, "debts", []) or []:
                items.append(d)
                ir = getattr(d, "interest_rate_pct", None)
                if ir is not None:
                    rates.append(ir)

        cnt = len(items)
        if cnt == 0:
            return "Brak zobowiązań"

        avg = (sum(rates) / len(rates)) if rates else None
        if avg is None:
            return f"{cnt} zobowiązań"
        return f"{cnt} zobowiązań · średn. {format_pl_amount(avg, decimals=1)}%"
    
    def compute_assets_by_currency(self) -> dict[str, Decimal]:
        """
        Compute total assets grouped by *original currency code*, but values are expressed in view currency.

        This is useful for "assets by currency" charts while keeping a consistent unit (view currency).

        Returns:
            Mapping {currency_code: total_in_view_currency}
        """
        totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

        wallets = self.selected_wallet or []
        for w in wallets:
            for acc in getattr(w, "accounts", []) or []:
                ccy = acc.currency.value if hasattr(acc.currency, "value") else str(acc.currency)
                available = Decimal(str(getattr(acc, "available", 0) or 0))
                blocked = Decimal(str(getattr(acc, "blocked", 0) or 0))
                base_value = (available + blocked)
                totals[ccy] += change_currency_to(
                                                amount=base_value,
                                                view_currency=self.view_currency.value,
                                                transaction_currency=ccy,
                                                rates=self.currency_rate,
                                            )

            for b in getattr(w, "brokerage_accounts", []) or []:
                for ccy, amt in (b.totals_by_currency or {}).items():
                    c = ccy.value if hasattr(ccy, "value") else str(ccy)
                    totals[c] += change_currency_to(
                                                amount=amt,
                                                view_currency=self.view_currency.value,
                                                transaction_currency=c,
                                                rates=self.currency_rate,
                                            )

        self.add_real_estates_to_currency_totals(totals)
        self.add_metals_to_currency_totals(totals)

        return dict(totals)
    
    def iter_real_estate_values(self) -> Iterator[Tuple[Decimal, str]]:
        """Yield (base_value, tx_ccy) for each real estate item."""
        for w in (self.selected_wallet or []):
            for p in getattr(w, "real_estates", []) or []:
                tx_ccy = p.purchase_currency.value

                if getattr(p, "price", None) and getattr(p, "area_m2", None):
                    base_value = dec(p.area_m2) * dec(p.price)
                else:
                    base_value = dec(getattr(p, "purchase_price", 0) or 0)

                if base_value > 0:
                    yield base_value, tx_ccy

    def iter_metal_values(self) -> Iterator[Tuple[Decimal, str]]:
        """Yield (base_value, tx_ccy) for each metal holding."""
        view_ccy = self.view_currency.value

        for w in (self.selected_wallet or []):
            for m in getattr(w, "metal_holdings", []) or []:
                grams = dec(getattr(m, "grams", "0") or "0")

                if getattr(m, "price", None) is not None and grams > 0:
                    base_value = grams * dec(m.price)
                    tx_ccy = (
                        m.price_currency.value
                        if getattr(m, "price_currency", None) is not None
                        else (m.cost_currency.value if m.cost_currency else view_ccy)
                    )
                else:
                    if getattr(m, "cost_basis", None) is None:
                        continue
                    base_value = dec(m.cost_basis)
                    tx_ccy = m.cost_currency.value if m.cost_currency else view_ccy

                if base_value > 0:
                    yield base_value, tx_ccy

    def _sum_in_view_ccy(self, rows: Iterable[Tuple[Decimal, str]]) -> Decimal:
        """
        Sum a sequence of (base_value, tx_ccy) pairs into view currency.
        """
        total = Decimal("0")
        view_ccy = self.view_currency.value

        for base_value, tx_ccy in rows:
            total += change_currency_to(
                amount=base_value,
                view_currency=view_ccy,
                transaction_currency=tx_ccy,
                rates=self.currency_rate,
            )
        return total

    def _add_to_totals_in_view_ccy(self, totals: Dict[str, Decimal], rows: Iterable[Tuple[Decimal, str]]) -> None:
        """
        Add values from rows into `totals[tx_ccy]`, converting each base_value into view currency.
        """

        view_ccy = self.view_currency.value

        for base_value, tx_ccy in rows:
            totals[tx_ccy] += change_currency_to(
                amount=base_value,
                view_currency=view_ccy,
                transaction_currency=tx_ccy,
                rates=self.currency_rate,
            )

    def compute_properties_total_in_view_ccy(self) -> Decimal:
        """Compute total properties value (real estate) in view currency."""
        return self._sum_in_view_ccy(self.iter_real_estate_values())

    def compute_metals_total_in_view_ccy(self) -> Decimal:
        """Compute total metals value in view currency."""
        return self._sum_in_view_ccy(self.iter_metal_values())

    def add_real_estates_to_currency_totals(self, totals: Dict[str, Decimal]) -> None:
        """Accumulate real estate values into `totals` (values in view currency)."""
        self._add_to_totals_in_view_ccy(totals, self.iter_real_estate_values())

    def add_metals_to_currency_totals(self, totals: Dict[str, Decimal]) -> None:
        """Accumulate metal holding values into `totals` (values in view currency)."""
        self._add_to_totals_in_view_ccy(totals, self.iter_metal_values())
        
    def compute_capital_gains_totals_in_view_ccy(self) -> Dict[str, Decimal]:
        """
        Compute YTD capital gains totals by bucket in view currency.

        Buckets:
            - Stocks
            - Cash
            - Properties
            - Metals
        """
        
        view_ccy = self.view_currency.value
        totals: Dict[str, Decimal] = {
            "Stocks": Decimal("0"),
            "Cash": Decimal("0"),
            "Properties": Decimal("0"),
            "Metals": Decimal("0"),
        }

        for w in (self.selected_wallet or []):
            for c, a in (getattr(w, "capital_gains_broker_ytd", {}) or {}).items():
                tx_ccy = ccy_to_str(c)
                amt = dec(a)
                totals["Stocks"] += change_currency_to(
                    amt, view_ccy, tx_ccy, self.currency_rate
                )

            for c, a in (getattr(w, "capital_gains_deposit_ytd", {}) or {}).items():
                tx_ccy = ccy_to_str(c)
                amt = dec(a)
                totals["Cash"] += change_currency_to(
                    amt, view_ccy, tx_ccy, self.currency_rate
                )
                
            for c, a in (getattr(w, "capital_gains_real_estate_ytd", {}) or {}).items():
                tx_ccy = ccy_to_str(c)
                amt = dec(a)
                totals["Properties"] += change_currency_to(
                    amt, view_ccy, tx_ccy, self.currency_rate
                )
                
            for c, a in (getattr(w, "capital_gains_metal_ytd", {}) or {}).items():
                tx_ccy = ccy_to_str(c)
                amt = dec(a)
                totals["Metals"] += change_currency_to(
                    amt, view_ccy, tx_ccy, self.currency_rate
                )
        return totals
    
    def compute_goals_ytd_inputs(self) -> dict:
        """
        Compute inputs for your YTD goals/flow chart:
        - revenue targets and actuals (YTD)
        - expense budgets and actuals (YTD)
        - current month index
        - unit suffix string

        Returns:
            A dict suited for chart/legend components.
        """

        view_ccy = self.view_currency.value or "PLN"
        now = datetime.now(timezone.utc)
        month_index = now.month - 1

        rev_target_year = Decimal("0")
        exp_budget_year = Decimal("0")

        for w in (self.selected_wallet or []):
            g: YearGoalOut = getattr(w, "year_goal", None)
            if not g:
                continue

            g_ccy = g.currency.value if hasattr(g.currency, "value") else str(g.currency)

            rev_target_year += change_currency_to(
                amount=Decimal(str(g.rev_target_year or "0")),
                view_currency=view_ccy,
                transaction_currency=g_ccy,
                rates=self.currency_rate,
            )
            exp_budget_year += change_currency_to(
                amount=Decimal(str(g.exp_budget_year or "0")),
                view_currency=view_ccy,
                transaction_currency=g_ccy,
                rates=self.currency_rate,
            )
        rev_actual_ytd = sum(
            change_currency_to(a, self.view_currency.value, c.value, self.currency_rate)
            for w in self.selected_wallet
            for c, a in (w.income_ytd_by_currency or {}).items()
        )

        exp_actual_ytd = sum(
            change_currency_to(a, self.view_currency.value, c.value, self.currency_rate)
            for w in self.selected_wallet
            for c, a in (w.expense_ytd_by_currency or {}).items()
        )

        return {
            "rev_target_year": float(rev_target_year),
            "exp_budget_year": float(exp_budget_year),
            "rev_actual_ytd": float(rev_actual_ytd),
            "exp_actual_ytd": abs(float(exp_actual_ytd)),
            "month_index": month_index,
            "unit": f" {view_ccy}",
        }
        
    def compute_dash_flow_series_last_8m(self) -> tuple[list[str], list[float], list[float], list[float]]:
        """
        Compute the last 8 months series for your dashboard flow chart:
            months, income_net (income - capital), expense, capital

        Returns:
            (months, inc, exp, capi) lists aligned by index.
        """
        view_ccy = self.view_currency.value or "PLN"
        rates = self.currency_rate

        months: list[str] = []
        for w in (self.selected_wallet or []):
            if getattr(w, "dash_flow_8m", None):
                months = [x.month for x in w.dash_flow_8m]
                break
        if not months:
            now = datetime.now(timezone.utc)
            months = [(month_floor(now) - relativedelta(months=i)).strftime("%Y-%m") for i in range(7, -1, -1)]

        inc: list[float] = []
        exp: list[float] = []
        capi: list[float] = []

        for idx, ms in enumerate(months):
            income_view = Decimal("0")
            expense_view = Decimal("0")
            cap_view = Decimal("0")

            for w in (self.selected_wallet or []):
                items = getattr(w, "dash_flow_8m", []) or []
                if idx >= len(items) or items[idx].month != ms:
                    it = next((x for x in items if x.month == ms), None)
                else:
                    it = items[idx]

                if not it:
                    continue

                for c, a in (it.income_by_currency or {}).items():
                    income_view += change_currency_to(a, view_ccy, c.value, rates)

                for c, a in (it.expense_by_currency or {}).items():
                    expense_view += change_currency_to(a, view_ccy, c.value, rates)

                for c, a in (it.capital_by_currency or {}).items():
                    cap_view += change_currency_to(a, view_ccy, c.value, rates)

            inc_val = income_view - cap_view

            inc.append(float(inc_val))
            exp.append(float(expense_view))
            capi.append(float(cap_view))

        return months, inc, exp, capi
    
    
@ui.page('/wallet')
async def wallet(request: Request):

    add_style()
    add_user_style()

    Wallet(request)
      
    

    
    
    

        
