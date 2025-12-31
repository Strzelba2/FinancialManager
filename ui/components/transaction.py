from nicegui import ui
import datetime
import uuid
import logging
from typing import Iterable, Callable, List, Optional, Any, Dict

from .panel.card import panel
from .date import attach_date_time_popups
from schemas.wallet import (
    TransactionCreationRow, WalletListItem, CapitalGainKind,
    BrokerageEventImportRow
)
from .brokerage_event import render_brokerage_event_form

from services.wallet import make_transaction_rows
from utils.utils import parse_date
from utils.money import dec
from imports.parsers import PARSERS
from exceptions import MissingRequiredColumnsError

logger = logging.getLogger(__name__)


async def render_manual_transaction_form(
    self: Any,                      
    container: Any,                 
    accounts: Dict[uuid.UUID, str],  
    on_success: Callable[[], Any],   
    on_cancel: Optional[Callable[[], Any]] = None,
    default_account_id: Optional[uuid.UUID] = None,
) -> None:
    """
    Render a manual transaction creation form into a given NiceGUI container.

    The form collects:
    - account (required)
    - amount (required)
    - description (required in current validation)
    - transaction type / capital gain kind (required; "TRANSACTION" maps to None in payload)
    - balance after transaction (required)
    - date (required)

    On submit, it builds a payload compatible with `self.wallet_client.create_transaction(...)`
    and calls `on_success()` after a successful API response.

    Args:
        self:
            Page/controller instance that provides:
            - self.get_user_id() -> uuid.UUID (or string convertible)
            - self.wallet_client.create_transaction(user_id, payload) -> Awaitable[truthy/falsey]
        container:
            NiceGUI container element where the form is rendered (must support `.clear()` and context manager usage).
        accounts:
            Mapping of account_id -> account label.
        on_success:
            Async callback invoked after successful transaction creation.
        on_cancel:
            Optional callback invoked when the user clicks Cancel.
        default_account_id:
            If provided and present in `accounts`, preselect it in the account dropdown.
    """

    logger.info("render_manual_transaction_form: render")
    container.clear()

    with container:
        account_select = (
            ui.select(accounts, label="Account *")
            .props("filled clearable use-input")
            .style("width:100%")
        )
        if default_account_id and default_account_id in accounts:
            account_select.value = default_account_id

        amount_input = (
            ui.input(label="Kwota *", placeholder="e.g., 123.45")
            .props("filled clearable input-class=text-center maxlength=32")
            .style("width:100%")
        )

        description_input = (
            ui.input(label="Description")
            .props("filled clearable counter maxlength=255")
            .style("width:100%")
        )

        capital_gain_kind = {c.name: c.value for c in CapitalGainKind}
        capital_select = (
            ui.select(capital_gain_kind, value="TRANSACTION", label="Typ *")
            .props("filled clearable use-input")
            .style("width:100%")
        )

        balance_input = (
            ui.input(label="Saldo po transakcji", placeholder="e.g., 123.45")
            .props("filled clearable input-class=text-center maxlength=32")
            .style("width:100%")
        )

        date_input = ui.input("Date *").props("filled").style("width:100%")
        attach_date_time_popups(date_input)

        with ui.row().classes("justify-center q-gutter-md q-mt-sm"):
            if on_cancel:
                ui.button("Cancel").props("no-caps flat").style("min-width:110px;height:44px").on_click(on_cancel)

            submit_btn = (
                ui.button("Add", icon="add")
                .props("no-caps color=primary")
                .style("min-width:140px;height:44px;border-radius:8px")
            )

    async def do_add() -> None:
        """Handle form submission: validate input, call API, notify user, then run on_success()."""
        logger.info("render_manual_transaction_form: submit clicked")
        try:
            if not account_select.value:
                ui.notify("Choose account.", color="negative")
                logger.warning("do_add: account not selected")
                return

            if not amount_input.value:
                ui.notify("Provide amount.", color="negative")
                logger.warning("do_add: amount not provided")
                return

            if not balance_input.value:
                ui.notify("Provide balance after.", color="negative")
                logger.warning("do_add: balance_after not provided")
                return

            if not description_input.value:
                ui.notify("Provide description.", color="negative")
                logger.warning("do_add: description not provided")
                return

            capital_gain = None if capital_select.value == CapitalGainKind.TRANSACTION.name else capital_select.value

            acc_id: uuid.UUID = account_select.value
            amount = dec(amount_input.value)
            balance = dec(balance_input.value)

            user_id = self.get_user_id()

            payload = {
                "account_id": str(acc_id),
                "transactions": [
                    {
                        "date": f"{date_input.value}",
                        "amount": str(amount),
                        "description": description_input.value,
                        "amount_after": str(balance),
                        "capital_gain_kind": capital_gain,
                    }
                ],
            }

            submit_btn.props("loading")
            res = await self.wallet_client.create_transaction(user_id, payload)
            if not res:
                logger.error("do_add: wallet_client.create_transaction returned falsy result")
                ui.notify("Failed to create transaction.", color="negative")
                return

            logger.info("do_add: transaction created successfully")
            ui.notify("Transaction added.", color="positive")
            await on_success()

        except Exception as e:
            logger.exception("Create transaction error")
            ui.notify(f"Error: {e}", color="negative")
        finally:
            submit_btn.props(remove="loading")

    submit_btn.on_click(do_add)


def render_lack_transactions():
    """
    Render an information placeholder when there are no transactions to display.

    The layout:
    - A centered row containing a column.
    - An icon (receipt) at the top.
    - A main label: "Brak transakcji do wyświetlania".
    - A secondary label: "Dodaj transakcje, aby je wyświetlić."

    This function only builds UI components; it does not return any data.
    """
    logger.info("render_lack_transactions: rendering 'no transactions' placeholder")
    with ui.row().classes('items-center text-grey-7 justify-center w-full').style('padding:10px 0;'):
        with ui.column().classes('items-center justify-center q-gutter-sm'):
            ui.icon('sym_o_receipt_long').classes('text-h4')
            ui.label('Brak transakcji do wyświetlania')\
                .classes('text-body2 q-mt-none q-mb-none')\
                .style('line-height:1.2; margin:0;')

            ui.label('Dodaj transakcje, aby je wyświetlić.')\
                .classes('text-caption text-grey-6 q-mt-none q-mb-none')\
                .style('line-height:1.2; margin:0;')
       
        
def transactions_table_card(
    rows,
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
    wallets: List[WalletListItem],
    title: str = 'Ostatnie transakcje (rachunek depozytowy)',
    top: int = 5,
    account_type: str = "CURRENT",
    currency: str = "PLN",
    rates: Optional[Dict[str, Any]] = None, 
) -> None:
    """
    Render a clickable card with a small table of recent cash transactions
    and an expanded dialog showing a full table.

    - The card itself shows up to `top` transactions.
    - Clicking the card opens a dialog:
        * If there are transactions, shows a full table (with balance & currency).
        * If not, shows a "no transactions" placeholder.

    Args:
        wallets: List of wallet items containing transaction data.
        title: Title shown on the card and dialog.
        top: Number of most recent transactions to show in the compact view.
        account_type: Account type filter (e.g. "CURRENT", "DEPOSIT").
        currency: Currency filter (e.g. "PLN").
        rates: Optional FX rates or helper mapping used by `make_transaction_rows`.
    """
    logger.info(
        "cash_transactions_table_card: rendering card "
        f"wallets={len(wallets)}, title={title!r}, top={top}, "
        f"account_type={account_type!r}, currency={currency!r}, "
        f"rates_provided={rates is not None}"
    )
    top5 = make_transaction_rows(wallets, n=top, account_type=account_type, currency=currency, rates=rates)

    logger.debug(
        f"cash_transactions_table_card: top5 rows computed -> {len(top5)} rows"
    )

    all_sorted = make_transaction_rows(wallets, n=top, account_type=account_type, 
                                       all_last=True, description_lenght=70, currency=currency, rates=rates)

    logger.debug(
        "cash_transactions_table_card: all_sorted rows computed -> "
        f"{len(all_sorted)} rows"
    )
    
    cols_compact = [
        {'name': 'date_transaction', 'label': 'Data', 'field': 'date_transaction', 'align': 'left', 'style': 'width:110px',
         'headerStyle': 'font-weight:700'},
        {'name': 'description', 'label': 'Opis', 'field': 'description', 'align': 'left', 'headerStyle': 'font-weight:700'},
        {'name': 'account_name', 'label': 'Konto', 'field': 'account_name', 'align': 'left', 'headerStyle': 'font-weight:700'},
        {'name': 'amount', 'label': 'Kwota', 'field': 'amount', 'align': 'right', 'classes': 'num',
         'style': 'width:140px', 'headerStyle': 'font-weight:700'},
    ]
    cols_full = cols_compact + [
        {'name': 'balance_after', 'label': 'Po transakcji', 'field': 'balance_after', 'align': 'left', 'style': 'width:92px',
         'headerStyle': 'font-weight:700'},
        {'name': 'currency', 'label': 'Waluta', 'field': 'currency', 'align': 'left', 'style': 'width:92px',
         'headerStyle': 'font-weight:700'},
    ]

    dlg = ui.dialog()
    if all_sorted:
        dlg.props('maximized')
        
    card_w = '60vw' if all_sorted else '520px'
    card_max_h = '70vh' if all_sorted else 'auto'
        
    with dlg, ui.card().classes().style(f'width:{card_w}; max-height:{card_max_h}h'):
        ui.label(title).classes('text-base font-semibold q-mb-sm')
        if all_sorted:
            logger.info("cash_transactions_table_card: rendering full transactions table in dialog")
            full_tbl = ui.table(columns=cols_full, rows=[r.model_dump() for r in all_sorted], row_key='id') \
                .props('flat dense separator=horizontal rows-per-page-options=[10,25,50,0]') \
                .classes('q-mt-none w-full')

            full_tbl.add_slot('body-cell-amount', """
            <q-td :props="props" :class="(props.row.amount >= 0 ? 'text-positive' : 'text-negative') + ' num'">
            {{ props.row.amount }}
            </q-td>
            """)
        else:
            logger.info(
                "cash_transactions_table_card: no transactions for dialog -> rendering placeholder"
            )
            render_lack_transactions()

        with ui.row().classes('q-pa-md items-center justify-end w-full'):
            ui.button('Zamknij', on_click=dlg.close)

    with panel() as card:
        card.classes('w-full max-w-none cursor-pointer p-0').style('width:100%')
        card.on('click', lambda e: dlg.open())
        logger.debug("cash_transactions_table_card: card click bound to open dialog")

        if top5:
            logger.info(
                "cash_transactions_table_card: rendering compact table with "
                f"{len(top5)} rows"
            )
            ui.label(title).classes('text-sm font-semibold').style('padding:6px 12px 2px 12px')
            with ui.row().classes('q-pa-md items-center justify-end w-full'):
                mini_tbl = (ui.table(columns=cols_compact, rows=[r.model_dump() for r in top5], row_key='id')
                            .props('flat dense separator=horizontal hide-bottom hide-pagination rows-per-page-options=[5]')
                            .classes('q-mt-none w-full')
                            .style('margin:0;padding:0')
                            )

                mini_tbl.add_slot('body-cell-amount', """
                <q-td :props="props" :class="(props.row.amount >= 0 ? 'text-positive' : 'text-negative') + ' num'">
                {{ props.row.amount}}
                </q-td>
                """)
        else:
            logger.info(
                "cash_transactions_table_card: no top transactions -> rendering header + placeholder"
            )
            with ui.row().classes(
                'items-center justify-between w-full q-pa-md'
            ).style('background:linear-gradient(180deg,#fafafa, #ffffff);'):
                ui.label(title).classes('text-subtitle2 text-weight-medium text-8')
                ui.icon('sym_o_open_in_new').classes('text-grey-5')
            render_lack_transactions()


def render_create_transaction_dialog(self):
    """
    Create and configure the 'Add transaction / Import CSV / Maklerska' modal dialog.

    The dialog contains three tabs:
    - Manual: create a single cash transaction.
    - Import CSV: import multiple transactions or brokerage events from a bank file.
    - Maklerska: manually create a single brokerage event.

    Returns:
        A callable `open_dialog()` which:
        - refreshes accounts from `self.wallets`,
        - clears all tab bodies,
        - populates the active tab,
        - opens the dialog.
    """
    logger.info("render_create_transaction_dialog: initializing dialog")
    dlg = ui.dialog()
    
    async def fill_manual():
        accounts = self.accounts 
        
        async def _after():
            dlg.close()

        await render_manual_transaction_form(
            self=self,
            container=self.manual_body,
            accounts=accounts,
            on_success=_after,
            on_cancel=dlg.close,
        )
        
    def fill_import():
        """
        Build and render the 'Import CSV' tab content for importing transactions/brokerage events.
        """
        logger.info("render_create_transaction_dialog.fill_import: building import tab")
        self.import_body.clear()
        with self.import_body:
            account_select2 = (ui.select(self.accounts, label='Account for imported rows *')
                               .props('filled clearable use-input').style('width:100%')
                               )

            bank_map = {p.name: p.name for p in PARSERS}
            bank_select = (ui.select(bank_map, value=PARSERS[0].name, label='Bank format')
                           .props('filled clearable use-input').style('width:100%')
                           )

            rows_buffer: list[TransactionCreationRow] = []  
            brokerage_rows_buffer: list[BrokerageEventImportRow] = []
            
            mode_slot = ui.element('div')
            brokerage_acc_slot = ui.element('div').style('width:100%')

            self.import_mode = 'transactions'
            self.brokerage_import_account = None

            def render_preview(rows: list[TransactionCreationRow]):
                """
                Open preview dialog for imported cash transactions.
                """
                logger.info(
                    f"render_preview: opening preview for {len(rows)} transaction rows"
                )
                open_import_preview_dialog(rows, on_ok=None)

            async def on_upload(e):
                """
                Handle file upload event: validate account / brokerage selection,
                parse file using chosen parser and populate buffers and preview.
                """
                logger.info("on_upload: file upload received in Import CSV tab")
                if not account_select2.value and self.import_mode == "transactions":
                    upload.run_method("reset")
                    ui.notify('File received but no account selected. Pick an account, then click "Process file".',
                              color='warning')
                    logger.warning("on_upload: account not selected for transactions import")
                    return
                
                if self.import_mode == "brokerage_events":
                    if not self.brokerage_import_account or not self.brokerage_import_account.value:
                        upload.run_method("reset")
                        ui.notify(
                            'File received but no brokerage account selected.',
                            color='warning',
                        )
                        logger.warning(
                            "on_upload: brokerage account not selected for brokerage_events import"
                        )
                        return
                
                file_bytes = e.content  
                rows_buffer.clear()
                brokerage_rows_buffer.clear()

                chosen = next((p for p in PARSERS if p.name == bank_select.value), PARSERS[0])
                try:
                    if chosen.kind == 'PDF':
                        parsed = chosen.parse(file_bytes)
                    else:
                        reader, headers = chosen.open_mb_dictreader_from_bytes(file_bytes)

                        if getattr(chosen, "supports_brokerage_events", False) and self.import_mode == "brokerage_events":
                            parsed_events: list[BrokerageEventImportRow] = await chosen.parse_brokerage_events(
                                reader,
                                self.stock_client,
                            )
                            brokerage_rows_buffer.extend(parsed_events)
                            open_import_preview_dialog_brokerage(brokerage_rows_buffer, on_ok=None)
                        else:
                            parsed = chosen.parse(reader)
                            rows_buffer.extend(parsed)
                            logger.info(
                                f"on_upload: parsed {len(rows_buffer)} transaction rows"
                            )
                            render_preview(rows_buffer)

                except MissingRequiredColumnsError as e:
                    logger.warning(f"on_upload: MissingRequiredColumnsError: {e}")
                    ui.notify(f"{e}", color='negative')
                    upload.run_method('reset')
                    return
                except Exception:
                    upload.run_method("reset")
                    logger.exception('Import parse error')
                    ui.notify('Parse error. Check selected format/file.', color='negative')
                    return
                
            upload = (ui.upload(
                                label=PARSERS[0].upload_label, 
                                on_upload=on_upload,
                                on_rejected=lambda: ui.notify(
                                    'This file type is not allowed here. Please chose correct format', 
                                    color='negative')
                                )
                        .props('accept=.csv max-files=1')
                        .style('width:100%')
                      )
                
            def on_format_change():
                """
                Update upload configuration and import mode when bank format changes.
                """
                chosen = next((p for p in PARSERS if p.name == bank_select.value), PARSERS[0])
                upload.label = chosen.upload_label
                upload.props(remove='accept')
                upload.props(f"accept={chosen.accept}")
                
                if chosen.name == "IngMakler CSV":
                    logger.info("on_format_change: opening ING Makler instructions dialog")
                    open_instructions_dialog()
                    
                mode_slot.clear()
                brokerage_acc_slot.clear()
                self.import_mode = "transactions"
                self.brokerage_import_account = None

                if getattr(chosen, "supports_brokerage_events", False):
                    with mode_slot:
                        mode_select = ui.select(
                            {
                                "transactions": "Import as cash transactions",
                                "brokerage_events": "Import as brokerage events",
                            },
                            value="transactions",
                            label="Import mode",
                        ).props('filled clearable use-input').style('width:100%')

                        def ensure_brokerage_select():
                            """
                            Ensure brokerage account selector is shown and populated.
                            """
                            logger.info("ensure_brokerage_select: populating brokerage account select")
                            brokerage_acc_slot.clear()
                            dep_brokerage_accounts = {
                                a.id: a.name
                                for w in (self.wallets or [])
                                for a in (getattr(w, "brokerage_accounts", []) or [])
                            }
                            if not dep_brokerage_accounts:
                                logger.warning(
                                    "ensure_brokerage_select: no brokerage accounts available for user"
                                )
                                with brokerage_acc_slot:
                                    ui.label(
                                        "No brokerage accounts available for this user."
                                    ).classes('text-negative')
                                return

                            with brokerage_acc_slot:
                                self.brokerage_import_account = ui.select(
                                    dep_brokerage_accounts,
                                    label='Brokerage account for events *',
                                ).props('filled clearable use-input').style('width:100%')

                        def on_mode_change():
                            """
                            Handle change between 'transactions' and 'brokerage_events' import modes.
                            """
                            self.import_mode = mode_select.value
                            if self.import_mode == "brokerage_events":
                                ensure_brokerage_select()
                            else:
                                brokerage_acc_slot.clear()
                                self.brokerage_import_account = None

                        mode_select.on('update:model-value', on_mode_change)
                else:
                    logger.info(
                        "on_format_change: chosen format does not support brokerage_events -> transactions only"
                    )
                    self.import_mode = "transactions"

            bank_select.on('update:model-value', lambda: on_format_change())

            with ui.row().classes('justify-center q-gutter-md q-mt-sm'):
                ui.button('Cancel').props('no-caps flat').style('min-width:110px;height:44px').on_click(dlg.close)
                import_btn = (ui.button('Import', icon='file_upload')
                              .props('no-caps color=primary')
                              .style('min-width:160px;height:44px;border-radius:8px')
                              )

        async def do_import():
            """
            Perform import of transactions or brokerage events, depending on `self.import_mode`.
            """
            mode = getattr(self, "import_mode", "transactions")
            
            if mode == "transactions":
                if not rows_buffer:
                    ui.notify('No rows to import.', color='warning')
                    logger.warning("do_import: no transaction rows_buffer to import")
                    return
            else:
                if not brokerage_rows_buffer:
                    ui.notify('No brokerage events to import.', color='warning')
                    logger.warning("do_import: no brokerage_rows_buffer to import")
                    return
                if not self.brokerage_import_account or not self.brokerage_import_account.value:
                    ui.notify('Select brokerage account for events.', color='negative')
                    logger.warning("do_import: brokerage account not selected for events")
                    return
                
            import_btn.props('loading')

            try:
                user_id = self.get_user_id()
                
                if mode == "transactions":
                    payload = {
                        'account_id': str(account_select2.value),
                        'transactions': [r.model_dump(mode="json") for r in rows_buffer],
                    }

                    res, res_color = await self.wallet_client.create_transaction(user_id, payload)
                    if not res:
                        logger.error("do_import: wallet_client.create_transaction returned falsy result")
                        ui.notify('Import failed: empty response', color='negative')
                        return
                    ui.notify(res, color=res_color, close_button='Close', timeout=0)

                else:
                    payload = {
                        "brokerage_account_id": str(self.brokerage_import_account.value),
                        "events": [ev.model_dump(mode="json") for ev in brokerage_rows_buffer],
                    }

                    res = await self.wallet_client.import_brokerage_events(user_id, payload)
                    if not res or res.get("created", 0) == 0:
                        logger.error(
                            "do_import: import_brokerage_events failed or created=0"
                        )
                        ui.notify('Brokerage import failed.', color='negative')
                        return

                    msg = f"Imported {res['created']} events"
                    if res.get("failed"):
                        msg += f", failed: {res['failed']}"
                    ui.notify(msg, color='positive', close_button='Close', timeout=0)

                dlg.close()

            except Exception:
                logger.exception(f"do_import: unexpected error: {e}")
                ui.notify('{errors} rows failed', color='warning')
                
            finally:
                import_btn.props(remove='loading')

        import_btn.on_click(do_import)
    
    async def fill_broker():
        dep_brokerage_accounts = {
            a.id: a.name
            for w in (self.wallets or [])
            for a in (w.brokerage_accounts or [])
        }

        async def _after():
            dlg.close()

        await render_brokerage_event_form(
            self=self,
            container=self.broker_body,
            brokerage_accounts=dep_brokerage_accounts,
            on_success=_after,
        )
        
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

            with ui.tabs().classes('w-full').props('stretch') as tabs:
                ui.tab(name='Manual')
                ui.tab(name='Import CSV')
                ui.tab(name='Maklerska')

            with ui.tab_panels(tabs, value='Manual').classes('w-full'):
                with ui.tab_panel('Manual'):
                    self.manual_body = ui.column().classes('w-full q-gutter-sm')
                with ui.tab_panel('Import CSV'):
                    self.import_body = ui.column().classes('w-full q-gutter-sm')
                with ui.tab_panel('Maklerska'):
                    with ui.element('div').style('max-height: 400px; overflow-y: auto;'):
                        self.broker_body = ui.column().classes('w-full q-gutter-sm')
                        
    def reset_all():
        """
        Clear all tab bodies (Manual, Import CSV, Maklerska) when dialog hides or reopens.
        """
        logger.info("reset_all: clearing all tab contents")
        if getattr(self, "manual_body", None):
            self.manual_body.clear()
        if getattr(self, "import_body", None):
            self.import_body.clear()
        if getattr(self, "broker_body", None):
            self.broker_body.clear()

    dlg.on('hide', lambda _: reset_all())
    
    def fill_active_panel():
        """
        Fill the currently active tab with its content.
        """
        active = tabs.value
        logger.info(f"fill_active_panel: active tab={active!r}")
        if active == 'Manual':
            ui.timer(0.01, fill_manual, once=True)
        elif active == 'Import CSV':
            fill_import()
        elif active == 'Maklerska':
            ui.timer(0.01, fill_broker, once=True)

    def on_tab_change():
        """
        Handle tab change event and rebuild the active tab content.
        """
        logger.info("on_tab_change: tab changed, re-filling active panel")
        fill_active_panel()
        
    tabs.on('update:model-value', lambda *_: on_tab_change())
    
    def open_dialog():
        """
        Refresh accounts, reset all tab contents, fill active tab and open the dialog.
        """
        self.accounts = {a.id: a.name for w in (self.wallets or []) for a in w.accounts}
        reset_all()
        fill_active_panel()
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
        {"name": "description",  "label": "Opis transakcji", "field": "description",  "align": "left"},
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
    
    
def open_import_preview_dialog_brokerage(
    rows: Iterable[BrokerageEventImportRow],
    on_ok: Callable[[], None] | None = None,
) -> None:
    """
    Open a modal dialog with a preview table of brokerage events to be imported.

    Each row shows:
        - trade_at
        - instrument_symbol
        - kind
        - quantity
        - price
        - currency

    Args:
        rows: Iterable of `BrokerageEventImportRow` objects to display.
        on_ok: Optional callback executed after user clicks "OK" and the dialog closes.

    Returns:
        None. The NiceGUI dialog is shown immediately.
    """

    data = []
    for i, r in enumerate(rows):
        data.append({
            "__idx__": i,
            "trade_at": r.trade_at,
            "instrument_symbol": r.instrument_symbol,
            "kind": r.kind.value if hasattr(r.kind, "value") else r.kind,
            "quantity": r.quantity,
            "price": r.price,
            "currency": r.currency.value if hasattr(r.currency, "value") else r.currency,
        })

    columns = [
        {"name": "trade_at",          "label": "Data",        "field": "trade_at",          "align": "left",  "sortable": True},
        {"name": "instrument_symbol", "label": "Symbol",      "field": "instrument_symbol", "align": "left",  "sortable": True},
        {"name": "kind",             "label": "Typ",         "field": "kind",              "align": "left"},
        {"name": "quantity",         "label": "Ilość",       "field": "quantity",          "align": "right"},
        {"name": "price",            "label": "Cena",        "field": "price",             "align": "right"},
        {"name": "currency",         "label": "Waluta",      "field": "currency",          "align": "center"},
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
                ui.icon('show_chart').style('''
                    font-size: 26px; color:#2563eb;
                    background:#e0ecff; padding:10px; border-radius:12px;
                    box-shadow: 0 4px 10px rgba(37,99,235,.15);
                ''')
                with ui.column().classes('q-gutter-none').style('flex:1'):
                    ui.label('Podgląd zdarzeń maklerskich').style('font-size:18px; font-weight:600; color:#0f172a;')
                    ui.label('Sprawdź dane zdarzeń przed importem.'
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
            with ui.row().classes('justify-end q-gutter-sm q-mt-sm').style(
                'width:100%; padding: 8px 16px 16px;'
            ):
                ui.button('Anuluj').props('flat no-caps').on_click(dlg.close)

                def _ok():
                    dlg.close()
                    if on_ok:
                        on_ok()

                ui.button('OK').props('color=primary no-caps').on_click(_ok)

    logger.debug("open_import_preview_dialog_brokerage: opening dialog")
    dlg.open()
    
    
def open_instructions_dialog():
    """
    Show a short instruction modal for preparing the input file before import.

    The dialog explains:
    - Which row/column to remove.
    - How to name the columns.
    - To verify transaction order before upload.

    Returns:
        None. Opens a NiceGUI dialog immediately.
    """
    logger.info("open_instructions_dialog: opening instructions modal")
    
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
