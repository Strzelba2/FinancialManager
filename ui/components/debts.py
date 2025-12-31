from nicegui import ui
from decimal import Decimal
from typing import Dict, List, Any
from datetime import datetime
import logging

from utils.utils import to_uuid
from utils.money import dec, change_currency_to, format_pl_amount
from .date import attach_date_time_popups

logger = logging.getLogger(__name__)


def debts_kpi_label(amount_in_view: Decimal, view_ccy: str) -> str:
    """
    Build KPI label string for debts total (negative-style formatting).

    Args:
        amount_in_view: Total debt amount converted to view currency.
        view_ccy: View currency code (e.g. "PLN").

    Returns:
        Formatted KPI label (e.g. "−12 345 PLN" or "0 PLN").
    """
    if amount_in_view == Decimal(0):
        return f"{format_pl_amount(abs(amount_in_view), decimals=0)} {view_ccy}"
    return f"−{format_pl_amount(abs(amount_in_view), decimals=0)} {view_ccy}"


def debts_kpi_subtitle(count: int, avg_rate_pct: Decimal) -> str:
    """
    Build KPI subtitle describing count and average interest rate.

    Args:
        count: Number of debt items.
        avg_rate_pct: Average interest rate (percent).

    Returns:
        Subtitle string in Polish ("Brak zobowiązań" or "3 kredyty · średn. 7.5%").
    """
    if count <= 0:
        return "Brak zobowiązań"
    avg = format_pl_amount(avg_rate_pct, decimals=1)
    label = "kredyt" if count == 1 else "kredyty" if 2 <= count <= 4 else "kredytów"
    return f"{count} {label} · średn. {avg}%"


async def compute_debts_summary_from_api(wallet) -> tuple[Decimal, int, Decimal, Decimal]:
    """
    Compute overall debts summary by querying the API for each selected wallet.

    Returns:
        total_in_view_ccy, count, avg_rate_pct, total_monthly_payment_in_view_ccy
    """
    user_id = to_uuid(wallet.get_user_id())
    view_ccy = wallet.view_currency.value or "PLN"

    total = Decimal("0")
    monthly_total = Decimal("0")
    rate_sum = Decimal("0")
    count = 0

    for w in (wallet.selected_wallet or []):
        rows = await wallet.wallet_client.list_debts(user_id=user_id, wallet_id=to_uuid(w.id))
        for d in rows:
            count += 1
            amt = dec(d.amount)
            ccy = (d.currency.value if hasattr(d.currency, "value") else str(d.currency))
            total += change_currency_to(amt, view_ccy, ccy, wallet.currency_rate)

            mp = dec(getattr(d, "monthly_payment", None))
            monthly_total += change_currency_to(mp, view_ccy, ccy, wallet.currency_rate)

            rate_sum += dec(getattr(d, "interest_rate_pct", None))

    avg_rate = (rate_sum / count) if count else Decimal("0")
    logger.info(
        "compute_debts_summary_from_api: done "
        f"count={count} total={total} avg_rate={avg_rate} monthly_total={monthly_total} view_ccy={view_ccy!r}"
    )
    return total, count, avg_rate, monthly_total


def show_add_debt_dialog(wallet, on_refresh=None) -> None:
    """
    Open dialog to create a debt entry.

    Args:
        wallet: Wallet page/controller providing `wallet_client`, `selected_wallet`, `view_currency`, `get_user_id()`.
        on_refresh: Optional async callback to refresh UI after creating debt.
    """
    dlg = ui.dialog()
    user_id = to_uuid(wallet.get_user_id())

    with dlg:
        with ui.card().style('''
            max-width: 520px;
            padding: 36px 28px 22px;
            border-radius: 24px;
            background: linear-gradient(180deg, #ffffff 0%, #f6f9ff 100%);
            box-shadow: 0 10px 24px rgba(15,23,42,.06);
            border: 1px solid rgba(2,6,23,.06);
        '''):
            with ui.column().classes('items-center justify-center').style('width:100%'):

                ui.icon('sym_o_account_balance').style('''
                    font-size: 44px;
                    color: #ef4444;
                    background: #fee2e2;
                    padding: 18px;
                    border-radius: 50%;
                    margin-bottom: 18px;
                ''')

                ui.label('Dodaj zobowiązanie').classes('text-h5 text-weight-medium q-mb-sm text-center')
                ui.label('Uzupełnij podstawowe dane. Pola z * są wymagane.').classes(
                    'text-body2 text-grey-8 q-mb-lg text-center'
                )

                wallets = wallet.selected_wallet or []
                wallet_options = {str(w.id): getattr(w, "name", str(w.id)) for w in wallets}
                if not wallet_options:
                    ui.notify("Brak wybranego portfela.", color="negative")
                    return

                wallet_sel = ui.select(
                    options=wallet_options,
                    value=list(wallet_options.keys())[0],
                    label='Portfel *',
                ).props('filled').style('width: 100%').classes('q-mb-sm')

                name = ui.input(placeholder='Nazwa *').props('filled clearable').style('width:100%').classes('q-mb-sm')
                lander = ui.input(placeholder='Lender *').props('filled clearable').style('width:100%').classes('q-mb-sm')

                with ui.row().classes('q-gutter-sm w-full'):
                    amount = ui.input(placeholder='Kwota *').props('filled').classes('col')
                    currency = ui.select(
                        options=['PLN', 'USD', 'EUR'],
                        value=wallet.view_currency.value or 'PLN',
                        label='Waluta *',
                    ).props('filled').classes('col')

                with ui.row().classes('q-gutter-sm w-full q-mt-sm'):
                    rate = ui.input(placeholder='Oprocentowanie %').props('filled').classes('col')
                    monthly = ui.input(placeholder='Rata miesięczna').props('filled').classes('col')

                date_input = ui.input('Date *').props('filled').style('width:100%')
                attach_date_time_popups(date_input)

                async def create() -> None:
                    """Validate inputs and create a debt via API."""
                    nm = (name.value or '').strip()
                    ln = (lander.value or '').strip()
                    if not nm or not ln:
                        logger.info("show_add_debt_dialog.create: missing required name/lander")
                        ui.notify('Uzupełnij Nazwa i Lender.', color='negative')
                        return

                    raw_amount = str(amount.value or '').strip().replace(' ', '').replace(',', '.')
                    raw_rate = str(rate.value or '0').strip().replace(' ', '').replace(',', '.')
                    raw_monthly = str(monthly.value or '0').strip().replace(' ', '').replace(',', '.')
                    raw_end = str(date_input.value or '').strip()

                    try:
                        amt = Decimal(raw_amount)
                        rt = Decimal(raw_rate or '0')
                        mp = Decimal(raw_monthly or '0')
                    except Exception:
                        logger.info(
                            "show_add_debt_dialog.create: invalid numbers "
                            f"raw_amount={raw_amount!r} raw_rate={raw_rate!r} raw_monthly={raw_monthly!r}"
                        )
                        ui.notify('Niepoprawne liczby.', color='negative')
                        return

                    try:
                        logger.info(f"show_add_debt_dialog.create: invalid end date raw_end={raw_end!r}")
                        end_dt = datetime.fromisoformat(raw_end)
                    except Exception:
                        ui.notify('Niepoprawna data końca (ISO).', color='negative')
                        return

                    w_id = to_uuid(wallet_sel.value)

                    res = await wallet.wallet_client.create_debt(
                        user_id=user_id,
                        wallet_id=w_id,
                        name=nm,
                        lander=ln,
                        amount=amt,
                        currency=str(currency.value),
                        interest_rate_pct=rt,
                        monthly_payment=mp,
                        end_date=end_dt,
                    )
                    if not res:
                        ui.notify('Nie udało się dodać zobowiązania.', color='negative')
                        return

                    ui.notify('Dodano zobowiązanie.', color='positive')
                    dlg.close()
                    if on_refresh:
                        await on_refresh()

                with ui.row().classes('justify-center q-gutter-md q-mt-md'):
                    ui.button('Anuluj').props('no-caps flat').style('min-width: 110px; height: 44px;').on_click(dlg.close)
                    ui.button('Dodaj', icon='add').props('no-caps color=primary').style(
                        'min-width: 130px; height: 44px; border-radius: 8px;'
                    ).on_click(create)

    dlg.open()
 
    
async def render_debts_table(wallet, on_refresh=None) -> None:
    """
    Render editable debts table and wire save/delete handlers.

    Args:
        wallet: Wallet page/controller providing `wallet_client`, `selected_wallet`, `view_currency`, FX rates, etc.
        on_refresh: Optional async callback to refresh the parent view after changes.
    """
    user_id = to_uuid(wallet.get_user_id())
    view_ccy = wallet.view_currency.value or "PLN"

    rows: List[Dict[str, Any]] = []

    for w in (wallet.selected_wallet or []):
        api_rows = await wallet.wallet_client.list_debts(user_id=user_id, wallet_id=to_uuid(w.id))

        for d in api_rows:
            d_ccy = (d.currency.value if hasattr(d.currency, "value") else str(d.currency))
            amount = dec(d.amount)
            amount_view = change_currency_to(amount, view_ccy, d_ccy, wallet.currency_rate)

            mp = dec(getattr(d, "monthly_payment", None))
            mp_view = change_currency_to(mp, view_ccy, d_ccy, wallet.currency_rate)

            rows.append({
                "id": str(d.id),
                "wallet_id": str(d.wallet_id),
                "wallet": getattr(w, "name", ""),
                "name": d.name,
                "lander": d.lander,
                "amount": str(amount),                  
                "currency": d_ccy,                   
                "interest_rate_pct": str(getattr(d, "interest_rate_pct", "0")),
                "monthly_payment": str(mp),
                "end_date": (d.end_date.isoformat() if isinstance(d.end_date, datetime) else str(d.end_date)),
                "amount_fmt": f"{format_pl_amount(amount_view, decimals=0)} {view_ccy}",
                "monthly_fmt": f"{format_pl_amount(mp_view, decimals=0)} {view_ccy}",
            })

    columns = [
        {"name": "name", "label": "Nazwa", "field": "name", "align": "left"},
        {"name": "lander", "label": "Lender", "field": "lander", "align": "left"},
        {"name": "amount_fmt", "label": f"Kwota ({view_ccy})", "field": "amount_fmt", "align": "center"},
        {"name": "interest_rate_pct", "label": "Oprocent. %", "field": "interest_rate_pct", "align": "center"},
        {"name": "monthly_fmt", "label": f"Rata ({view_ccy})", "field": "monthly_fmt", "align": "center"},
        {"name": "end_date", "label": "Koniec", "field": "end_date", "align": "center"},
        {"name": "actions", "label": "", "field": "actions", "align": "right"},
    ]

    async def handle_save(row: Dict[str, Any]) -> None:
        """Validate edited row and send update request."""
        debt_id = to_uuid(row.get("id"))

        name = (row.get("name") or "").strip()
        lander = (row.get("lander") or "").strip()
        if not name or not lander:
            logger.info(f"render_debts_table.handle_save: missing required fields debt_id={debt_id}")
            ui.notify("Nazwa i lender są wymagane.", color="negative")
            return

        raw_amount = str(row.get("amount_fmt") or "").replace(view_ccy, "").strip().replace(" ", "").replace(",", ".")
        raw_rate = str(row.get("interest_rate_pct") or "").strip().replace(" ", "").replace(",", ".")
        raw_mp = str(row.get("monthly_fmt") or "").replace(view_ccy, "").strip().replace(" ", "").replace(",", ".")
        raw_end = str(row.get("end_date") or "").strip()
        
        try:
            amt = Decimal(raw_amount)
            mpd = Decimal(raw_mp or "0")
        except Exception:
            ui.notify("Niepoprawna kwota.", color="negative")
            return
        
        amount = change_currency_to(
                amount=Decimal(amt),
                view_currency=row.get("currency"),
                transaction_currency=view_ccy,
                rates=wallet.currency_rate,
            )
        
        mp = change_currency_to(
                amount=Decimal(mpd),
                view_currency=row.get("currency"),
                transaction_currency=view_ccy,
                rates=wallet.currency_rate,
            )

        try:
            rate = Decimal(raw_rate or "0")      
        except Exception:
            logger.info(f"render_debts_table.handle_save: invalid rate debt_id={debt_id} raw_rate={raw_rate!r}")
            ui.notify("Niepoprawne liczby (kwota / oprocentowanie / rata).", color="negative")
            return

        try:
            end_dt = datetime.fromisoformat(raw_end)
        except Exception:
            logger.info(f"render_debts_table.handle_save: invalid end date debt_id={debt_id} raw_end={raw_end!r}")
            ui.notify("Niepoprawna data końca (ISO format).", color="negative")
            return

        res = await wallet.wallet_client.update_debt(
            debt_id=debt_id,
            user_id=user_id,
            name=name,
            lander=lander,
            amount=amount,
            currency=str(row.get("currency") or ""),
            interest_rate_pct=rate,
            monthly_payment=mp,
            end_date=end_dt,
        )
        if not res:
            logger.error(f"render_debts_table.handle_save: update failed debt_id={debt_id}")
            ui.notify("Nie udało się zaktualizować zobowiązania.", color="negative")
            return

        ui.notify("Zobowiązanie zaktualizowane.", color="positive")
        if on_refresh:
            await on_refresh()

    async def handle_delete(row: Dict[str, Any]) -> None:
        """Delete debt entry."""
        debt_id = to_uuid(row.get("id"))
        ok = await wallet.wallet_client.delete_debt(user_id=user_id, debt_id=debt_id)
        
        if not ok:
            ui.notify("Nie udało się usunąć zobowiązania.", color="negative")
            return
        
        logger.info(f"render_debts_table.handle_delete: succeeded debt_id={debt_id}")
        ui.notify("Zobowiązanie usunięte.", color="positive")
        if on_refresh:
            await on_refresh()

    def open_add_debt_dialog() -> None:
        """Open the create-debt dialog."""
        logger.debug("render_debts_table: open_add_debt_dialog")
        show_add_debt_dialog(wallet, on_refresh=on_refresh)

    with ui.card().classes('w-full').style('''
        border-radius: 16px;
        background: #ffffff;
        border: 1px solid rgba(148,163,184,.35);
        box-shadow: 0 4px 10px rgba(15,23,42,.03);
        padding: 12px 14px 10px;
    '''):
        with ui.row().classes('items-center justify-between q-mb-xs w-full'):
            with ui.row().classes('items-center q-gutter-sm'):
                ui.icon('sym_o_account_balance').classes('text-grey-6')
                ui.label('Zobowiązania').classes('text-sm text-weight-medium')

            ui.button('Dodaj', on_click=open_add_debt_dialog) \
                .props('flat dense no-caps color=primary') \
                .classes('text-caption')

        if not rows:
            with ui.row().classes('items-center text-grey-7 justify-center w-full').style('padding:10px 0;'):
                with ui.column().classes('items-center justify-center q-gutter-xs'):
                    ui.icon('sym_o_receipt_long').classes('text-h5 text-grey-5')
                    ui.label('Brak zobowiązań do wyświetlania').classes('text-caption text-grey-6')
            return

        tbl = ui.table(columns=columns, rows=rows, row_key="id") \
            .props('flat dense separator=horizontal') \
            .classes('w-full text-body2')

        tbl.add_slot('body-cell-name', """
        <q-td :props="props">
          <q-input v-model="props.row.name" dense borderless class="q-pa-none" />
        </q-td>
        """)
        tbl.add_slot('body-cell-lander', """
        <q-td :props="props">
          <q-input v-model="props.row.lander" dense borderless class="q-pa-none" />
        </q-td>
        """)
        tbl.add_slot('body-cell-amount_fmt', """
        <q-td :props="props">
          <q-input v-model="props.row.amount_fmt"
                    dense borderless 
                    class="q-pa-none"
                    input-class="text-center"
                    style="max-width:120px;margin:0 auto;" />
        </q-td>
        """)

        tbl.add_slot('body-cell-interest_rate_pct', """
        <q-td :props="props" class="text-center">
          <q-input v-model="props.row.interest_rate_pct" 
                    dense borderless 
                    class="q-pa-none"
                    input-class="text-center"
                    style="max-width:120px;margin:0 auto;" />
        </q-td>
        """)
        tbl.add_slot('body-cell-monthly_fmt', """
        <q-td :props="props" class="text-center">
          <q-input v-model="props.row.monthly_fmt" 
                    dense borderless 
                    class="q-pa-none"
                    input-class="text-center"
                    style="max-width:120px;margin:0 auto;" />
        </q-td>
        """)

        tbl.add_slot('body-cell-end_date', """
        <q-td :props="props" class="text-center">
          <q-input v-model="props.row.end_date" dense borderless class="q-pa-none"
                   style="max-width:160px;text-align:center;margin:0 auto"
                   placeholder="YYYY-MM-DDTHH:MM:SS" />
        </q-td>
        """)

        tbl.add_slot('body-cell-actions', """
        <q-td :props="props">
          <q-btn flat dense icon="save" color="primary"
                 @click="$parent.$emit('save', {row: props.row})" />
          <q-btn flat dense icon="delete" color="negative"
                 @click="$parent.$emit('delete', {row: props.row})" />
        </q-td>
        """)

        tbl.on('save', lambda e: handle_save(e.args['row']))
        tbl.on('delete', lambda e: handle_delete(e.args['row']))


async def show_debts_dialog(wallet) -> None:
    """
    Open a dialog showing debts KPIs and an editable debts table.

    Args:
        wallet: Wallet page/controller providing `view_currency`, `selected_wallet`,
                `wallet_client`, and FX rates.
    """
    dlg = ui.dialog()

    view_ccy = wallet.view_currency.value or "PLN"
    
    logger.info(f"show_debts_dialog: open view_ccy={view_ccy!r}")

    with dlg:
        with ui.card().style('''
            max-width: 920px;
            padding: 32px 32px 24px;
            border-radius: 24px;
            background: linear-gradient(180deg, #ffffff 0%, #f6f9ff 100%);
            box-shadow: 0 12px 30px rgba(15,23,42,.08);
            border: 1px solid rgba(15,23,42,.06);
        '''):

            with ui.row().classes('items-center q-gutter-md q-mb-md').style('width: 100%;'):
                ui.icon('sym_o_account_balance').style('''
                    font-size: 40px;
                    color: #ef4444;
                    background: #fee2e2;
                    padding: 16px;
                    border-radius: 50%;
                ''')
                with ui.column().classes('q-gutter-xs'):
                    ui.label('Zobowiązania').classes('text-h5 text-weight-medium')
                    ui.label('Suma zobowiązań i szczegóły per portfel.').classes('text-body2 text-grey-7')
            
            with ui.row().classes('w-full justify-center q-mt-xs q-mb-md'):
                with ui.column().classes('items-center q-pa-md rounded-2xl bg-white').style(
                    'border:1px solid rgba(148,163,184,.5); min-width:300px; max-width:380px;'
                ):
                    ui.label('Łączna kwota zobowiązań').classes('text-xs text-grey-600')
                    kpi_total_label = ui.label('—').classes('text-h5 text-weight-semibold text-center')
                    kpi_sub_label = ui.label('').classes('text-caption text-grey-7 text-center')

            with ui.row().classes('q-gutter-sm q-mb-sm w-full justify-center no-wrap'):
                def small_kpi(label: str, value: str) -> None:
                    with ui.column().classes('col q-pa-sm rounded-xl bg-white items-center').style(
                        'border:1px solid rgba(148,163,184,.4); min-width:0;'
                    ):
                        ui.label(label).classes('text-xs text-grey-500')
                        ui.label(value).classes('text-sm text-weight-semibold text-center')
                
                with ui.column().classes('col q-pa-sm rounded-xl bg-white items-center').style('border:1px solid rgba(148,163,184,.4);'):
                    ui.label('Liczba').classes('text-xs text-grey-500')
                    kpi_count = ui.label('—').classes('text-sm text-weight-semibold text-center')

                with ui.column().classes('col q-pa-sm rounded-xl bg-white items-center').style('border:1px solid rgba(148,163,184,.4);'):
                    ui.label('Śr. oprocent.').classes('text-xs text-grey-500')
                    kpi_avg = ui.label('—').classes('text-sm text-weight-semibold text-center')

                with ui.column().classes('col q-pa-sm rounded-xl bg-white items-center').style('border:1px solid rgba(148,163,184,.4);'):
                    ui.label('Rata (suma)').classes('text-xs text-grey-500')
                    kpi_monthly = ui.label('—').classes('text-sm text-weight-semibold text-center')

            ui.separator().classes('q-my-md')

            with ui.column().classes('w-full').style('max-height: 360px; overflow-y: auto; padding-right: 4px;'):
                with ui.row().classes('w-full justify-center'):
                    table_container = ui.column().classes('w-[95%] max-w-[820px]')

            with ui.row().classes('justify-end q-mt-md').style('width: 100%;'):
                ui.button('Zamknij', on_click=dlg.close).props('no-caps').style('min-width: 110px; height: 40px;')

            async def refresh_dialog() -> None:
                """Recompute KPIs and rerender table."""
                table_container.clear()

                total, count, avg_rate, monthly_total = await compute_debts_summary_from_api(wallet)

                kpi_total_label.set_text(debts_kpi_label(total, view_ccy))
                kpi_sub_label.set_text(debts_kpi_subtitle(count, avg_rate))

                kpi_count.set_text(str(count))
                kpi_avg.set_text(f"{format_pl_amount(avg_rate, decimals=1)}%")
                kpi_monthly.set_text(f"{format_pl_amount(monthly_total, decimals=0)} {view_ccy}")

                with table_container:
                    await render_debts_table(wallet, on_refresh=refresh_dialog)

    dlg.open()
    await refresh_dialog()
