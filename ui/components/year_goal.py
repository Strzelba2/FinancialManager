from nicegui import ui
from datetime import datetime, timezone
from typing import List
from decimal import Decimal
import uuid
import logging

from schemas.wallet import Currency, YearGoalOut
from .cards import goals_bullet_card
from .investments import render_empty_assets_placeholder
from utils.money import change_currency_to, dec

logger = logging.getLogger(__name__)


async def render_goals_table(wallet, uid: uuid.UUID, on_refresh) -> None:
    """
    Render an editable goals table (per selected wallet) inside a styled card.

    The table shows:
    - year goals (revenue target / expense budget)
    - currency
    - save/delete actions

    Args:
        wallet: Your page/controller that exposes:
            - wallet.selected_wallet (iterable of wallets)
            - wallet.view_currency.value
            - wallet.wallet_client.list_wallet_goals(...)
            - wallet.wallet_client.upsert_wallet_goals(...)
            - wallet.wallet_client.delete_wallet_goals(...)
        uid: Current user id.
        on_refresh: Async callback to rebuild the dialog (chart + table) after save/delete.
    """
    view_ccy = wallet.view_currency.value

    rows = []
    for w in (wallet.selected_wallet or []):
        goals: List[YearGoalOut] = await wallet.wallet_client.list_wallet_goals(user_id=uid, wallet_id=w.id)
        if goals:
            for g in goals:
                rows.append({
                    "id": str(g.id),
                    "wallet_id": str(w.id),
                    "wallet": w.name,
                    "rev_target_year": str(g.rev_target_year),
                    "exp_budget_year": str(g.exp_budget_year),
                    "currency": (g.currency.value if hasattr(g.currency, "value") else str(g.currency)),
                    "year": g.year
                })

    columns = [
        {"name": "wallet", "label": "Portfel", "field": "wallet", "align": "left"},
        {"name": "year", "label": "Rok", "field": "year", "align": "center"},
        {"name": "rev_target_year", "label": "Cel przychodów (rok)", "field": "rev_target_year", "align": "center"},
        {"name": "exp_budget_year", "label": "Budżet wydatków (rok)", "field": "exp_budget_year", "align": "center"},
        {"name": "currency", "label": "Waluta", "field": "currency", "align": "center"},
        {"name": "actions", "label": "", "field": "actions", "align": "right"},
    ]

    async def handle_save(row: dict) -> None:
        """
        Save (upsert) a single goals row.

        Row is edited inline in the table and contains numeric fields as strings.
        """
        wallet_id = uuid.UUID(str(row["wallet_id"]))
        ccy = str(row.get("currency") or view_ccy)

        def parse_money(raw: str) -> Decimal:
            raw = (raw or "").strip().replace(" ", "").replace(",", ".")
            return Decimal(raw) if raw else Decimal("0")

        try:
            rev = parse_money(str(row.get("rev_target_year") or "0"))
            exp = parse_money(str(row.get("exp_budget_year") or "0"))
            year = int(row.get("year") or datetime.now(timezone.utc).year)
        except Exception:
            ui.notify("Invalid number.", color="negative", timeout=0, close_button="OK")
            return

        res = await wallet.wallet_client.upsert_wallet_goals(
            user_id=uid,
            wallet_id=wallet_id,
            year=year,
            rev_target_year=rev,
            exp_budget_year=exp,
            currency=ccy,
        )
        if not res:
            ui.notify("Failed to save.", color="negative", timeout=0, close_button="OK")
            return

        ui.notify("Saved.", color="positive")
        await on_refresh()

    async def handle_delete(row: dict) -> None:
        """Delete goals for a row if it has an id."""
        if not row.get("id"):
            logger.warning("handle_delete: row has no id -> nothing to delete")
            ui.notify("Nothing to delete (goals not created).", color="warning", timeout=0, close_button="OK")
            return
        goal_id = uuid.UUID(str(row["id"]))

        ok = await wallet.wallet_client.delete_wallet_goals(user_id=uid, goal_id=goal_id)
        if not ok:
            ui.notify("Failed to delete.", color="negative", timeout=0, close_button="OK")
            return

        ui.notify("Deleted.", color="positive")
        await on_refresh()

    with ui.card().classes('w-full').style('''
        border-radius: 16px;
        background: #ffffff;
        border: 1px solid rgba(148,163,184,.35);
        box-shadow: 0 4px 10px rgba(15,23,42,.03);
        padding: 12px 14px 10px;
        margin-top: 12px;
    '''):
        with ui.row().classes('items-center q-gutter-sm q-mb-xs'):
            ui.icon('sym_o_tune').classes('text-grey-6')
            
        if not rows:
            render_empty_assets_placeholder('Brak dodanych nieruchomości w portfelu.')
            return

        tbl = ui.table(columns=columns, rows=rows, row_key='wallet_id') \
            .props('flat dense separator=horizontal') \
            .classes('w-full text-body2')

        tbl.add_slot('body-cell-rev_target_year', """
        <q-td :props="props">
          <q-input v-model="props.row.rev_target_year" dense borderless class="q-pa-none text-right" />
        </q-td>
        """)
        tbl.add_slot('body-cell-exp_budget_year', """
        <q-td :props="props">
          <q-input v-model="props.row.exp_budget_year" dense borderless class="q-pa-none text-right" />
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


async def show_goals_dialog(wallet) -> None:
    """
    Show a dialog with:
    - year selector
    - YTD progress card (computed by client calls)
    - editable goals table (save/delete)
    - button to open 'add goals' dialog

    Args:
        wallet: Your controller/page object that exposes:
            - get_user_id()
            - selected_wallet
            - view_currency.value
            - currency_rate
            - wallet_client methods used below
    """
    logger.info("show_goals_dialog: start")
    user_id = wallet.get_user_id()
    if not user_id:
        ui.notify("Invalid user.", color="negative", timeout=0, close_button="OK")
        return
    uid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))

    dlg = ui.dialog()
    year_now = datetime.now(timezone.utc).year

    with dlg:
        with ui.card().style('''
            max-width: 920px;
            padding: 32px 32px 24px;
            border-radius: 24px;
            background: linear-gradient(180deg, #ffffff 0%, #f6f9ff 100%);
            box-shadow: 0 12px 30px rgba(15,23,42,.08);
            border: 1px solid rgba(15,23,42,.06);
        '''):

            with ui.row().classes('items-center q-gutter-sm q-mb-md').style('width:100%'):
                ui.icon('sym_o_flag').style('''
                    font-size: 40px;
                    color: #3b82f6;
                    background: #e6f0ff;
                    padding: 16px;
                    border-radius: 50%;
                ''')
                with ui.column().classes('q-gutter-xs'):
                    ui.label('Cele i budżet').classes('text-h5 text-weight-medium')
                    ui.label('Cele roczne i realizacja YTD z transakcji.').classes('text-body2 text-grey-7')

            with ui.row().classes('items-center justify-between w-full q-mb-sm'):
                year_sel = ui.select(
                    options=[year_now, year_now - 1, year_now - 2],
                    value=year_now,
                    label='Rok',
                ).props('dense outlined').style('min-width:140px')

                ui.label('').classes('text-caption text-grey-6')

            chart_container = ui.column().classes('w-full')
            table_container = ui.column().classes('w-full')

            with ui.row().classes('justify-end q-mt-md').style('width: 100%;'):
                ui.button('Zamknij', on_click=dlg.close).props('no-caps').style('min-width:110px;height:40px;')

            async def open_add_goal_dialog() -> None:
                """Open dialog to add/upsert annual goals for a selected wallet/year."""
                logger.info("open_add_goal_dialog: start")
                dlg = ui.dialog()
                with dlg:
                    with ui.card().style("""
                        max-width: 520px;
                        padding: 44px 34px 28px;
                        border-radius: 24px;
                        background: linear-gradient(180deg, #ffffff 0%, #f6f9ff 100%);
                        box-shadow: 0 10px 24px rgba(15,23,42,.06);
                        border: 1px solid rgba(2,6,23,.06);
                    """):

                        with ui.column().classes("items-center justify-center").style("width:100%"):
                            ui.icon("sym_o_flag").style("""
                                font-size: 48px;
                                color: #3b82f6;
                                background: #e6f0ff;
                                padding: 20px;
                                border-radius: 50%;
                                margin-bottom: 18px;
                            """)

                            ui.label("Ustaw cele na rok").classes("text-h5 text-weight-medium q-mb-xs text-center")
                            ui.label("Dodaj/ustaw cele dla wybranego portfela. Pola z gwiazdką (*) są wymagane.") \
                                .classes("text-body2 text-grey-8 q-mb-lg text-center")

                        wallets = wallet.selected_wallet or []
                        wallet_options = {str(w.id): getattr(w, "name", str(w.id)) for w in wallets}

                        if not wallet_options:
                            ui.notify(
                                "Brak portfeli do wyboru. Najpierw utwórz portfel.",
                                color="negative",
                                timeout=0,
                                close_button=True,
                            )
                            return

                        year_now = datetime.now(timezone.utc).year

                        wallet_sel = ui.select(
                            options=wallet_options,
                            value=list(wallet_options.keys())[0],
                            label="Portfel *",
                        ).props("filled dense").style("width: 100%").classes("q-mb-sm")

                        year_sel = ui.select(
                            options=[year_now, year_now - 1, year_now - 2],
                            value=year_now,
                            label="Rok *",
                        ).props("filled dense").style("width: 100%").classes("q-mb-sm")

                        ccy_sel = ui.select(
                            options=[c.value for c in Currency],
                            value=wallet.view_currency.value,
                            label="Waluta *",
                        ).props("filled dense").style("width: 100%").classes("q-mb-sm")

                        rev_in = ui.input(
                            label="Cel przychodów (rok) *",
                            placeholder="np. 100000.00",
                        ).props("filled dense").style("width: 100%").classes("q-mb-sm")

                        exp_in = ui.input(
                            label="Budżet wydatków (rok) *",
                            placeholder="np. 50000.00",
                        ).props("filled dense").style("width: 100%").classes("q-mb-md")

                        def _parse_decimal(v: object) -> Decimal:
                            s = str(v or "0").strip().replace(" ", "").replace(",", ".")
                            return Decimal(s)

                        async def save() -> None:
                            """Validate inputs, upsert goals, close dialog, refresh parent dialog."""
                            try:
                                if not wallet_sel.value:
                                    ui.notify("Wybierz portfel.", color="negative", timeout=0, close_button="OK")
                                    return

                                rev = _parse_decimal(rev_in.value)
                                exp = _parse_decimal(exp_in.value)

                                if rev <= 0 or exp <= 0:
                                    ui.notify("Wartości muszą być większe od 0.", color="negative", timeout=0, close_button="OK")
                                    return

                            except Exception:
                                ui.notify("Nieprawidłowy format liczby.", color="negative", timeout=0, close_button="OK")
                                return

                            res = await wallet.wallet_client.upsert_wallet_goals(
                                user_id=uid,
                                wallet_id=uuid.UUID(str(wallet_sel.value)),
                                year=int(year_sel.value),
                                rev_target_year=rev,
                                exp_budget_year=exp,
                                currency=str(ccy_sel.value),
                            )

                            if not res:
                                ui.notify("Nie udało się zapisać celów.", color="negative", timeout=0, close_button="OK")
                                return

                            ui.notify("Zapisano.", color="positive")
                            dlg.close()
                            await refresh_dialog()

                        with ui.row().classes("justify-end q-gutter-sm q-mt-md").style("width:100%"):
                            ui.button("Anuluj").props("no-caps flat").style("""
                                min-width: 110px;
                                height: 44px;
                                padding: 0 18px;
                            """).on_click(dlg.close)

                            ui.button("Zapisz", icon="save").props("no-caps color=primary").style("""
                                min-width: 140px;
                                height: 44px;
                                border-radius: 10px;
                                padding: 0 22px;
                            """).on_click(save)

                dlg.open()
                
            async def compute_goals_ytd_inputs_vi_client(year: int) -> dict:
                """
                Compute YTD progress numbers by calling wallet_client endpoints.

                Returns a dict consumed by goals_bullet_card(...).
                """
                logger.info(f"compute_goals_ytd_inputs_vi_client: start (year={year})")

                user_id = wallet.get_user_id()

                view_ccy = wallet.view_currency.value
                now = datetime.now(timezone.utc)
                month_index = now.month - 1

                rev_target_year = Decimal("0")
                exp_budget_year = Decimal("0")
                rev_actual_ytd = Decimal("0")
                exp_actual_ytd = Decimal("0")

                for w in (wallet.selected_wallet or []):
                    g = await wallet.wallet_client.get_wallet_goals(user_id=user_id, wallet_id=w.id, year=year)
                    if g:
                        g_ccy = g.currency.value if hasattr(g.currency, "value") else str(g.currency)
                        rev_target_year += change_currency_to(dec(g.rev_target_year), view_ccy, g_ccy, wallet.currency_rate)
                        exp_budget_year += change_currency_to(dec(g.exp_budget_year), view_ccy, g_ccy, wallet.currency_rate)

                    s = await wallet.wallet_client.get_wallet_ytd_summary(user_id=user_id, wallet_id=w.id, year=year)

                    for ccy, amt_s in (s.get("income_by_currency") or {}).items():
                        rev_actual_ytd += change_currency_to(dec(amt_s), view_ccy, ccy, wallet.currency_rate)

                    for ccy, amt_s in (s.get("expense_by_currency") or {}).items():
                        exp_actual_ytd += change_currency_to(dec(amt_s), view_ccy, ccy, wallet.currency_rate)

                return {
                    "rev_target_year": float(rev_target_year),
                    "exp_budget_year": float(exp_budget_year),
                    "rev_actual_ytd": float(rev_actual_ytd),
                    "exp_actual_ytd": abs(float(exp_actual_ytd)),
                    "month_index": month_index,
                    "unit": f" {view_ccy}",
                }

            async def refresh_dialog() -> None:   
                """Rebuild chart + table for the selected year."""
                y = int(year_sel.value or year_now)

                chart_container.clear()
                with chart_container:
                    data = await compute_goals_ytd_inputs_vi_client(y)

                    with ui.row().classes('items-center justify-between w-full q-mb-xs'):
                        ui.label('Postęp YTD').classes('text-sm font-semibold')
                        ui.button('Ustaw cele', on_click=open_add_goal_dialog) \
                            .props('flat dense no-caps color=primary') \
                            .classes('text-caption')

                    goals_bullet_card(
                        "Cele YTD",
                        rev_target_year=data["rev_target_year"],
                        exp_budget_year=data["exp_budget_year"],
                        rev_actual_ytd=data["rev_actual_ytd"],
                        exp_actual_ytd=data["exp_actual_ytd"],
                        month_index=data["month_index"],
                        unit=data["unit"],
                    )

                table_container.clear()
                with table_container:
                    await render_goals_table(wallet, uid=uid, on_refresh=refresh_dialog)

            year_sel.on('update:model-value', refresh_dialog)

    dlg.open()
    await refresh_dialog()
