from nicegui import ui, app
from fastapi import Request
import logging

from components.navbar_footer import nav, footer
from components.panel.card import panel 
from static.style import add_style, add_user_style
from components.alerts import ALERTS, alerts_panel_card
from components.transaction import transactions_table_card, cash_transactions_table_card
from components.cards import (expenses_table_card, goals_bullet_card, 
                              render_top5_table_observer, render_top5_table, pie_card,
                              line_card, kpi_card, bar_card)
from utils.utils import export_csv

logger = logging.getLogger(__name__)


class Wallet:
    def __init__(self, request):
        
        self.months = ['2025-01', '2025-02', '2025-03', '2025-04', '2025-05', '2025-06', '2025-07', '2025-08']
        self.revenue = [120000, 118500, 123400, 125200, 113000, 122500, 145000, 130000]    
        self.cpi_idx = [100.0, 101.1, 101.9, 102.7, 101.2, 105.7, 102.3, 101.2] 
        self.inc = [4000.0, 4300.3, 4200.2, 4600.6, 4500.5, 4800.8, 5000.0, 8000]
        self.exp = [3200.2, 3330.3, 3400.4, 3500.5, 3600.6, 3600.6, 3700.7, 7000]
        self.capi = [20000, -10000, 3000, 8000, -24000, 15000, 8000, 9000]
        
        self.build_ui()

    def build_ui(self):
        
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
                    ui.select(['Mój portfel', 'Portfel A', 'Portfel Demo'], value='Mój portfel'
                              ).props('label=Portfel dense outlined').style('flex:0 0 auto;')

                    ui.button('Add Transaction', icon='add'
                              ).props('outline no-caps padding="xs lg"').style('flex:0 0 auto;')
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

        root = ui.element('div').classes('dashboard-root').style('width:min(1500px,94vw); margin:0 auto;')
                
        with root:
            with ui.grid(columns=6).classes('gap-4'):
                kpi_card('Wartość netto', '1 234 567 PLN', '+2.4% m/m · +8.1% YTD')
                kpi_card('Gotówka', '123 456 PLN', '25% portfela and 5% free')
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
            
        with ui.dialog() as notes_dialog, panel('Notatki'):
            ui.textarea(value='Moje notatki…').props('autogrow outlined dense').classes('w-[520px]')
            with ui.row().classes('justify-end w-full'):
                ui.button('Zamknij', on_click=notes_dialog.close).props('flat')
        
    
@ui.page('/wallet')
async def wallet(request: Request):
    
    user_data = await app.storage.session.get(request.cookies.get('sessionid'))
    logger.debug(f"sessuion: {user_data}")

    add_style()
    add_user_style()

    nav("User")
    
    Wallet(request)
      
    footer()

    
    
    

        
