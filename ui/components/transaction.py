from nicegui import ui
import datetime

from .panel.card import panel
from utils.utils import fmt_money, parse_date
       
        
def transactions_table_card(
    rows,
    *,
    title: str = 'Ostatnie transakcje maklerskie',
    top: int = 5,
    sort_by: str = 'date',       
    reverse: bool = True,      
):

    def fmt_num(v, places=2):
        return f"{float(v or 0):,.{places}f}".replace(',', ' ').replace('nan', '0')

    def fmt_amt(v, ccy):
        return f"{fmt_num(v, 2)} {ccy or ''}".strip()

    def cashflow(type_, value):
        if type_ in ('BUY', 'FEE'):
            return -(abs(value or 0.0))
        return (abs(value or 0.0))

    prepared = []
    for r in rows:
        ccy = r.get('ccy', 'PLN')
        qty = float(r.get('qty') or 0.0)
        price = float(r.get('price') or 0.0)
        value = float(r.get('value') if r.get('value') is not None else qty * price)
        typ = (r.get('type') or '').upper()
        cf = cashflow(typ, value)

        d = r.get('date')
        ts = r.get('ts')
        dt = datetime.datetime.fromtimestamp(ts) if ts else parse_date(d)
        date_disp = (
            dt.strftime('%Y-%m-%d %H:%M') if dt and (':' in str(d)) else
            dt.strftime('%Y-%m-%d') if dt else
            (str(d) or '')
        )

        prepared.append({
            'date': date_disp,
            'ts': int(dt.timestamp()) if dt else (ts or 0),
            'sym': r.get('sym', ''),
            'name': r.get('name', ''),
            'type': typ, 
            'qty': qty,
            'price': price,
            'value': value,
            'cf': cf,
            'qty_fmt': fmt_num(qty, 4).rstrip('0').rstrip('.') if qty else '0',
            'price_fmt': fmt_amt(price, ccy),
            'value_fmt': fmt_amt(value, ccy),
            'cf_fmt': fmt_amt(cf, ccy),
            'ccy': ccy,
            'account': r.get('account', ''),
            'note': r.get('note', ''),
        })

    key_map = {
        'date': lambda r: r.get('ts', 0),
        'cf': lambda r: float(r.get('cf') or 0),
        'value': lambda r: float(r.get('value') or 0),
        'price': lambda r: float(r.get('price') or 0),
        'qty': lambda r: float(r.get('qty') or 0),
        'sym': lambda r: str(r.get('sym', '')).lower(),
    }
    prepared = sorted(prepared, key=key_map.get(sort_by, key_map['date']), reverse=reverse)

    cols_compact = [
        {'name': 'date', 'label': 'Data', 'field': 'date', 'align': 'left', 'style': 'width:110px',
         'headerStyle': 'font-weight:700'},
        {'name': 'sym', 'label': 'Ticker', 'field': 'sym', 'align': 'left', 'headerStyle': 'font-weight:700'},
        {'name': 'type', 'label': 'Typ', 'field': 'type', 'align': 'left', 'style': 'width:92px',
         'headerStyle': 'font-weight:700'},
        {'name': 'qty_fmt', 'label': 'Ilość', 'field': 'qty_fmt', 'align': 'right', 'classes': 'num',
         'style': 'width:90px', 'headerStyle': 'font-weight:700'},
        {'name': 'price_fmt', 'label': 'Cena', 'field': 'price_fmt', 'align': 'right', 'classes': 'num',
         'style': 'width:120px', 'headerStyle': 'font-weight:700'},
        {'name': 'cf_fmt', 'label': 'Przepływ', 'field': 'cf_fmt', 'align': 'right', 'classes': 'num',
         'style': 'width:140px', 'headerStyle': 'font-weight:700'},
    ]
    cols_full = cols_compact[:]
    cols_full.insert(2, {'name': 'name', 'label': 'Nazwa', 'field': 'name', 'align': 'left', 
                         'headerStyle': 'font-weight:700'})
    cols_full += [
        {'name': 'account', 'label': 'Konto', 'field': 'account', 'align': 'left', 'headerStyle': 'font-weight:700'},
        {'name': 'note', 'label': 'Notatka', 'field': 'note', 'align': 'left', 'headerStyle': 'font-weight:700'},
    ]

    dlg = ui.dialog()
    with dlg, ui.card().classes('w-[min(1200px,96vw)]'):
        ui.label(title).classes('text-base font-semibold q-mb-sm')
        full_tbl = ui.table(columns=cols_full, rows=prepared, row_key='date') \
            .props('flat dense separator=horizontal rows-per-page-options=[10,25,50,0]') \
            .classes('q-mt-none w-full')

        full_tbl.add_slot('body-cell-type', """
        <q-td :props="props">
          <q-badge :color="(props.row.type==='BUY' || props.row.type==='DIV') ? 'positive' : 'negative'"
                   :label="props.row.type" class="q-px-sm"/>
        </q-td>
        """)
        full_tbl.add_slot('body-cell-cf_fmt', """
        <q-td :props="props" :class="props.row.cf<0 ? 'text-negative' : 'text-positive'">
          {{ props.row.cf_fmt }}
        </q-td>
        """)

        ui.button('Zamknij', on_click=dlg.close).classes('q-mt-sm self-end')

    top_rows = prepared[:top]
    with panel() as card:
        card.classes('w-full max-w-none cursor-pointer p-0').style('width:100%')
        card.on('click', lambda e: dlg.open())

        ui.label(title).classes('text-sm font-semibold').style('padding:6px 12px 2px 12px')

        mini_tbl = ui.table(columns=cols_compact, rows=top_rows, row_key='date') \
            .props('flat dense separator=horizontal hide-bottom hide-pagination rows-per-page-options=[5]') \
            .classes('q-mt-none w-full') \
            .style('margin:0;padding:0')

        mini_tbl.add_slot('body-cell-type', """
        <q-td :props="props">
          <q-badge :color="(props.row.type==='BUY' || props.row.type==='DIV') ? 'positive' : 'negative'"
                   :label="props.row.type" class="q-px-sm"/>
        </q-td>
        """)
        mini_tbl.add_slot('body-cell-cf_fmt', """
        <q-td :props="props" :class="props.row.cf<0 ? 'text-negative' : 'text-positive'">
          {{ props.row.cf_fmt }}
        </q-td>
        """)
    
        
def cash_transactions_table_card(
    rows,
    *,
    title: str = 'Ostatnie transakcje (rachunek depozytowy)',
    top: int = 5,
    sort_by: str = 'date',    
    reverse: bool = True,   
    opening_balance: float | None = None,
    default_ccy: str = 'PLN',
):
 
    def to_amount(r):
        """Zwraca kwotę ze znakiem; honoruje 'direction' jeśli kwota bez znaku."""
        amt = r.get('amount', 0)
        try:
            amt = float(amt)
        except Exception:
            amt = 0.0
        direction = (r.get('direction') or '').upper()
        if direction == 'IN' and amt < 0:  
            amt = abs(amt)
        elif direction == 'OUT' and amt > 0:  
            amt = -abs(amt)
        return amt

    base = []
    for r in rows:
        dt = parse_date(r.get('date'))
        ts = int(dt.timestamp()) if dt else 0
        ccy = r.get('ccy') or default_ccy
        amt = to_amount(r)

        base.append({
            'date': (
                dt.strftime('%Y-%m-%d %H:%M')
                if dt and ':' in str(r.get('date', ''))
                else dt.strftime('%Y-%m-%d')
                if dt
                else r.get('date') or ''
            ),
            'ts': ts,
            'payee': r.get('payee', ''),
            'category': r.get('category', ''),
            'method': r.get('method', ''),
            'account': r.get('account', ''),
            'amount': amt,
            'amount_fmt': fmt_money(amt, ccy),
            'balance': r.get('balance', None),
            'ccy': ccy,
            'note': r.get('note', ''),
            'id': r.get('id', ''),
        })

    if opening_balance is not None and not any(r.get('balance') is not None for r in base):
        asc = sorted(base, key=lambda r: r.get('ts', 0))
        running = float(opening_balance)
        for r in asc:
            running += float(r['amount'] or 0)
            r['balance'] = running

        idx = {(r['ts'], r['payee'], r['amount']): r['balance'] for r in asc}
        for r in base:
            r['balance'] = idx.get((r['ts'], r['payee'], r['amount']), r['balance'])

    for r in base:
        r['balance_fmt'] = fmt_money(r['balance'], r['ccy']) if r.get('balance') is not None else ''

    key_map = {
        'date': lambda r: r.get('ts', 0),
        'amount': lambda r: float(r.get('amount') or 0),
        'balance': lambda r: float(r.get('balance') or 0),
        'payee': lambda r: r.get('payee', '').lower(),
        'category': lambda r: r.get('category', '').lower(),
        'method': lambda r: r.get('method', '').lower(),
    }
    prepared = sorted(base, key=key_map.get(sort_by, key_map['date']), reverse=reverse)

    cols_compact = [
        {'name': 'date', 'label': 'Data', 'field': 'date', 'align': 'left', 'style': 'width:110px',
         'headerStyle': 'font-weight:700'},
        {'name': 'payee', 'label': 'Kontrahent', 'field': 'payee', 'align': 'left', 'headerStyle': 'font-weight:700'},
        {'name': 'category', 'label': 'Kategoria', 'field': 'category', 'align': 'left', 'headerStyle': 'font-weight:700'},
        {'name': 'amount_fmt', 'label': 'Kwota', 'field': 'amount_fmt', 'align': 'right', 'classes': 'num',
         'style': 'width:140px', 'headerStyle': 'font-weight:700'},
    ]
    cols_full = cols_compact + [
        {'name': 'method', 'label': 'Metoda', 'field': 'method', 'align': 'left', 'style': 'width:92px',
         'headerStyle': 'font-weight:700'},
        {'name': 'balance_fmt', 'label': 'Saldo', 'field': 'balance_fmt', 'align': 'right', 'classes': 'num',
         'style': 'width:150px', 'headerStyle': 'font-weight:700'},
        {'name': 'account', 'label': 'Konto', 'field': 'account', 'align': 'left', 'headerStyle': 'font-weight:700'},
        {'name': 'note', 'label': 'Notatka', 'field': 'note', 'align': 'left', 'headerStyle': 'font-weight:700'},
        {'name': 'id', 'label': 'ID', 'field': 'id', 'align': 'left', 'style': 'width:120px', 
         'headerStyle': 'font-weight:700'},
    ]

    dlg = ui.dialog()
    dlg.props('maximized') 
    with dlg, ui.card().classes().style('width:60vw; max-height:40vh'):
        ui.label(title).classes('text-base font-semibold q-mb-sm')
        full_tbl = ui.table(columns=cols_full, rows=prepared, row_key='id') \
            .props('flat dense separator=horizontal rows-per-page-options=[10,25,50,0]') \
            .classes('q-mt-none w-full')

        full_tbl.add_slot('body-cell-amount_fmt', """
        <q-td :props="props" :class="(props.row.amount >= 0 ? 'text-positive' : 'text-negative') + ' num'">
          {{ props.row.amount_fmt }}
        </q-td>
        """)

        ui.button('Zamknij', on_click=dlg.close).classes('q-mt-sm self-end')

    top_rows = prepared[:top]
    with panel() as card:
        card.classes('w-full max-w-none cursor-pointer p-0').style('width:100%')
        card.on('click', lambda e: dlg.open())

        ui.label(title).classes('text-sm font-semibold').style('padding:6px 12px 2px 12px')

        mini_tbl = ui.table(columns=cols_compact, rows=top_rows, row_key='id') \
            .props('flat dense separator=horizontal hide-bottom hide-pagination rows-per-page-options=[5]') \
            .classes('q-mt-none w-full') \
            .style('margin:0;padding:0')

        mini_tbl.add_slot('body-cell-amount_fmt', """
        <q-td :props="props" :class="(props.row.amount >= 0 ? 'text-positive' : 'text-negative') + ' num'">
          {{ props.row.amount_fmt }}
        </q-td>
        """)
