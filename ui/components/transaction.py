from nicegui import ui
import datetime
import uuid
import logging
from typing import Iterable, Callable

from .panel.card import panel
from schemas.wallet import TransactionCreationRow
from utils.utils import fmt_money, parse_date
from utils.money import dec
from imports.parsers import PARSERS
from exceptions import MissingRequiredColumnsError

logger = logging.getLogger(__name__)
       
        
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


def render_create_transaction_dialog(self):
    """
    Modal for creating a single transaction or importing many from bank CSV.

    Returns: open_dialog() callable
    """
    dlg = ui.dialog()

    with dlg:
        with ui.card().style('''
            max-width: 720px;
            padding: 28px 24px;
            border-radius: 24px;
            background: linear-gradient(180deg, #ffffff 0%, #f6f9ff 100%);
            box-shadow: 0 10px 24px rgba(15,23,42,.06);
            border: 1px solid rgba(2,6,23,.06);
        '''):
            ui.icon('paid').style('font-size:44px;color:#16a34a;background:#e6ffed;padding:16px;border-radius:50%')
            ui.label('Add transaction / Import CSV').classes('text-h5 text-weight-medium q-mb-xs text-center')
            ui.label('Enter transaction details or import from your bank statement.') \
                .classes('text-body2 text-grey-8 q-mb-md')

            with ui.tabs().classes('w-full') as tabs:
                t_manual = ui.tab('Manual')
                t_import = ui.tab('Import CSV')
            with ui.tab_panels(tabs, value=t_manual).classes('w-full'):
                # --- Manual tab -------------------------------------------------
                with ui.tab_panel(t_manual):
                    with ui.column().classes('w-full q-gutter-sm'):
                        
                        accounts = {a.id: a.name for w in (self.wallets or []) for a in w.accounts}
                        account_select = ui.select(accounts, label='Account *').props('filled clearable use-input') \
                            .style('width:100%')

                        amount_input = ui.input(label='Kwota *', placeholder='e.g., 123.45') \
                            .props('filled clearable input-class=text-center maxlength=32') \
                            .style('width:100%')

                        description_input = ui.input(label='Description').props('filled clearable counter maxlength=255') \
                            .style('width:100%')
                            
                        balance_input = ui.input(label='Saldo po transakcji', placeholder='e.g., 123.45') \
                            .props('filled clearable input-class=text-center maxlength=32') \
                            .style('width:100%')
                            
                        date_input = ui.input('Date *').props('filled').style('width:100%')
                            
                        cal_dlg = ui.dialog()
                        with cal_dlg, ui.card().classes('w-[min(360px,95vw)]'):
                            ui.label('Select date').classes('text-base font-semibold q-mb-sm')
                            val = datetime.datetime.now().strftime('%Y-%m-%d')
                            ui.date().bind_value(date_input).classes('w-full')
                            date_input.value = val
                            with ui.row().classes('justify-end q-gmt-sm'):
                                ui.button('Close', on_click=cal_dlg.close).props('flat')
                                ui.button('OK', on_click=cal_dlg.close).props('unelevated color=primary')

                        with date_input.add_slot('append'):
                            ui.icon('edit_calendar').on('click', cal_dlg.open).classes('cursor-pointer')
                        date_input.on('click', cal_dlg.open)

                        with ui.row().classes('justify-center q-gutter-md q-mt-sm'):
                            ui.button('Cancel').props('no-caps flat').style('min-width:110px;height:44px').on_click(dlg.close)
                            submit_btn = ui.button('Add', icon='add').props('no-caps color=primary') \
                                .style('min-width:140px;height:44px;border-radius:8px')

                    async def do_add():
                        """Validate inputs and create a single transaction."""
                        try:
                            if not account_select.value:
                                ui.notify('Choose account.', color='negative')
                                return

                            if not amount_input.value:
                                ui.notify('Provide amount.', color='negative')
                                return
                            
                            if not balance_input.value:
                                ui.notify('Provide amount.', color='negative')
                                return
                            
                            if not description_input.value:
                                ui.notify('Provide description.', color='negative')
                                return

                            acc_id: uuid.UUID = account_select.value 
                            amount = dec(amount_input.value)
                            balance = dec(balance_input)
                            
                            user_id = self.get_user_id()

                            payload = {
                                'account_id': str(acc_id),
                                'transactions': [{
                                    'created_at': f"{date_input.value}T00:00:00",
                                    'amount': str(amount),
                                    'description': (description_input.value),
                                    'amount_after': str(balance)
                                }]
                            }

                            submit_btn.props('loading')
                            res = await self.wallet_client.create_transaction(user_id, payload)
                            if not res:
                                ui.notify('Failed to create transaction.', color='negative')
                                return

                            ui.notify('Transaction added.', color='positive')
                            dlg.close()

                        except Exception as e:
                            logger.exception('Create transaction error')
                            ui.notify(f'Error: {e}', color='negative')
                        finally:
                            submit_btn.props(remove='loading')

                    submit_btn.on_click(do_add)
                    
                with ui.tab_panel(t_import):
                    with ui.column().classes('w-full q-gutter-sm'):

                        account_select2 = ui.select(accounts, label='Account for imported rows *') \
                            .props('filled clearable use-input').style('width:100%')

                        bank_map = {p.name: p.name for p in PARSERS}
                        bank_select = ui.select(bank_map, value=PARSERS[0].name, label='Bank format') \
                            .props('filled clearable use-input').style('width:100%')

                        rows_buffer: list[TransactionCreationRow] = []  

                        def render_preview(rows: list[TransactionCreationRow]):
                            open_import_preview_dialog(rows, on_ok=None)

                        async def on_upload(e):
                            """Handle file upload event: parse file to rows_buffer."""
                            if not account_select2.value:
                                upload.run_method("reset")
                                ui.notify('File received but no account selected. Pick an account, then click "Process file".',
                                          color='warning')
                                return
                            file_bytes = e.content  
                            rows_buffer.clear()

                            chosen = next((p for p in PARSERS if p.name == bank_select.value), PARSERS[0])
                            try:
                                if chosen.kind == 'PDF':
                                    parsed = chosen.parse(file_bytes)
                                else:
                                    reader, headers = chosen.open_mb_dictreader_from_bytes(file_bytes)

                                    parsed = chosen.parse(reader)
                                    
                            except MissingRequiredColumnsError as e:
                                ui.notify(f"{e}", color='negative')
                                upload.run_method('reset')
                                return

                            except Exception:
                                upload.run_method("reset")
                                logger.exception('Import parse error')
                                ui.notify('Parse error. Check selected format/file.', color='negative')
                                return

                            rows_buffer.extend(parsed)
                            render_preview(rows_buffer)
                            
                        upload = ui.upload(label=PARSERS[0].upload_label, on_upload=on_upload,
                                           on_rejected=lambda: ui.notify('This file type is not allowed here. Please chose correct format', color='negative')) \
                            .props('accept=.csv max-files=1') \
                            .style('width:100%')
                            
                        def on_format_change():
                            chosen = next((p for p in PARSERS if p.name == bank_select.value), PARSERS[0])
                            upload.label = chosen.upload_label
                            upload.props(remove='accept')
                            upload.props(f"accept={chosen.accept}")
                            
                            if chosen.name == "IngMakler CSV":
                                open_instructions_dialog()

                        bank_select.on('update:model-value', lambda: on_format_change())

                        with ui.row().classes('justify-center q-gutter-md q-mt-sm'):
                            ui.button('Cancel').props('no-caps flat').style('min-width:110px;height:44px').on_click(dlg.close)
                            import_btn = ui.button('Import', icon='file_upload').props('no-caps color=primary') \
                                .style('min-width:160px;height:44px;border-radius:8px')

                    async def do_import():
                        if not rows_buffer:
                            """Send parsed rows to the service."""
                            ui.notify('No rows to import.', color='warning')
                            return
                        import_btn.props('loading')

                        try:
                            user_id = self.get_user_id()
                            
                            payload = {
                                'account_id': str(account_select2.value),
                                'transactions': [r.model_dump(mode="json") for r in rows_buffer]

                            }

                            logger.info("Importing transactions")
                            res = await self.wallet_client.create_transaction(user_id, payload)
                            
                            if not res:
                                ui.notify('Import failed: empty response', color='negative')
                                return
                        
                            ui.notify('Imported transactions', color='positive')

                            dlg.close()

                        except Exception:
                            ui.notify('{errors} rows failed', color='warning')
                            
                        finally:
                            import_btn.props(remove='loading')

                    import_btn.on_click(do_import)

    def open_dialog():
        dlg.open()

    return open_dialog


def open_import_preview_dialog(
    rows: Iterable[TransactionCreationRow],
    on_ok: Callable[[], None] | None = None,
) -> None:
    
    """
    Show a modal with a table preview of parsed transaction rows.

    Args:
        rows: Iterable of parsed `TransactionCreationRow` items to preview.
        on_ok: Optional callback executed after the user confirms (clicks OK).

    Returns:
        None. Opens a NiceGUI dialog immediately.
    """

    data = []
    for i, r in enumerate(rows):
        data.append({
            "__idx__": i,
            "date": r.date,
            "description": r.description or "",
            "amount": r.amount,
            "amount_after": r.amount_after,
            
        })

    columns = [
        {"name": "date",         "label": "Data",           "field": "date",         "align": "left",  "sortable": True},
        {"name": "description",  "label": "Opis transakcji","field": "description",  "align": "left"},
        {"name": "amount",       "label": "Kwota",          "field": "amount",       "align": "right"},
        {"name": "amount_after", "label": "Saldo po",       "field": "amount_after", "align": "right"},
        
    ]

    dlg = ui.dialog()

    with dlg:
        with ui.card().style('''
            max-width: 1200px;
            width: 96vw;
            border-radius: 24px;
            background: #ffffff;
            box-shadow: 0 10px 24px rgba(15,23,42,.06);
            border: 1px solid rgba(2,6,23,.06);
            padding: 0;
        '''):
            with ui.element('div').style('''
                width:100%;
                display:flex; align-items:center; gap:14px;
                padding:16px 20px;
                border-top-left-radius:24px; border-top-right-radius:24px;
                background: linear-gradient(180deg, #eff6ff 0%, #ffffff 80%);
                border-bottom: 1px solid rgba(2,6,23,.06);
            '''):
                ui.icon('table_view').style('''
                    font-size: 26px; color:#2563eb;
                    background:#e0ecff; padding:10px; border-radius:12px;
                    box-shadow: 0 4px 10px rgba(37,99,235,.15);
                ''')
                with ui.column().classes('q-gutter-none').style('flex:1'):
                    ui.label('Podgląd importu').style('font-size:18px; font-weight:600; color:#0f172a;')
                    ui.label('Sprawdź dane w tabeli poniżej, a następnie zatwierdź.'
                             ).style('font-size:13px; color:#64748b;')
                ui.badge(f'{len(data)} wierszy').props('color=primary').style('''
                    font-weight:600; background:#2563eb; color:white;
                    padding:6px 10px; border-radius:9999px;
                ''')

            with ui.element('div').style('padding: 10px 14px 0 14px; width:100%;'):
                with ui.element('div').style('width: 98%; margin: 0 auto;'):
                    ui.table(
                        columns=columns,
                        rows=data,
                        row_key="__idx__",
                    ).props(
                        'flat bordered dense wrap-cells virtual-scroll '
                        'rows-per-page-options="[10,25,50,0]"'
                    ).style('height: 60vh; width:100%;')

            ui.separator().classes('q-mt-sm')
            with ui.row().classes('justify-end q-gutter-sm q-mt-sm').style('width:100%; padding: 8px 16px 16px;'):
                ui.button('Anuluj').props('flat no-caps').on_click(dlg.close)

                def _ok():
                    dlg.close()
                    if on_ok:
                        on_ok()

                ui.button('OK').props('color=primary no-caps').on_click(_ok)

    dlg.open()
    
    
def open_instructions_dialog():
    """
    Show a short instruction modal for preparing the input file before import.

    Returns:
        None. Opens a NiceGUI dialog immediately.
    """
    dlg = ui.dialog()

    with dlg:
        with ui.card().style('''
            max-width: 720px; width: 92vw;
            border-radius: 16px;
            background: #f8fafc;     
            border: 1px solid #e2e8f0;    
            box-shadow: 0 10px 24px rgba(15,23,42,.08);
            padding: 16px;                
        '''):

            ui.label('Instrukcja przygotowania pliku').classes('text-h6 q-mb-sm')

            html_msg = """
            <div style="line-height:1.5">
            <div><b>1.</b> Proszę usunąć kolumnę numerującą wiersze</div>
            <div><b>2.</b> Proszę usunąć pierwszy i ostatni wiersz</div>
            <div><b>3.</b> Proszę nadać nazwy kolumn w pierwszym wierszu kolejno:</div>
            <div style="margin-left:14px">a) Data transakcji</div>
            <div style="margin-left:14px">b) Typ transakcji</div>
            <div style="margin-left:14px">c) Opis transakcji</div>
            <div style="margin-left:14px">d) Kwota transakcji</div>
            <div style="margin-left:14px">e) Saldo po operacji</div>
            <div style="margin-left:14px">f) Waluta</div>
            <div><b>4.</b> Proszę sprawdzić kolejność transakcji</div>
            </div>
            """
            ui.html(html_msg)

            with ui.row().classes('justify-end q-gutter-sm q-mt-md'):
                ui.button('Zamknij').props('color=primary no-caps').on_click(dlg.close)

    dlg.open()
