from nicegui import ui
from fastapi import Request
from typing import List
import logging

from components.navbar_footer import footer
from components.panel.card import panel 
from static.style import add_style, add_user_style
from components.alerts import ALERTS, alerts_panel_card
from components.transaction import transactions_table_card, cash_transactions_table_card, render_create_transaction_dialog
from components.cards import (expenses_table_card, goals_bullet_card, 
                              render_top5_table_observer, render_top5_table, pie_card,
                              line_card, kpi_card, bar_card)

from utils.utils import export_csv
from utils.money import cash_total_in_pln, cash_total_in_eur, cash_total_in_usd, cash_kpi_label
from demo.factories import create_demo_wallet_payload
from clients.wallet_client import WalletClient
from clients.nbp_client import NBPClient
from schemas.wallet import ClientWalletSyncResponse, Currency, WalletListItem
from components.context.nav_context import NavContextBase
from components.account import render_create_account_dialog
from services.current_user import get_current_user_or_create
from storage.session_state import set_wallets_from_payload, set_current_user_id

logger = logging.getLogger(__name__)


class Wallet(NavContextBase):
    def __init__(self, request):
        """
        Initialize Wallet context with request, clients
        """
        super().__init__()
        self.request = request
        self.wallet_client = WalletClient()
        self.nbp_client = NBPClient()
        
        self.months = ['2025-01', '2025-02', '2025-03', '2025-04', '2025-05', '2025-06', '2025-07', '2025-08']
        self.revenue = [120000, 118500, 123400, 125200, 113000, 122500, 145000, 130000]    
        self.cpi_idx = [100.0, 101.1, 101.9, 102.7, 101.2, 105.7, 102.3, 101.2] 
        self.inc = [4000.0, 4300.3, 4200.2, 4600.6, 4500.5, 4800.8, 5000.0, 8000]
        self.exp = [3200.2, 3330.3, 3400.4, 3500.5, 3600.6, 3600.6, 3700.7, 7000]
        self.capi = [20000, -10000, 3000, 8000, -24000, 15000, 8000, 9000]
        
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
        
        set_wallets_from_payload(self.wallets)
        self.accounts = [acc for w in self.wallets for acc in w.accounts]
        set_current_user_id(self.user_id)

        self.render_navbar()
        
        self.currency_rate = await self.nbp_client.get_usd_eur_pln()

        if not self.wallets:
            logger.warning("No wallets found. Rendering wallet onboarding.")
            self.render_no_wallet_onboarding(self.username)
        elif not self.accounts:
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
            
        return cash_kpi_label(total, cur, decimals=0)

    def on_currency_change(self):
        """
        Callback triggered when the selected currency changes.
        Updates the displayed cash KPI label accordingly.
        """
        logger.info(f"Currency changed to: {self.view_currency.value}")
        self.kpi_cash_label.text = self.capture_cash_label()

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

                    ui.button('Notatki', icon='edit_note'
                              ).props('color=primary unelevated no-caps padding="xs lg"'
                                      ).on('click', lambda e: notes_dialog.open()).style('flex:0 0 auto;')
        
        with ui.dialog() as notes_dialog, panel('Notatki'):
            ui.textarea(value='Moje notatki…').props('autogrow outlined dense').classes('w-[520px]')
            with ui.row().classes('justify-end w-full'):
                ui.button('Zamknij', on_click=notes_dialog.close).props('flat') 
                
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
                kpi_card('Wartość netto', '1 234 567 PLN', '+2.4% m/m · +8.1% YTD')
                
                cash = self.capture_cash_label()
                self.kpi_cash_label = kpi_card('Gotówka', cash, '25% portfela and 5% free')
                kpi_card('Inwestycje', '876 543 PLN', 'P/L YTD +8.1%')
                kpi_card('Zobowiązania', '−345 000 PLN', '2 kredyty · średn. 6.2%')
                kpi_card('Wydatki (mies.)', '7 890 PLN', 'Budżet 85%')
                kpi_card('Zyski Kapitałowe (mies.)', '20 890 PLN', '+2.1% YTD')
    
            ui.space().style('height:20px')
            
            with ui.grid(columns=4).classes('gap-3 w-full items-stretch q-mb-sm'):
                with panel('Top Gaining Stocks'):
                    render_top5_table([
                        {'sym': 'MSFT', 'pl_pct': 15.00, 'pl_abs': 1140},
                        {'sym': 'MCD', 'pl_pct': 10.51, 'pl_abs': 670},
                        {'sym': 'AAPL', 'pl_pct': 9.04, 'pl_abs': 1350},
                        {'sym': 'NVDA', 'pl_pct': 8.30, 'pl_abs': 520},
                        {'sym': 'AMZN', 'pl_pct': 5.90, 'pl_abs': 410},
                    ], tone='positive') 

                with panel('Top Losing Stocks'):
                    render_top5_table([
                        {'sym': 'XYZ', 'pl_pct': -6.40, 'pl_abs': -820},
                        {'sym': 'ABC', 'pl_pct': -5.10, 'pl_abs': -560},
                        {'sym': 'UBER', 'pl_pct': -4.80, 'pl_abs': -430},
                        {'sym': 'GOOGL', 'pl_pct': -3.20, 'pl_abs': -390},
                        {'sym': 'META', 'pl_pct': -2.10, 'pl_abs': -210},
                    ], tone='negative') 

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
                pie_card('Portfolio Allocation',
                         [{'name': 'USD', 'value': 40}, {'name': 'EUR', 'value': 35}, {'name': 'PLN', 'value': 24}])

                pie_card('Capital Gains',
                         [{'name': 'Stocks', 'value': 26.6},
                          {'name': 'Cash', 'value': 15.7},
                          {'name': 'Properties', 'value': 14.7},
                          {'name': 'Crypto', 'value': 0},
                          {'name': 'Raw materials', 'value': 4.7},
                          ])

                goals_bullet_card(
                    'Cele YTD',
                    rev_target_year=1_380_000, 
                    exp_budget_year=756_000,   
                    rev_actual_ytd=962_000,
                    exp_actual_ytd=514_500,
                    month_index=7,    
                )

                bank_tx = [
                    {'date': '2025-04-18 13:05', 'payee': 'Biedronka', 'category': 'Żywność', 'amount': -123.45,
                     'method': 'Karta', 'account': 'mBank', 'id': 'TX1'},
                    {'date': '2025-04-18 09:11', 'payee': 'Przelew od ACME', 'category': 'Wynagrodzenie',
                     'amount': 8500, 'method': 'Przelew', 'account': 'mBank', 'id': 'TX2'},
                    {'date': '2025-04-17', 'payee': 'Media Expert', 'category': 'RTV/AGD', 'amount': -899.99,
                     'method': 'Karta', 'account': 'mBank', 'id': 'TX3'},
                    {'date': '2025-04-16', 'payee': 'Zwrot Allegro', 'category': 'Zwroty', 'amount': 219.00,
                     'method': 'Przelew', 'account': 'mBank', 'id': 'TX4'},
                    {'date': '2025-04-15', 'payee': 'Czynsz', 'category': 'Mieszkanie', 'amount': -1800,
                     'method': 'Przelew', 'account': 'mBank', 'id': 'TX5'},
                    {'date': '2025-04-14', 'payee': 'Orlen', 'category': 'Paliwo', 'amount': -240.50,
                     'method': 'Karta', 'account': 'mBank', 'id': 'TX6'},
                ]
                cash_transactions_table_card(bank_tx, top=5, opening_balance=3200.00)
                
                tx = [
                    {'date': '2025-04-18 13:05', 'sym': 'AAPL', 'type': 'BUY', 'qty': 10, 'price': 182.35, 
                     'ccy': 'USD', 'account': 'mBank'},
                    {'date': '2025-04-17', 'sym': 'MSFT', 'type': 'SELL', 'qty': 5, 'price': 410.0,
                     'ccy': 'USD', 'account': 'mBank'},
                    {'date': '2025-04-15', 'sym': 'SPY', 'type': 'DIV', 'qty': 0, 'price': 0, 'value': 35.12,
                     'ccy': 'USD', 'account': 'IBKR'},
                    {'date': '2025-04-12', 'sym': 'TSLA', 'type': 'FEE', 'qty': 0, 'price': 0, 'value': -2.5,
                     'ccy': 'USD', 'account': 'IBKR', 'note': 'commission'},
                    {'date': '2025-04-10', 'sym': 'PKO', 'type': 'BUY', 'qty': 100, 'price': 50.1,
                     'ccy': 'PLN', 'account': 'mBank'},
                    {'date': '2025-04-02', 'sym': 'NVDA', 'type': 'SELL', 'qty': 2, 'price': 900.0,
                     'ccy': 'USD', 'account': 'mBank'},
                ]
                transactions_table_card(tx, top=5, sort_by='date', reverse=True)
                
                rows = [
                    {'name': 'Czynsz', 'amount': 1800, 'category': 'Mieszkanie', 'due_day': 10, 'account': 'mBank'},
                    {'name': 'Prąd', 'amount': 210, 'category': 'Media', 'due_day': 15, 'account': 'mBank'},
                    {'name': 'Internet', 'amount': 69, 'category': 'Media', 'due_day': 8, 'account': 'Revolut'},
                    {'name': 'Telefon', 'amount': 45, 'category': 'Media', 'due_day': 20, 'account': 'Revolut'},
                    {'name': 'Spotify', 'amount': 24.99, 'category': 'Subskrypcja', 'due_day': 5, 'account': 'Visa'},
                    {'name': 'Netflix', 'amount': 29.99, 'category': 'Subskrypcja', 'due_day': 12, 'account': 'Visa',
                     'note': 'Plan Standard'},
                ]

                expenses_table_card(rows, top=5, sort_by='amount', reverse=True)

            ui.space().style('height:15px')
            
            with ui.grid(columns=2).classes('gap-3 w-full items-stretch'):    
                line_card(
                    'Przychody: nominalnie vs realnie',
                    x=self.months, y=self.revenue,
                    cpi=self.cpi_idx, base='first',                 
                    y_suffix=' PLN'
                )    
                
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

                open_create = render_create_account_dialog(self, self.wallets[0].id)
                
                create_btn = ui.button('Dodaj konto', icon='add') \
                    .props('color=primary unelevated size=lg no-caps') \
                    .classes('text-weight-medium') \
                    .style(
                        'position:absolute; left:50%; bottom:78px; transform:translateX(-50%);'
                        'min-width:288px; padding:16px 38px; border-radius:9999px;'
                        'font-size:16px; letter-spacing:.2px;'
                        'box-shadow:0 16px 34px rgba(59,130,246,.28), 0 6px 12px rgba(59,130,246,.18);'
                        'transition:transform .15s ease, box-shadow .15s ease;'
                    ).on('click', lambda: open_create())

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
    
    
@ui.page('/wallet')
async def wallet(request: Request):

    add_style()
    add_user_style()

    Wallet(request)
      
    

    
    
    

        
