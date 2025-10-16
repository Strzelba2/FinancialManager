from nicegui import ui
from fastapi import Request
from datetime import datetime, timedelta
import itertools
import logging

from static.style import add_style, add_user_style, add_table_style
from components.context.nav_context import NavContextBase
from clients.wallet_client import WalletClient
from components.navbar_footer import footer
from utils.utils import fmt_money, parse_date

logger = logging.getLogger(__name__)

ID_GEN = itertools.count(1)
DB = {
    'mBank': [
        {'id': f'TX-{next(ID_GEN)}', 'date': '2025-08-20 10:22', 'payee': 'Biedronka', 'category': 'Żywność',
         'amount': -123.45, 'ccy': 'PLN', 'method': 'Karta', 'type': 'OUT', 'note': ''},
        {'id': f'TX-{next(ID_GEN)}', 'date': '2025-08-19 09:00', 'payee': 'ACME S.A.', 'category': 'Wynagrodzenie',
         'amount': 8500.00, 'ccy': 'PLN', 'method': 'Przelew', 'type': 'IN', 'note': 'sierpień'},
    ],
    'Revolut': [
        {'id': f'TX-{next(ID_GEN)}', 'date': '2025-07-18', 'payee': 'Orlen', 'category': 'Paliwo',
         'amount': -240.50, 'ccy': 'PLN', 'method': 'Karta', 'type': 'OUT', 'note': ''},
    ],
}
ACCOUNTS = list(DB.keys())
CURRENT_USER = 'User' 


class Transactions(NavContextBase):
    def __init__(self, request):
        super().__init__()
        self.request = request
        self.wallet_client = WalletClient()
        
        self.range_btn = None
        self.custom_row = None
        
        self.range_state = {'value': 'ALL'}
        self.range_labels = {'ALL': 'All', '1M': 'Last Month', '3M': 'Last 3 Months', '1Y': 'Last Year',
                             'CUSTOM': 'Date'}
        self.type_map = {'Wszystkie': 'ALL', 'Wpływ': 'IN', 'Wypływ': 'OUT'}

        self.state = {
            'accounts': set(ACCOUNTS), 
            'categories': set(),         
            'type': 'ALL',             
            'from': '',                
            'to': '',                   
        }
        
        ui.timer(0.01, self._init_async, once=True)
        
    async def _init_async(self):
        self.render_navbar()
        self.build_ui()
        footer()

    def build_ui(self):
        
        with ui.column().classes('w-[100vw] gap-1'):
            self.header_card = ui.card().classes('elevated-card q-pa-sm q-mb-md')\
                .style('width:min(1600px,98vw); margin:0 auto 1px;')               
            self.manage_card = ui.card().classes('elevated-card q-pa-sm q-mb-md')\
                .style('width:min(1600px,98vw); margin:0 auto 1px;')
            self.table_card = ui.card().classes('elevated-card q-pa-sm q-mb-md')\
                .style('width:min(1600px,98vw); margin:0 auto 1px;')

        self.render_all()

    def to_type_from_amount(self, amount: float) -> str:
        return 'IN' if (amount or 0) >= 0 else 'OUT'

    def category_color(self, cat: str) -> str:
        m = {
            'Żywność': 'orange',
            'Wynagrodzenie': 'positive',
            'Paliwo': 'warning',
            'Transport': 'info',
            'Opłaty': 'negative',
            'Rozrywka': 'accent',
        }
        return m.get((cat or '').strip(), 'info')

    def method_color(self, method: str) -> str:
        m = {'Karta': 'primary', 'Przelew': 'secondary', 'Gotówka': 'grey'}
        return m.get((method or '').strip(), 'secondary')
    
    def all_categories(self) -> list[str]:
        cats = set()
        for lst in DB.values():
            for r in lst:
                c = (r.get('category') or '').strip()
                if c:
                    cats.add(c)
        logger.info(f"all_categories: {cats}")
        return sorted(cats)
    
    def load_rows(self):
        rows = []
        for acc in (self.state['accounts'] or set(ACCOUNTS)):
            for r in DB.get(acc, []):
                rows.append({
                    **r,
                    'account': acc,
                    'user': r.get('user') or CURRENT_USER,
                    'from_name': CURRENT_USER,    
                    'to_name': r.get('payee', ''),   
                })
        if self.state['type'] != 'ALL':
            want_in = (self.state['type'] == 'IN')
            rows = [r for r in rows if r.get('type') == ('IN' if want_in else 'OUT')]

        if self.state['categories']:
            rows = [r for r in rows if r.get('category') in self.state['categories']]

        d_from = parse_date(self.state['from'] or None)
        d_to = parse_date(self.state['to'] or None)
        if d_from:
            rows = [r for r in rows if (parse_date(r.get('date')) or datetime.min) >= d_from]
        if d_to: 
            rows = [r for r in rows if (parse_date(r.get('date')) or datetime.min) <= d_to]

        rows.sort(key=lambda r: (parse_date(r.get('date')) or datetime.min), reverse=True)
        prepared = []
        for r in rows:
            prepared.append(
                {
                    **r,
                    'amount_fmt': fmt_money(r.get('amount', 0), r.get('ccy', 'PLN')),
                    'date_disp': (
                        (parse_date(r.get('date')) or datetime.min).strftime('%Y-%m-%d %H:%M')
                        if ':' in str(r.get('date', ''))
                        else (r.get('date') or '')
                    ),
                    'category_color': self.category_color(r.get('category', '')),
                    'method_color': self.method_color(r.get('method', '')),
                }
            )
        return prepared
    
    def current_balance(self, rows):
        return sum((r.get('amount') or 0.0) for r in rows)
    
    def on_save(self, payload: dict, old_account: str | None = None):
        pass
        self.render_all()
        
    def delete_one(self, tx_id: str):
        for a, lst in DB.items():
            if any(r['id'] == tx_id for r in lst):
                DB[a] = [r for r in lst if r['id'] != tx_id]
                break
        self.render_all()
        
    def apply_quick_range(self, mode: str):
        today = datetime.now().date()
        if mode == '1M':
            self.state['from'], self.state['to'] = (today - timedelta(days=30)).strftime('%Y-%m-%d'), ''
        elif mode == '3M':
            self.state['from'], self.state['to'] = (today - timedelta(days=90)).strftime('%Y-%m-%d'), ''
        elif mode == '1Y':
            self.state['from'], self.state['to'] = (today - timedelta(days=365)).strftime('%Y-%m-%d'), ''
        else:
            self.state['from'], self.state['to'] = '', ''
        self.render_all()
        
    def set_range(self, mode: str):
        logger.info(f"_set_range: {mode}")
        self.range_state['value'] = mode
        if self.range_btn:
            logger.info(f"range_btn: {self.range_labels[mode]}")
            self.range_btn.text = f"{self.range_labels[mode]} ▾"

        if self.custom_row:
            logger.info("custom_row:")
            self.custom_row.style('display:flex' if mode == 'CUSTOM' else 'display:none')

        if mode == 'CUSTOM':
            self.render_table(self.load_rows())
        else:
            self.apply_quick_range(mode)
            
    def on_accounts_change(self, e):
        vals: list[str] = list(e.sender.value or [])
        if 'Wszystkie' in vals or not vals:
            if not vals:
                self.state['accounts'] = set(ACCOUNTS)
            elif (vals[0] == "Wszystkie" and len(vals) <= 1):
                logger.info("wal")
                self.state['accounts'] = set(ACCOUNTS) 
                self.sel_accounts.set_value(["Wszystkie"])
            elif (vals[0] == "Wszystkie" and len(vals) >= 1):
                self.state['accounts'] = set(vals[1:]) 
                self.sel_accounts.set_value(vals[1:])
            elif (vals[-1] == "Wszystkie" or not vals):
                self.state['accounts'] = set(ACCOUNTS) 
                self.sel_accounts.set_value(["Wszystkie"])
            else:
                vals = [v for v in vals if v != 'Wszystkie']
                self.state['accounts'] = set(vals)
                self.sel_accounts.set_value(vals)
            
        else:
            vals = [v for v in vals if v != 'Wszystkie']
            self.state['accounts'] = set(vals)
            logger.info(f"vals: {vals}")
            self.sel_accounts.set_value(vals)
            
        rows = self.load_rows()
        self.render_table(rows)
        self.render_header(rows)
        e.sender.run_method('hidePopup')

    def on_categories_change(self, e):
        self.state['categories'] = set(list(e.sender.value or []))
        rows = self.load_rows()
        self.render_table(rows)
        self.render_header(rows)
        e.sender.run_method('hidePopup')

    def on_type_change(self, e):
        logger.info(e)
        val = e.sender.value
        code = ""
        if val is None:
            code = self.type_map.get('Wszystkie')
        else:
            code = self.type_map.get(val)
            
        self.state['type'] = code  
        self.render_all()
        
    def make_multi_select(self, options, value, label, width='w-[260px]'):
        s = (
            ui.select(options, multiple=True, value=value, label=label)
            .classes(f'filter-field min-w-[220px] {width}')
            .props('outlined dense use-chips options-dense clearable color=primary popup-content-class=filter-popup')
        )
        return s
    
    def make_single_select(self, options, value, label, width='w-[200px]'):
        s = (
            ui.select(options, value=value, label=label)
            .classes(f'filter-field min-w-[180px] {width}')
            .props('outlined dense options-dense clearable color=primary popup-content-class=filter-popup')
        )
        return s
   
    def render_header(self, rows):
        self.header_card.clear()
        bal = self.current_balance(rows)
        sign_cls = 'pos' if bal >= 0 else 'neg'
        with self.header_card:
            with ui.row().style(
                    'display: flex; '
                    'justify-content: space-between; '
                    'align-items: center; '
                    'flex-wrap: wrap; '
                    'gap: 10px; '
                    'width: 100%; '
                    'padding: 1px 20px;'):
                with ui.row().style('display:flex; align-items:center; flex-wrap:wrap; gap:10px;'):
                    ui.label('Transakcje').classes('header-title')
                
                with ui.row().style('display:flex; align-items:center; flex-wrap:wrap; gap:10px;'):
                    ui.html(
                        f'<div class="balance-pill {sign_cls}">'
                        f'<span class="label">Balance: </span>'
                        f'<span class="amount">{fmt_money(bal)}</span>'
                        f'</div>'
                    )
                    with ui.button(
                            icon='add',
                            on_click=lambda: self.open_tx_dialog(on_save=self.on_save, accounts=ACCOUNTS),
                            ).props('round flat color=primary').classes('q-mr-sm'):

                        ui.tooltip('Dodaj transakcję').props('anchor="top middle" self="bottom middle"')
                        
    def render_manage(self):
        self.manage_card.clear()
        with self.manage_card:
            with ui.row().style(
                    'display: flex; '
                    'justify-content: space-between; '
                    'align-items: center; '
                    'flex-wrap: wrap; '
                    'gap: 10px; '
                    'width: 100%; '
                    'padding: 1px 30px;'):
                with ui.row().style('display:flex; align-items:center; flex-wrap:wrap; gap:1px;'):
                    with ui.column().classes('gap-1'):
                        accounts_list = list((*ACCOUNTS, 'Wszystkie'))
                        self.sel_accounts = self.make_multi_select(accounts_list, ['Wszystkie'], 'Konta')
                        with self.sel_accounts.add_slot('prepend'):
                            ui.icon('account_balance').classes('text-primary')
                        
                        self.sel_accounts.on('update:model-value', lambda e: self.on_accounts_change(e))

                    with ui.column().classes('gap-1 q-ml-lg'):
                        cat_options = self.all_categories()  
                        logger.info(f"cat_options: {cat_options}")

                        sel_categories = self.make_multi_select(
                            cat_options, sorted(list(self.state['categories'])), 'Kategorie'
                        )
                        with sel_categories.add_slot('prepend'):
                            ui.icon('label').classes('text-primary')
                        sel_categories.on('update:model-value', lambda e: self.on_categories_change(e))

                    with ui.column().classes('gap-1 q-ml-lg'):
                        
                        current_label = next(k for k, v in self.type_map.items() if v == self.state['type'])
                        sel_type = self.make_single_select(list(self.type_map.keys()), current_label, 'Rodzaj')
                        with sel_type.add_slot('prepend'):
                            ui.icon('swap_vert').classes('text-primary')
                 
                        sel_type.on('update:model-value', lambda e: (self.on_type_change(e)))
                    
                with ui.row().style('display:flex; align-items:center; flex-wrap:wrap; gap:1px;'):
           
                    with ui.row().classes('items-center gap-1'):
                        self.range_btn = ui.button(
                            f"{self.range_labels.get(self.range_state.get('value'))} ▾",
                            icon='event',
                        ).props('flat color=primary').classes('q-mr-sm')
                        with self.range_btn:
                            with ui.menu() as m:
                                m.props('offset=[0,8]')
                                ui.menu_item('Last Month', on_click=lambda: self.set_range('1M'))
                                ui.menu_item('Last 3 Months', on_click=lambda: self.set_range('3M'))
                                ui.menu_item('Last Year', on_click=lambda: self.set_range('1Y'))
                                ui.menu_item('All', on_click=lambda: self.set_range('ALL'))
                                ui.separator()
                                ui.menu_item('Zakres dat…',     on_click=lambda: self.set_range('CUSTOM'))
                        self.custom_row = ui.row().classes('items-center gap-1').style('display:none')
                        with self.custom_row:
                            ui.button('FROM', icon='event', on_click=lambda: self.open_date_picker('From date', 'from')
                                      ).props('flat color=primary').classes('q-mr-sm')
                            ui.button('TO', icon='event', on_click=lambda: self.open_date_picker('To date', 'to')
                                      ).props('flat color=primary').classes('q-mr-sm')

    def render_table(self, rows):
        self.table_card.clear()
        with self.table_card:
     
            with ui.element('div').classes('card-body w-full'):
                cols = [
                    {'name': 'date_disp', 'label': 'Date', 'field': 'date_disp', 'sortable': True, 'align': 'left',
                     'style': 'width:130px;white-space:nowrap;', 'headerStyle': 'white-space:nowrap;'},
                    {'name': 'from_name', 'label': 'From', 'field': 'from_name', 'align': 'left',
                     'style': 'width:140px;white-space:nowrap;', 'headerStyle': 'white-space:nowrap;'},
                    {'name': 'to_name', 'label': 'To', 'field': 'to_name', 'align': 'left',
                     'style': 'max-width:260px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;',
                     'headerStyle': 'white-space:nowrap;'},
                    {'name': 'account', 'label': 'Account', 'field': 'account', 'align': 'left',
                     'style': 'width:120px;white-space:nowrap;', 'headerStyle': 'white-space:nowrap;'},
                    {'name': 'category', 'label': 'Category', 'field': 'category', 'align': 'left',
                     'style': 'width:150px;white-space:nowrap;', 'headerStyle': 'white-space:nowrap;'},
                    {'name': 'method', 'label': 'Method', 'field': 'method', 'align': 'left',
                     'style': 'width:120px;white-space:nowrap;', 'headerStyle': 'white-space:nowrap;'},
                    {'name': 'status', 'label': 'Status', 'field': 'type', 'align': 'left',
                     'style': 'width:110px;white-space:nowrap;', 'headerStyle': 'white-space:nowrap;'},
                    {'name': 'amount_fmt', 'label': 'Amount', 'field': 'amount_fmt', 'align': 'right',
                     'classes': 'num', 'style': 'width:140px;white-space:nowrap;', 'headerStyle': 'white-space:nowrap;'},
                    {'name': 'ccy', 'label': 'CCY', 'field': 'ccy', 'align': 'left',
                     'style': 'width:70px;white-space:nowrap;', 'headerStyle': 'white-space:nowrap;'},
                    {'name': 'detail', 'label': '', 'field': 'id', 'align': 'right',
                     'style': 'width:90px;white-space:nowrap;', 'headerStyle': 'white-space:nowrap;'},
                ]

                tbl = (
                    ui.table(columns=cols, rows=rows, row_key='id')
                    .props('flat separator=horizontal wrap-cells '
                           'rows-per-page-options=[20,40,0] rows-per-page=20 '
                           'table-style="width:100%;table-layout:auto"')
                    .classes('q-mt-none w-full table-modern')
                )

                tbl.add_slot('body-cell-amount_fmt', """
                <q-td :props="props" :class="(props.row.amount >= 0 ? 'text-positive' : 'text-negative') + ' num'">
                  {{ props.row.amount_fmt }}
                </q-td>
                """)

                tbl.add_slot('body-cell-category', """
                <q-td :props="props">
                  <q-chip dense square class="chip-soft" :color="props.row.category_color" text-color="white">
                    {{ props.row.category }}
                  </q-chip>
                </q-td>
                """)
                tbl.add_slot('body-cell-method', """
                <q-td :props="props">
                  <q-chip dense square class="chip-soft" :color="props.row.method_color" text-color="white">
                    {{ props.row.method }}
                  </q-chip>
                </q-td>
                """)
                tbl.add_slot('body-cell-status', """
                <q-td :props="props">
                  <q-chip dense square class="chip-soft"
                          :color="(props.row.type === 'IN' ? 'positive' : 'negative')" text-color="white">
                    {{ props.row.type === 'IN' ? 'Inflow' : 'Outflow' }}
                  </q-chip>
                </q-td>
                """)

                tbl.add_slot('body-cell-detail', """
                    <q-td :props="props" class="text-right">
                    <q-btn flat round dense icon="more_vert" color="primary">
                        <q-menu anchor="bottom right" self="top right">
                        <q-list style="min-width: 160px">
                            <!-- EDIT -->
                            <q-item clickable v-close-popup
                                    @click.stop="$parent.$emit('on_tx_edit', props.row); $q.notify('EMIT ' + props.row.id)">
                            <q-item-section avatar><q-icon name="edit"/></q-item-section>
                            <q-item-section>Edytuj</q-item-section>
                            </q-item>

                            <q-separator />

                            <!-- DELETE -->
                            <q-item clickable v-close-popup
                                    @click.stop="$q.dialog({
                                                title: 'Usuń transakcję',
                                                message: 'Na pewno chcesz usunąć ten wiersz?',
                                                cancel: true, persistent: true
                                                }).onOk(() => $parent.$emit('on_tx_delete', props.row.id))">
                            <q-item-section avatar><q-icon name="delete" color="negative"/></q-item-section>
                            <q-item-section class="text-negative">Usuń</q-item-section>
                            </q-item>
                        </q-list>
                        </q-menu>
                    </q-btn>
                    </q-td>
                    """)
                
                tbl.on('row-dblclick', lambda e: self.on_tx_edit(e.args[1]))
                tbl.on('on_tx_edit', lambda e: self.on_tx_edit(e.args))
                tbl.on('on_tx_delete', lambda e: self.on_tx_delete(e.args))

    def open_date_picker(self, title: str, which: str):
        dlg = ui.dialog()
        with dlg, ui.card().classes('w-[min(360px,95vw)]'):
            ui.label(title).classes('text-base font-semibold q-mb-sm')
            val = self.state[which] or datetime.now().strftime('%Y-%m-%d')
            picker = ui.date(value=val).classes('w-full')
            with ui.row().classes('justify-end gap-2 q-mt-sm'):
                ui.button('Cancel', on_click=dlg.close).props('flat')
                
                def _ok():
                    self.state[which] = picker.value
                    dlg.close()
                    self.render_all()
                ui.button('OK', on_click=_ok).props('unelevated color=primary')
        dlg.open()
        
    def _find_tx(self, tx_id: str):
        """Zwraca (account_name, index_w_liscie, rekord) albo (None, None, None)."""
        for acc, lst in DB.items():
            for i, r in enumerate(lst):
                if r['id'] == tx_id:
                    return acc, i, r
        return None, None, None

    def on_tx_edit(self, e):

        tx_id = e['id']     

        acc, idx, tx = self._find_tx(tx_id)
        if not tx:
            ui.notify('Nie znaleziono transakcji', type='warning')
            return

        dlg = ui.dialog()
        with dlg, ui.card().classes('min-w-[520px] rounded-2xl q-pa-md'):
            ui.label('Edytuj transakcję').classes('text-lg font-medium q-mb-sm')

            sel_account = ui.select(ACCOUNTS, value=acc, label='Konto') \
                            .props('outlined dense options-dense')
            inp_date = ui.input(label='Data (YYYY-MM-DD lub YYYY-MM-DD HH:MM)',
                                value=tx.get('date', '')).classes('w-full')
            inp_payee = ui.input(label='Odbiorca/Nadawca',
                                 value=tx.get('payee', '')).classes('w-full')

            cat_options = sorted(set(self.all_categories() + ([tx.get('category')] if tx.get('category') else [])))
            sel_cat = ui.select(cat_options, value=tx.get('category', ''), label='Kategoria'
                                ).props('outlined dense clearable options-dense')

            sel_method = ui.select(['Karta', 'Przelew', 'Gotówka'],
                                   value=tx.get('method', 'Karta'), label='Metoda'
                                   ).props('outlined dense options-dense')
            sel_ccy = ui.select(['PLN', 'EUR', 'USD'],
                                value=tx.get('ccy', 'PLN'), label='Waluta'
                                ).props('outlined dense options-dense')

            inp_amount = ui.input(label='Kwota', value=str(tx.get('amount', ''))
                                  ).props('type=number step=0.01').classes('w-full')
            inp_note = ui.input(label='Notatka', value=tx.get('note', '')
                                ).props('type=textarea autogrow').classes('w-full')

            with ui.row().classes('justify-end gap-2 q-mt-md'):
                ui.button('Anuluj', on_click=dlg.close).props('flat')
                
                def _save():

                    try:
                        amt = float(str(inp_amount.value).replace(',', '.'))
                    except Exception:
                        ui.notify('Podaj poprawną kwotę', type='warning')
                        return

                    new_tx = {
                        'id': tx['id'],
                        'date': inp_date.value or '',
                        'payee': inp_payee.value or '',
                        'category': sel_cat.value or '',
                        'amount': amt,
                        'ccy': sel_ccy.value or 'PLN',
                        'method': sel_method.value or 'Karta',
                        'type': self.to_type_from_amount(amt),
                        'note': inp_note.value or '',
                    }

                    new_acc = sel_account.value or acc
                    if new_acc == acc:
                        DB[acc][idx] = new_tx
                    else:
                        DB[acc].pop(idx)
                        DB.setdefault(new_acc, []).append(new_tx)

                    ui.notify('Zapisano', type='positive')
                    dlg.close()
                    self.render_all()

                ui.button('Zapisz', on_click=_save).props('unelevated color=primary')

        dlg.open()

    def on_tx_delete(self, tx_id: str):
        logger.info(f"on_tx_delete: {tx_id}")
        acc, idx, tx = self._find_tx(tx_id)
        if not tx:
            ui.notify('Wpis nie istnieje', type='warning')
            return

        DB[acc].pop(idx)
        ui.notify('Usunięto', type='positive')
        self.render_all()
    
    def render_all(self):
        rows = self.load_rows()
        self.render_header(rows)
        self.render_manage()
        self.render_table(rows)


@ui.page('/transactions')
def transactions_page(request: Request):
    
    add_style()
    add_user_style()
    add_table_style()
    Transactions(request)
    
    
