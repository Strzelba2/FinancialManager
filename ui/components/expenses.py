import uuid
from decimal import Decimal
from typing import Any, Dict, List
import logging

from nicegui import ui

from schemas.wallet import RecurringExpenseOut
from utils.money import format_pl_amount, dec, change_currency_to
from utils.utils import to_uuid

logger = logging.getLogger(__name__)


async def show_add_recurring_expense_dialog(wallet, on_refresh=None) -> None:
    """
    Show a dialog to create a recurring monthly expense.

    Args:
        wallet: Wallet page/controller providing `get_user_id()`, `selected_wallet`,
                `view_currency`, `currency_rate`, and `wallet_client`.
        on_refresh: Optional async callback invoked after a successful create.

    Returns:
        None. Opens a NiceGUI dialog.
    """
    user_id_raw = wallet.get_user_id()
    if not user_id_raw:
        logger.warning("show_add_recurring_expense_dialog: invalid user_id (empty)")
        ui.notify("Niepoprawny user.", color="negative")
        return
    user_id = to_uuid(user_id_raw)

    wallets = wallet.selected_wallet or []
    if not wallets:
        logger.info(f"show_add_recurring_expense_dialog: no selected wallets user_id={user_id}")
        ui.notify("Brak wybranego portfela.", color="negative")
        return

    view_ccy = getattr(getattr(wallet, "view_currency", None), "value", None) or "PLN"

    dlg = ui.dialog()
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

                ui.icon('sym_o_receipt_long').style('''
                    font-size: 44px;
                    color: #2563eb;
                    background: #dbeafe;
                    padding: 18px;
                    border-radius: 50%;
                    margin-bottom: 18px;
                ''')

                ui.label("Dodaj stały wydatek").classes("text-h5 text-weight-medium q-mb-sm text-center")
                ui.label("Stały miesięczny wydatek (np. czynsz, internet). Pola z * są wymagane.").classes(
                    "text-body2 text-grey-8 q-mb-lg text-center"
                )

                wallet_options = {str(w.id): getattr(w, "name", str(w.id)) for w in wallets}
                if not wallet_options:
                    ui.notify("Brak wybranego portfela.", color="negative")
                    return

                wallet_sel = ui.select(
                    options=wallet_options,
                    value=list(wallet_options.keys())[0],
                    label="Portfel *",
                ).props("filled").style("width:100%").classes("q-mb-sm")

                name = ui.input(placeholder="Nazwa * (np. Czynsz)").props("filled clearable").style("width:100%").classes("q-mb-sm")

                with ui.row().classes("q-gutter-sm w-full"):
                    category = ui.input(placeholder="Kategoria (np. Mieszkanie / Media)").props("filled clearable").classes("col")
                    account = ui.input(placeholder="Konto (np. mBank / Revolut / Visa)").props("filled clearable").classes("col")

                note = ui.input(placeholder="Notatka (opcjonalnie)").props("filled clearable").style("width:100%").classes("q-mt-sm")

                with ui.row().classes("q-gutter-sm w-full q-mt-sm"):
                    amount = ui.input(placeholder="Kwota * (np. 1800.00)").props("filled clearable inputmode=decimal").classes("col")
                    currency = ui.select(
                        options=["PLN", "EUR", "USD"],
                        value=view_ccy,
                        label="Waluta *",
                    ).props("filled").classes("col")

                with ui.row().classes("q-gutter-sm w-full q-mt-sm"):
                    due_day = ui.input(placeholder="Dzień miesiąca * (1–31)").props("filled clearable type=number min=1 max=31").classes("col")

                async def save() -> None:
                    """
                    Validate dialog fields and create recurring expense via API.
                    """
                    nm = (name.value or "").strip()
                    if not nm:
                        logger.info(f"show_add_recurring_expense_dialog.save: missing name user_id={user_id}")
                        ui.notify("Podaj nazwę.", color="negative")
                        return

                    raw_amount = str(amount.value or "").strip().replace(" ", "").replace(",", ".")
                    try:
                        amt = Decimal(raw_amount)
                    except Exception:
                        ui.notify("Podaj poprawną kwotę.", color="negative")
                        return
                    if amt <= 0:
                        ui.notify("Kwota musi być większa od 0.", color="negative")
                        return

                    raw_dd = str(due_day.value or "").strip()
                    try:
                        dd = int(raw_dd)
                    except Exception:
                        ui.notify("Podaj poprawny dzień (1–31).", color="negative")
                        return
                    if not (1 <= dd <= 31):
                        ui.notify("Dzień musi być w zakresie 1–31.", color="negative")
                        return

                    w_id = to_uuid(wallet_sel.value)

                    res = await wallet.wallet_client.create_recurring_expense(
                        user_id=user_id,
                        wallet_id=w_id,
                        name=nm,
                        category=((category.value or "").strip() or None),
                        amount=amt,
                        currency=str(currency.value),
                        due_day=dd,
                        account=((account.value or "").strip() or None),
                        note=((note.value or "").strip() or None),
                    )

                    if not res:
                        ui.notify("Nie udało się dodać wydatku.", color="negative")
                        return

                    ui.notify("Dodano stały wydatek.", color="positive")
                    dlg.close()
                    if on_refresh:
                        await on_refresh()

                with ui.row().classes("justify-center q-gutter-md q-mt-md"):
                    ui.button("Anuluj").props("no-caps flat").style("min-width: 110px; height: 44px;").on_click(dlg.close)
                    ui.button("Dodaj", icon="add").props("no-caps color=primary").style(
                        "min-width: 130px; height: 44px; border-radius: 8px;"
                    ).on_click(save)

    dlg.open()


async def render_recurring_expenses_table(wallet, on_refresh=None) -> None:
    """
    Render editable table of recurring expenses and wire save/delete handlers.

    Args:
        wallet: Wallet controller with `wallet_client`, `selected_wallet`, `view_currency`, and FX rates.
        on_refresh: Optional async callback invoked after successful edits/deletes.

    Returns:
        None. Renders UI.
    """
    user_id = wallet.get_user_id()
    if not user_id:
        logger.warning("render_recurring_expenses_table: invalid user_id (empty)")
        ui.notify("Niepoprawny user", color="negative")
        return

    wallets = wallet.selected_wallet or []
    view_ccy = wallet.view_currency.value or "PLN"

    api_rows: List[Dict[str, Any]] = []
    for w in wallets:
        rows: List[RecurringExpenseOut] = await wallet.wallet_client.list_recurring_expenses(
            user_id=user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id)),
            wallet_id=w.id,
        )
        for r in rows:
            amt = Decimal(str(r.amount or "0"))
            amt_view = change_currency_to(
                amount=amt,
                view_currency=view_ccy,
                transaction_currency=r.currency.value,
                rates=wallet.currency_rate,
            )
            api_rows.append({
                "id": str(r.id),
                "wallet_id": str(r.wallet_id),
                "wallet": w.name,
                "name": r.name,
                "category": r.category or "",
                "amount": str(r.amount),                
                "currency": r.currency.value,      
                "due_day": int(r.due_day),
                "account": r.account or "",
                "note": r.note or "",
                "amount_view_fmt": f"{format_pl_amount(amt_view, decimals=2)}",
            })

    columns = [
        {"name": "name", "label": "Nazwa", "field": "name", "align": "left"},
        {"name": "category", "label": "Kategoria", "field": "category", "align": "left"},
        {"name": "amount_view_fmt", "label": f"Kwota ({view_ccy})", "field": "amount_view_fmt", "align": "center"},
        {"name": "due_day", "label": "Dzień", "field": "due_day", "align": "center"},
        {"name": "account", "label": "Konto", "field": "account", "align": "center"},
        {"name": "note", "label": "Notatka", "field": "note", "align": "center"},
        {"name": "actions", "label": "", "field": "actions", "align": "right"},
    ]

    async def handle_save(row: Dict[str, Any]) -> None:
        """
        Validate edited row and send update request.
        """
        try:
            exp_id = uuid.UUID(str(row.get("id")))
        except Exception:
            ui.notify("Niepoprawne ID.", color="negative")
            return

        nm = (row.get("name") or "").strip()
        if not nm:
            ui.notify("Nazwa nie może być pusta.", color="negative")
            return

        raw_amt = str(row.get("amount_view_fmt") or "").strip().replace(" ", "").replace(",", ".")
        
        try:
            amt = Decimal(raw_amt)
        except Exception:
            ui.notify("Niepoprawna kwota.", color="negative")
            return
        
        amt_db_cur = change_currency_to(
                amount=Decimal(amt),
                view_currency=row.get("currency"),
                transaction_currency=view_ccy,
                rates=wallet.currency_rate,
            )
        
        cur = (row.get("currency") or "").strip().upper()
        if cur not in ("PLN", "EUR", "USD"):
            ui.notify("Waluta musi być PLN/EUR/USD.", color="negative")
            return

        try:
            dd = int(row.get("due_day") or 0)
        except Exception:
            ui.notify("Niepoprawny dzień.", color="negative")
            return
        if dd < 1 or dd > 31:
            ui.notify("Dzień musi być 1-31.", color="negative")
            return

        res = await wallet.wallet_client.update_recurring_expense(
            user_id=user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id)),
            expense_id=exp_id,
            name=nm,
            category=(row.get("category") or "").strip() or None,
            amount=amt_db_cur,
            currency=cur,
            due_day=dd,
            account=(row.get("account") or "").strip() or None,
            note=(row.get("note") or "").strip() or None,
        )
        if not res:
            ui.notify("Nie udało się zapisać zmian.", color="negative")
            return

        ui.notify("Zapisano zmiany.", color="positive")
        if on_refresh:
            await on_refresh()

    async def handle_delete(row: Dict[str, Any]) -> None:
        """
        Delete recurring expense entry.
        """
        try:
            exp_id = uuid.UUID(str(row.get("id")))
        except Exception:
            ui.notify("Niepoprawne ID.", color="negative")
            return

        ok = await wallet.wallet_client.delete_recurring_expense(
            user_id=user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id)),
            expense_id=exp_id,
        )
        if not ok:
            ui.notify("Nie udało się usunąć.", color="negative")
            return

        ui.notify("Usunięto wydatek.", color="positive")
        if on_refresh:
            await on_refresh()

    with ui.card().classes("w-full").style('''
        border-radius: 16px;
        background: #ffffff;
        border: 1px solid rgba(148,163,184,.35);
        box-shadow: 0 4px 10px rgba(15,23,42,.03);
        padding: 12px 14px 10px;
    '''):
        with ui.row().classes("items-center justify-between q-mb-xs w-full"):
            with ui.row().classes("items-center q-gutter-sm"):
                ui.icon("sym_o_payments").classes("text-grey-6")
                ui.label("Stałe wydatki").classes("text-sm text-weight-medium")

            ui.button(
                "Dodaj",
                on_click=lambda: show_add_recurring_expense_dialog(wallet, on_refresh=on_refresh),
            ).props("flat dense no-caps color=primary").classes("text-caption")

        if not api_rows:
            with ui.row().classes("items-center text-grey-7 justify-center w-full").style("padding:10px 0;"):
                with ui.column().classes("items-center justify-center q-gutter-xs"):
                    ui.icon("sym_o_receipt_long").classes("text-h5 text-grey-5")
                    ui.label("Brak stałych wydatków do wyświetlania.").classes("text-caption text-grey-6")
            return

        tbl = ui.table(columns=columns, rows=api_rows, row_key="id").props(
            "flat dense separator=horizontal"
        ).classes("w-full text-body2")

        tbl.add_slot("body-cell-name", """
        <q-td :props="props">
          <q-input v-model="props.row.name" dense borderless class="q-pa-none" />
        </q-td>
        """)
        
        tbl.add_slot("body-cell-category", """
        <q-td :props="props">
          <q-input v-model="props.row.category" dense borderless class="q-pa-none" />
        </q-td>
        """)
        
        tbl.add_slot("body-cell-amount_view_fmt", """
        <q-td :props="props" class="text-right">
          <q-input v-model="props.row.amount_view_fmt"
                   dense borderless class="q-pa-none"
                   input-class="text-center"
                   style="max-width:110px;margin:0 auto;" />
        </q-td>
        """)
     
        tbl.add_slot("body-cell-due_day", """
        <q-td :props="props" class="text-center">
          <q-input v-model="props.row.due_day"
                   dense borderless class="q-pa-none"
                   input-class="text-center"
                   style="max-width:110px;margin:0 auto;" />
        </q-td>
        """)
        
        tbl.add_slot("body-cell-account", """
        <q-td :props="props">
          <q-input v-model="props.row.account" 
                    dense borderless class="q-pa-none"
                    input-class="text-center"
                    style="max-width:110px;margin:0 auto;" />
        </q-td>
        """)
        tbl.add_slot("body-cell-note", """
        <q-td :props="props">
          <q-input v-model="props.row.note" dense borderless class="q-pa-none" />
        </q-td>
        """)

        tbl.add_slot("body-cell-actions", """
        <q-td :props="props">
          <q-btn flat dense icon="save" color="primary"
                 @click="$parent.$emit('save', {row: props.row})" />
          <q-btn flat dense icon="delete" color="negative"
                 @click="$parent.$emit('delete', {row: props.row})" />
        </q-td>
        """)

        tbl.on("save", lambda e: handle_save(e.args["row"]))
        tbl.on("delete", lambda e: handle_delete(e.args["row"]))
   
        
async def show_recurring_expenses_dialog(wallet) -> None:
    """
    Open dialog showing a summary and an editable recurring expenses table.

    Args:
        wallet: Wallet controller with `selected_wallet`, `wallet_client`, `view_currency`, and FX rates.

    Returns:
        None.
    """
    dlg = ui.dialog()

    view_ccy = wallet.view_currency.value or "PLN"

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
                ui.icon('sym_o_receipt_long').style('''
                    font-size: 40px;
                    color: #2563eb;
                    background: #e6f0ff;
                    padding: 16px;
                    border-radius: 50%;
                ''')
                with ui.column().classes('q-gutter-xs'):
                    ui.label('Stałe miesięczne wydatki').classes('text-h5 text-weight-medium')
                    ui.label('Podsumowanie i edycja stałych opłat.').classes('text-body2 text-grey-7')

            summary_box = ui.column().classes('w-full justify-center items-center q-mb-md')

            ui.separator().classes('q-my-md')

            content = ui.column().classes('w-full').style('max-height: 420px; overflow-y: auto; padding-right: 4px;')
            with content:
                table_container = ui.column().classes('w-full')

            with ui.row().classes('justify-end q-mt-md').style('width: 100%;'):
                ui.button('Zamknij', on_click=dlg.close).props('no-caps').style('min-width: 110px; height: 40px;')

            async def refresh_dialog() -> None:
                """
                Recompute summary and re-render the table.
                """
                user_id = wallet.get_user_id()
                wallets = wallet.selected_wallet or []
                total_view = Decimal("0")
                count = 0

                for w in wallets:
                    rows = await wallet.wallet_client.list_recurring_expenses(
                        user_id=user_id,
                        wallet_id=w.id,
                    )
                    for r in rows:
                        count += 1
                        amt = Decimal(str(r.amount or "0"))
                        total_view += change_currency_to(
                            amount=amt,
                            view_currency=view_ccy,
                            transaction_currency=r.currency.value,
                            rates=wallet.currency_rate,
                        )

                summary_box.clear()
                table_container.clear()

                with summary_box:
                    with ui.column().classes('items-center q-pa-md rounded-2xl bg-white').style(
                        'border:1px solid rgba(148,163,184,.5); min-width:260px; max-width:360px;'
                    ):
                        ui.label('Suma stałych wydatków / miesiąc').classes('text-xs text-grey-600')
                        ui.label(f"{format_pl_amount(total_view, decimals=0)} {view_ccy}").classes(
                            'text-h5 text-weight-semibold q-mb-xs text-center'
                        )
                        ui.label(f"{count} pozycji").classes('text-caption text-grey-7')

                with table_container:
                    await render_recurring_expenses_table(wallet, on_refresh=refresh_dialog)

            dlg.open()
            await refresh_dialog()


def recurring_expenses_panel_card(wallet, top: int = 5) -> None:
    """
    Render a compact panel card with top recurring expenses (from preloaded wallet state).

    Args:
        wallet: Wallet controller with `selected_wallet`, `view_currency`, and `currency_rate`.
        top: Maximum number of rows to show.

    Returns:
        None. Renders UI card.
    """
    view_ccy = wallet.view_currency.value or "PLN"
    wallets = wallet.selected_wallet or []

    all_rows: list[dict] = []
    for w in wallets:
        exp_list = getattr(w, "recurring_expenses_top", []) or []
        
        for r in exp_list:
            d_ccy = (r.currency.value if hasattr(r.currency, "value") else str(r.currency))
            amount = dec(r.amount)
            amount_view = change_currency_to(amount, view_ccy, d_ccy, wallet.currency_rate)
            amt = Decimal(str(r.amount or "0"))
            all_rows.append({
                "id": str(r.id),
                "name": r.name,
                "category": r.category or "",
                "amount": float(amt),
                "amount_fmt": f"{format_pl_amount(amount_view, decimals=2)} {view_ccy}",
                "due_day": int(r.due_day),
                "account": r.account or "",
                "note": r.note or "",
                "wallet": w.name,
            })

    all_rows.sort(key=lambda x: int(x.get("due_day") or 0), reverse=False)
    top_rows = all_rows[:top]

    cols_compact = [
        {"name": "name", "label": "Nazwa", "field": "name", "align": "left", "headerStyle": "font-weight:700"},
        {"name": "category", "label": "Kategoria", "field": "category", "align": "left", "headerStyle": "font-weight:700"},
        {"name": "amount_fmt", "label": "Kwota", "field": "amount_fmt", "align": "right",
         "classes": "num", "style": "width:140px", "headerStyle": "font-weight:700"},
        {"name": "due_day", "label": "Dzień", "field": "due_day", "align": "center",
         "style": "width:70px", "headerStyle": "font-weight:700"},
    ]

    with ui.card().classes('w-full max-w-none cursor-pointer p-0').style('width:100%') as card:
        card.on('click', lambda _: show_recurring_expenses_dialog(wallet)) 

        ui.label('Stałe miesięczne wydatki').classes('text-sm font-semibold').style('padding:6px 12px 2px 12px')

        if not top_rows:
            with ui.row().classes('items-center text-grey-7 justify-center w-full').style('padding:10px 0;'):
                with ui.column().classes('items-center justify-center q-gutter-sm'):
                    ui.icon('sym_o_receipt_long').classes('text-h4')
                    ui.label('Brak stałych wydatków do wyświetlania')\
                        .classes('text-body2 q-mt-none q-mb-none')\
                        .style('line-height:1.2; margin:0;')

                    ui.label('Dodaj Stały wydatek, aby je wyświetlić.')\
                        .classes('text-caption text-grey-6 q-mt-none q-mb-none')\
                        .style('line-height:1.2; margin:0;')
        else:
            ui.table(columns=cols_compact, rows=top_rows, row_key='id') \
                .props('flat dense separator=horizontal hide-bottom hide-pagination rows-per-page-options=[5]') \
                .classes('q-mt-none w-full') \
                .style('margin:0;padding:0')
