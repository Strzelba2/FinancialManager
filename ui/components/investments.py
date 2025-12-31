from nicegui import ui
import uuid
from typing import Dict, Any, List
from datetime import datetime
from decimal import Decimal, InvalidOperation
import logging

from schemas.wallet import Currency, PropertyType, RealEstateOut, MetalHoldingOut, MetalType
from utils.money import (change_currency_to, format_pl_amount, parse_amount)
from utils.utils import build_missing_price_message, is_current_account, to_uuid
from .date import attach_date_time_popups

logger = logging.getLogger(__name__)


TROY_OUNCE_G = Decimal("31.1034768") 


def show_sell_metal_dialog(wallet, row: dict, metal_rows, on_refresh=None) -> None:
    """
    Open dialog for selling an existing metal holding.

    Args:
        wallet: Wallet page/controller with `get_user_id()` and `wallet_client`.
        row: Table row dict containing at least `id` and `wallet_id`.
        metal_rows: Iterable of MetalHoldingOut-like objects used to resolve the holding object.
        on_refresh: Optional async callback to refresh parent UI after success.

    Returns:
        None. Opens a NiceGUI dialog.
    """
    user_id = wallet.get_user_id()
    mh_id = to_uuid(row["id"])

    mh = next((x for x in (metal_rows or []) if str(x.id) == str(mh_id)), None)
    if mh is None:
        logger.warning(f"show_sell_metal_dialog: metal holding not found mh_id={mh_id}")
        ui.notify("Metal holding not found.", color="negative")
        return

    total_grams = Decimal(str(mh.grams or "0"))
    cost_ccy = str(mh.cost_currency or wallet.view_currency.value or "PLN")

    acc_map: dict[str, str] = {}
    for w in (wallet.wallets or []):
        if str(w.id) == str(row.get("wallet_id") or ""):
            wallet_name = w.name

            accounts = getattr(w, "accounts", None) or []
            acc_map = {
                str(a.id): a.name
                for a in accounts
                if is_current_account(a)
            }
            break

    dlg = ui.dialog()
    with dlg:
        with ui.card().style("""
            max-width: 520px;
            padding: 28px 26px 18px;
            border-radius: 18px;
            background: #fff;
            border: 1px solid rgba(148,163,184,.35);
            box-shadow: 0 10px 24px rgba(15,23,42,.06);
        """):
            ui.label(f"Sell metal: {mh.metal}").classes("text-subtitle1 text-weight-medium")
            ui.label(f"Available: {total_grams} g | Currency: {cost_ccy}") \
                .classes("text-caption text-grey-7 q-mb-md")

            grams_in = ui.input("Grams to sell *", value=str(total_grams), placeholder="e.g. 10.5") \
                .props("filled dense clearable inputmode=decimal").style("width:100%")

            proceeds_in = ui.input("Sale proceeds *", placeholder="e.g. 3500.00") \
                .props("filled dense clearable inputmode=decimal").style("width:100%").classes("q-mb-sm")

            currency_sel = ui.select([c.value for c in Currency], value=cost_ccy, label="Currency") \
                .props("filled dense").style("width:100%").classes("q-mb-sm")

            occurred_at = ui.input('Date *').props('filled').style('width:100%')
            attach_date_time_popups(occurred_at)

            if acc_map:
                dep_acc = ui.select(acc_map, label="Deposit account *") \
                    .props("filled clearable use-input").style("width:100%").classes("q-mb-md")
            else:
                ui.notify(f"Proszę stworzyć konto bankowe dla portfela: {wallet_name}", 
                          color='negative', timeout=0, close_button=True,)
                return
            
            create_tx = ui.checkbox("Create transaction").props("dense").classes("q-mb-md")

            sell_btn = ui.button("Sell", icon="attach_money") \
                .props("no-caps color=positive").style("min-width:140px; height:42px; border-radius:10px;")
            cancel_btn = ui.button("Cancel").props("no-caps flat") \
                .style("min-width:110px; height:42px;")

            async def do_sell() -> None:
                """
                Validate inputs and submit sell request to wallet service.
                """
                try:
                    grams = Decimal(str(grams_in.value or "0").replace(",", "."))
                except Exception:
                    ui.notify("Invalid grams.", color="negative")
                    return
                if grams <= 0 or grams > total_grams:
                    logger.info(
                        "show_sell_metal_dialog.do_sell: grams out of range "
                        f"mh_id={mh_id} grams={grams} total_grams={total_grams}"
                    )
                    ui.notify("Grams must be > 0 and <= available.", color="negative")
                    return

                raw = (proceeds_in.value or "").strip().replace(" ", "").replace(",", ".")
                try:
                    proceeds = Decimal(raw)
                except Exception:
                    logger.info(
                        "show_sell_metal_dialog.do_sell: invalid proceeds "
                        f"mh_id={mh_id} raw={proceeds_in.value!r}"
                    )
                    ui.notify("Invalid proceeds.", color="negative")
                    return
                if proceeds <= 0:
                    logger.info(f"show_sell_metal_dialog.do_sell: non-positive proceeds mh_id={mh_id} proceeds={proceeds}")
                    ui.notify("Proceeds must be > 0.", color="negative")
                    return

                try:
                    deposit_account_id = to_uuid(str(dep_acc.value).strip())
                except Exception:
                    logger.info(f"show_sell_metal_dialog.do_sell: invalid deposit_account_id value={dep_acc.value!r}")
                    ui.notify("Invalid deposit account.", color="negative")
                    return

                dt_val = None
                raw_dt = (occurred_at.value or "").strip()
                if raw_dt:
                    try:
                        dt_val = datetime.fromisoformat(raw_dt)
                    except Exception:
                        logger.info(f"show_sell_metal_dialog.do_sell: invalid occurred_at raw_dt={raw_dt!r}")
                        ui.notify("Invalid date/time format.", color="negative")
                        return

                sell_btn.props("loading")
                try:
                    ok, msg = await wallet.wallet_client.sell_metal_holding(
                        user_id=user_id,
                        metal_holding_id=mh_id,
                        deposit_account_id=deposit_account_id,
                        grams_sold=grams,
                        proceeds_amount=proceeds,
                        proceeds_currency=str(currency_sel.value),
                        occurred_at=dt_val,
                        create_transaction=bool(create_tx.value),
                    )

                    if not ok:
                        logger.error(f"show_sell_metal_dialog.do_sell: failed mh_id={mh_id} msg={msg!r}")
                        ui.notify(msg, type="negative")
                        return
                    ui.notify(msg, type="positive")
                    dlg.close()
                    if on_refresh:
                        await on_refresh()
                    else:
                        ui.navigate.reload()
                finally:
                    sell_btn.props(remove="loading")

            sell_btn.on_click(do_sell)
            cancel_btn.on_click(dlg.close)

            with ui.row().classes("justify-end q-gutter-sm"):
                cancel_btn
                sell_btn

    dlg.open()


def show_sell_property_dialog(wallet, row: dict, on_refresh=None) -> None:
    """
    Open dialog for selling a real estate property.

    Args:
        wallet: Wallet page/controller with `get_user_id()` and `wallet_client`.
        row: Table row dict containing at least `id`, `wallet_id`, `purchase_currency`, `purchase_price`.
        on_refresh: Optional async callback to refresh parent UI after success.

    Returns:
        None. Opens a NiceGUI dialog.
    """
    user_id = wallet.get_user_id()
    logger.info(f"show_sell_property_dialog: open user_id={user_id} row_id={row.get('id')!r}")

    property_id = uuid.UUID(str(row["id"]))
    purchase_ccy = str(row.get("purchase_currency") or wallet.view_currency.value or "PLN")
    purchase_price = Decimal(str(row.get("purchase_price") or "0"))
    
    acc_map: dict[str, str] = {}
    for w in (wallet.wallets or []):
        if str(w.id) == str(row.get("wallet_id") or ""):
            wallet_name = w.name

            accounts = getattr(w, "accounts", None) or []
            acc_map = {
                str(a.id): a.name
                for a in accounts
                if is_current_account(a)
            }
            break

    dlg = ui.dialog()
    with dlg:
        with ui.card().style("""
            max-width: 520px;
            padding: 28px 26px 18px;
            border-radius: 18px;
            background: #fff;
            border: 1px solid rgba(148,163,184,.35);
            box-shadow: 0 10px 24px rgba(15,23,42,.06);
        """):
            ui.label(f"Sell property: {row.get('name','')}").classes("text-subtitle1 text-weight-medium")

            ui.label(
                f"Purchase: {purchase_price} {purchase_ccy}"
            ).classes("text-caption text-grey-7 q-mb-md")

            proceeds_in = ui.input("Sale proceeds *", placeholder="e.g. 650000.00") \
                .props("filled dense clearable inputmode=decimal").style("width:100%")

            currency_sel = ui.select(
                options=[c.value for c in Currency], 
                value=purchase_ccy,
                label="Currency",
            ).props("filled dense").style("width:100%").classes("q-mb-sm")

            occurred_at = ui.input('Date *').props('filled').style('width:100%')
            attach_date_time_popups(occurred_at)

            if acc_map:
                dep_acc = ui.select(acc_map, label="Deposit account *") \
                    .props("filled clearable use-input").style("width:100%").classes("q-mb-md")
            else:
                ui.notify(f"Proszę stworzyć konto bankowe dla portfela: {wallet_name}", color='negative', timeout=0, close_button=True,)
                return
                    
            create_tx = ui.checkbox("Create transaction").props("dense").classes("q-mb-md")

            sell_btn = ui.button("Sell", icon="attach_money") \
                .props("no-caps color=positive").style("min-width:140px; height:42px; border-radius:10px;")
            cancel_btn = ui.button("Cancel").props("no-caps flat") \
                .style("min-width:110px; height:42px;")

            async def do_sell() -> None:
                """
                Validate inputs and submit property sell request.
                """
                logger.info(f"show_sell_property_dialog.do_sell: start property_id={property_id} ")
                raw = (proceeds_in.value or "").strip().replace(" ", "").replace(",", ".")
                try:
                    proceeds = Decimal(raw)
                except (InvalidOperation, TypeError):
                    ui.notify("Invalid sale proceeds.", color="negative")
                    return
                if proceeds <= 0:
                    logger.info(f"show_sell_property_dialog.do_sell: non-positive proceeds property_id={property_id} proceeds={proceeds}")
                    ui.notify("Sale proceeds must be > 0.", color="negative")
                    return

                try:
                    deposit_account_id = to_uuid(str(dep_acc.value).strip())
                except Exception:
                    logger.info(f"show_sell_property_dialog.do_sell: invalid deposit_account_id value={dep_acc.value!r}")
                    ui.notify("Invalid deposit account.", color="negative")
                    return

                dt_val = None
                raw_dt = (occurred_at.value or "").strip()
                if raw_dt:
                    try:
                        dt_val = datetime.fromisoformat(raw_dt)
                    except Exception:
                        logger.info(f"show_sell_property_dialog.do_sell: invalid occurred_at raw_dt={raw_dt!r}")
                        ui.notify("Invalid date/time. Use YYYY-MM-DD HH:MM or ISO format.", color="negative")
                        return

                sell_btn.props("loading")
                try:
                    ok, msg = await wallet.wallet_client.sell_real_estate(
                        user_id=user_id,
                        real_estate_id=property_id,
                        deposit_account_id=deposit_account_id,
                        proceeds_amount=proceeds,
                        proceeds_currency=str(currency_sel.value),
                        occurred_at=dt_val,
                        create_transaction=bool(create_tx.value),
                    )
                    if not ok:
                        logger.error(f"show_sell_property_dialog.do_sell: failed property_id={property_id} msg={msg!r}")
                        ui.notify(msg, type="negative")
                        return
                    ui.notify(msg, type="positive")
                    if on_refresh:
                        await on_refresh()
                    else:
                        ui.navigate.reload()
                finally:
                    sell_btn.props(remove="loading")

            sell_btn.on_click(do_sell)
            cancel_btn.on_click(dlg.close)

            with ui.row().classes("justify-end q-gutter-sm"):
                cancel_btn
                sell_btn

    dlg.open()


def show_add_metal_dialog(wallet, on_refresh=None) -> None:
    """
    Open dialog for adding a metal holding.

    Args:
        wallet: Wallet page/controller with `selected_wallet`, `view_currency`, and `wallet_client`.
        on_refresh: Optional async callback invoked after successful create.

    Returns:
        None. Opens a NiceGUI dialog.
    """

    wallets = wallet.selected_wallet or []
    if not wallets:
        logger.info("show_add_metal_dialog: no wallets to choose from")
        ui.notify("Brak portfeli do wyboru.", color="negative", timeout=0, close_button="OK")
        return

    view_ccy = wallet.view_currency.value or "PLN"

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
                ui.icon("sym_o_insights").style("""
                    font-size: 48px;
                    color: #3b82f6;
                    background: #e6f0ff;
                    padding: 20px;
                    border-radius: 50%;
                    margin-bottom: 18px;
                """)

                ui.label("Dodaj metal szlachetny").classes("text-h5 text-weight-medium q-mb-xs text-center")
                ui.label("Uzupełnij ilość i koszt bazowy. Pola z gwiazdką (*) są wymagane.")\
                    .classes("text-body2 text-grey-8 q-mb-lg text-center")

            wallet_options = {
                str(w.id): w.name
                for w in (wallets or [])
                if any(
                    (getattr(a, "account_type", None) == "CURRENT") or
                    (getattr(getattr(a, "account_type", None), "value", None) == "CURRENT")  
                    for a in (getattr(w, "accounts", None) or [])
                )
            }
            if not wallet_options:
                ui.notify(
                    "Proszę stworzyć konto bankowe typu Konto Bankowe dla portfela ", 
                    color='negative', timeout=0, 
                    close_button=True,
                    )
                return
            wallet_sel = ui.select(
                options=wallet_options,
                value=str(wallets[0].id),
                label="Portfel *",
            ).props("filled dense").style("width: 100%").classes("q-mb-sm")

            metal_sel = ui.select(
                options=[m.value for m in MetalType],
                value=(MetalType.GOLD.value if hasattr(MetalType, "GOLD") else list(MetalType)[0].value),
                label="Metal *",
            ).props("filled dense").style("width: 100%").classes("q-mb-sm")

            grams_in = ui.input(
                label="Ilość (g) *",
                placeholder="np. 12.345",
            ).props("filled dense").style("width: 100%").classes("q-mb-sm")

            cost_basis_in = ui.input(
                label="Koszt bazowy (opcjonalnie)",
                placeholder="np. 12000.00",
            ).props("filled dense").style("width: 100%").classes("q-mb-sm")

            currency_sel = ui.select(
                options=[c.value for c in Currency],
                value=view_ccy,
                label="Waluta kosztu (opcjonalnie)",
            ).props("filled dense").style("width: 100%").classes("q-mb-md")
                        
            with ui.row().classes('justify-end q-gutter-sm q-mt-md').style('width:100%'):
                submit_btn = ui.button('Dodaj', icon='add').props("no-caps color=primary")\
                    .style("min-width: 140px; height: 44px; border-radius: 10px; padding: 0 22px;")
                cancel_btn = ui.button("Anuluj").props("no-caps flat")\
                    .style("min-width: 110px; height: 44px; padding: 0 18px;")

            async def save() -> None:
                """
                Validate inputs and create metal holding via API.
                """
                try:
                    wallet_id = uuid.UUID(str(wallet_sel.value))
                except Exception:
                    logger.info(f"show_add_metal_dialog.save: invalid wallet_id value={wallet_sel.value!r}")
                    ui.notify("Niepoprawny portfel.", color="negative", timeout=0, close_button="OK")
                    return

                metal = str(metal_sel.value or "").strip()
                if not metal:
                    logger.info("show_add_metal_dialog.save: empty metal")
                    ui.notify("Wybierz metal.", color="negative", timeout=0, close_button="OK")
                    return

                try:
                    grams = parse_amount(grams_in.value)
                except Exception:
                    logger.info(f"show_add_metal_dialog.save: invalid grams raw={grams_in.value!r}")
                    ui.notify("Podaj poprawną ilość gramów.", color="negative", timeout=0, close_button="OK")
                    return

                if grams is None or grams <= 0:
                    logger.info(f"show_add_metal_dialog.save: non-positive grams grams={grams}")
                    ui.notify("Ilość gramów musi być > 0.", color="negative", timeout=0, close_button="OK")
                    return

                try:
                    cost_basis = parse_amount(cost_basis_in.value)
                except Exception:
                    logger.info(f"show_add_metal_dialog.save: invalid cost_basis raw={cost_basis_in.value!r}")
                    ui.notify("Niepoprawny koszt bazowy.", color="negative", timeout=0, close_button="OK")
                    return

                cost_currency = str(currency_sel.value or "").strip() or None
                if cost_basis is None:
                    cost_currency = None

                submit_btn.props("loading")
                user_id = wallet.get_user_id()
                try:
                    res = await wallet.wallet_client.create_metal_holding(
                        user_id=user_id,
                        wallet_id=wallet_id,
                        metal=metal,
                        grams=grams,
                        cost_basis=cost_basis,
                        cost_currency=cost_currency,
                    )
                    if not res:
                        ui.notify("Nie udało się dodać metalu.", color="negative", timeout=0, close_button="OK")
                        return

                    ui.notify("Dodano metal.", color="positive")
                    dlg.close()

                    ui.navigate.reload()
                        
                finally:
                    submit_btn.props(remove="loading")

            submit_btn.on_click(save)
            cancel_btn.on_click(dlg.close)

    dlg.open()


async def fetch_metal_rows(wallet) -> List[Dict[str, Any]]:
    """
    Fetch metal holdings rows for all selected wallets.

    Args:
        wallet: Wallet controller with `selected_wallet`, `get_user_id()`, `wallet_client`.

    Returns:
        List of MetalHoldingOut-like objects.
    """
    rows: List[Dict[str, Any]] = []
    user_id = wallet.get_user_id()
    for w in (wallet.selected_wallet or []):
        api_rows: List[MetalHoldingOut] = await wallet.wallet_client.list_metal_holdings(user_id=user_id, wallet_id=w.id)  # List[MetalHoldingOut]
        for mh in api_rows:
            rows.extend(api_rows)
    return rows


def show_sticky_warning(
    message: str,
    title: str = 'Uwaga',
    icon: str = 'sym_o_warning',
) -> None:
    dlg = ui.dialog()
    """
    Show a modal warning dialog that stays until user closes it.

    Args:
        message: Main warning message (supports newlines).
        title: Dialog title.
        icon: Quasar icon name.

    Returns:
        None. Opens a NiceGUI dialog.
    """

    with dlg:
        with ui.card().style('''
            max-width: 560px;
            padding: 26px 22px 18px;
            border-radius: 22px;
            background: linear-gradient(180deg, #fff7ed 0%, #ffffff 100%);
            box-shadow: 0 12px 30px rgba(15,23,42,.10);
            border: 1px solid rgba(245,158,11,.40);
        '''):
            with ui.row().classes('items-center q-gutter-sm q-mb-sm'):
                ui.icon(icon).style('''
                    font-size: 34px;
                    color: #f59e0b;
                    background: rgba(245,158,11,.12);
                    padding: 12px;
                    border-radius: 50%;
                ''')
                with ui.column().classes('q-gutter-xs'):
                    ui.label(title).classes('text-subtitle1 text-weight-medium').style('color:#92400e;')
                    ui.label('Wymagana akcja użytkownika').classes('text-caption').style('color:rgba(146,64,14,.8);')

            ui.label(message).classes('text-body2').style('color:#92400e; line-height:1.45; white-space:pre-line;')

            with ui.row().classes('justify-end q-mt-md'):
                ui.button('Rozumiem', on_click=dlg.close) \
                    .props('no-caps color=warning') \
                    .style('min-width: 120px; height: 40px; border-radius: 10px;')

    dlg.open()


def open_prices_dialog(wallet) -> None:
    """
    Open dialog to create a real-estate reference price (avg price per m²).

    Args:
        wallet: Wallet controller with `wallet_client`.

    Returns:
        None. Opens a NiceGUI dialog.
    """
    logger.info("open_prices_dialog: open")
    dlg = ui.dialog()

    with dlg:
        with ui.card().style('''
            max-width: 520px;
            padding: 44px 36px 28px;
            border-radius: 24px;
            background: linear-gradient(180deg, #ffffff 0%, #f6f9ff 100%);
            box-shadow: 0 12px 30px rgba(15,23,42,.08);
            border: 1px solid rgba(2,6,23,.06);
        '''):

            with ui.column().classes('items-center justify-center').style('width: 100%'):
                ui.icon('sym_o_home_work').style('''
                    font-size: 44px;
                    color: #3b82f6;
                    background: #e6f0ff;
                    padding: 18px;
                    border-radius: 50%;
                    margin-bottom: 18px;
                ''')

                ui.label('Średnie ceny za m²').classes('text-h5 text-weight-medium q-mb-xs text-center')

                ui.label(
                    'Dodaj nową wycenę referencyjną. Najnowszy wpis będzie używany do obliczenia wartości nieruchomości.'
                ).classes('text-body2 text-grey-8 q-mb-lg text-center').style('padding: 0 10px;')

                # Inputs container
                with ui.column().classes('q-gutter-sm').style('width: 100%;'):

                    # country + city in one row, responsive
                    with ui.row().classes('q-gutter-sm w-full'):
                        country = ui.input(
                            label='Kraj (ISO2)',
                            placeholder='PL',
                        ).props('filled clearable maxlength=2').classes('col-4')

                        city = ui.input(
                            label='Miasto (opcjonalnie)',
                            placeholder='Warszawa',
                        ).props('filled clearable').classes('col')

                    type_options = {t.name: t.value for t in PropertyType}
                    type_sel = ui.select(
                        type_options,
                        label='Typ nieruchomości',
                        value='APARTMENT',
                    ).props('filled map-options emit-value').classes('w-full')

                    currency_options = {c.name: c.value for c in Currency}
                    currency_sel = ui.select(
                        currency_options,
                        label='Waluta',
                        value='PLN',
                    ).props('filled map-options emit-value').classes('w-full')

                    price_m2 = ui.input(
                        label='Cena za 1 m²',
                        placeholder='12000',
                    ).props('filled clearable inputmode=decimal').classes('w-full')

                    ui.label(
                        'Wskazówka: możesz wpisać wartość z przecinkiem lub kropką, np. 12 345,50.'
                    ).classes('text-caption text-grey-7 q-mt-xs text-center').style('padding: 0 10px;')

                with ui.row().classes('justify-center q-gutter-md q-mt-lg'):
                    ui.button('Anuluj').props('no-caps flat').style(
                        'min-width: 110px; height: 44px; padding: 0 20px;'
                    ).on_click(dlg.close)

                    save_btn = ui.button('Zapisz', icon='save').props('no-caps color=primary').style(
                        'min-width: 140px; height: 44px; border-radius: 10px; padding: 0 20px;'
                    )

                    async def save() -> None:
                        """
                        Validate inputs and create a new reference price record.
                        """
                        ctry = (country.value or '').strip().upper() or None
                        cty = (city.value or '').strip() or None

                        if ctry and len(ctry) != 2:
                            ui.notify('Kod kraju powinien mieć 2 znaki (ISO2), np. PL.', color='negative')
                            return

                        raw = str(price_m2.value or '').strip()
                        raw = raw.replace(' ', '').replace(',', '.')
                        try:
                            val = Decimal(raw)
                        except Exception:
                            ui.notify('Podaj poprawną liczbę dla ceny za m².', color='negative')
                            return

                        if val < 0:
                            ui.notify('Cena za m² nie może być ujemna.', color='negative')
                            return

                        save_btn.props('loading')
                        try:
                            res = await wallet.wallet_client.create_real_estate_price(
                                country=ctry,
                                city=cty,
                                type_=str(type_sel.value),
                                currency=str(currency_sel.value),
                                avg_price_per_m2=val,
                            )
                            if not res:
                                ui.notify('Nie udało się zapisać ceny.', color='negative')
                                return

                            ui.notify('Zapisano cenę za m².', color='positive')
                            dlg.close()

                        finally:
                            save_btn.props(remove='loading')
                            ui.navigate.reload()

                    save_btn.on_click(save)

    dlg.open()


def show_add_property_dialog(wallet) -> None:
    """
    Open dialog to create a new real estate entry.

    Args:
        wallet: Wallet page/controller providing `wallets`, `get_user_id()`,
                and `wallet_client.create_real_estate(...)`.

    Returns:
        None. Opens a NiceGUI dialog.
    """
    logger.info("show_add_property_dialog: open")
    dlg = ui.dialog()
    
    all_wallets = wallet.wallets or []
    default_wallet_id = all_wallets[0].name if len(all_wallets) == 1 else None

    with dlg:
        with ui.card().style('''
            max-width: 520px;
            padding: 32px 28px;
            border-radius: 24px;
            background: linear-gradient(180deg, #ffffff 0%, #f6f9ff 100%);
            box-shadow: 0 10px 24px rgba(15,23,42,.06);
            border: 1px solid rgba(2,6,23,.06);
        '''):

            with ui.column().classes('items-center justify-center q-gutter-md').style('width: 100%'):

                ui.icon('sym_o_home').style(
                    '''
                    font-size: 40px;
                    color: #0ea5e9;
                    background: #e0f2fe;
                    padding: 16px;
                    border-radius: 50%;
                    '''
                )

                ui.label('Dodaj nieruchomość').classes(
                    'text-h6 text-weight-medium text-center'
                )

                ui.label(
                    'Uzupełnij podstawowe dane nieruchomości. Pola z gwiazdką (*) są wymagane.'
                ).classes('text-body2 text-grey-7 text-center')

                wallet_options = {
                    str(w.id): w.name
                    for w in (all_wallets or [])
                    if any(
                        (getattr(a, "account_type", None) == "CURRENT") or
                        (getattr(getattr(a, "account_type", None), "value", None) == "CURRENT")  # if enum
                        for a in (getattr(w, "accounts", None) or [])
                    )
                }
                if not wallet_options:
                    ui.notify(
                        "Proszę stworzyć konto bankowe typu Konto Bankowe dla portfela ", 
                        color='negative', timeout=0, 
                        close_button=True,
                        )
                    return
                
                wallet_select = ui.select(
                    wallet_options,
                    value=str(default_wallet_id) if default_wallet_id else None,
                    label='Portfel *',
                ).props('filled dense').style('width:100%')

                name_input = ui.input('Nazwa nieruchomości *') \
                    .props('filled clearable counter maxlength=80') \
                    .style('width: 100%')

                with ui.row().classes('w-full q-gutter-sm'):
                    country_input = ui.input('Kraj (ISO2)').props('filled').classes('col')
                    city_input = ui.input('Miasto').props('filled').classes('col')

                type_options = {t.name: t.value for t in PropertyType}
                type_select = ui.select(
                    type_options,
                    label='Typ nieruchomości *',
                ).props('filled dense').style('width:100%')

                with ui.row().classes('w-full q-gutter-sm'):
                    area_input = ui.input('Powierzchnia (m²)').props('filled').classes('col')
                    price_input = ui.input('Cena zakupu *').props('filled').classes('col')

                currency_options = {c.name: c.value for c in Currency}
                currency_select = ui.select(
                    currency_options,
                    label='Waluta zakupu *',
                ).props('filled dense').style('width:100%')

                with ui.row().classes('justify-end q-gutter-sm q-mt-md').style('width:100%'):
                    ui.button('Anuluj', on_click=dlg.close) \
                        .props('no-caps flat') \
                        .style('min-width: 100px; height: 40px;')
                    submit_btn = ui.button('Dodaj', icon='add') \
                        .props('no-caps color=primary') \
                        .style('min-width: 120px; height: 40px;')

                async def create_real_estate_action() -> None:
                    """
                    Validate inputs and create real estate via wallet service.
                    """
                    wid = wallet_select.value or None
                    nm = (name_input.value or '').strip()
                    if not wid or not nm:
                        logger.info(f"show_add_property_dialog.create: missing required fields wid={wid!r} nm={nm!r}")
                        ui.notify('Wybierz portfel i podaj nazwę.', color='negative')
                        return
                    try:
                        wallet_id = uuid.UUID(str(wid))
                    except ValueError:
                        logger.info(f"show_add_property_dialog.create: invalid wallet_id wid={wid!r}")
                        ui.notify('Niepoprawny portfel.', color='negative')
                        return

                    try:
                        price = Decimal((price_input.value or '').replace(',', '.'))
                    except (InvalidOperation, TypeError):
                        logger.info(f"show_add_property_dialog.create: invalid purchase_price raw={price_input.value!r}")
                        ui.notify('Niepoprawna cena zakupu.', color='negative')
                        return

                    area_val: Decimal | None = None
                    raw_area = (area_input.value or '').strip()
                    if raw_area:
                        try:
                            area_val = Decimal(raw_area.replace(',', '.'))
                        except InvalidOperation:
                            logger.info(f"show_add_property_dialog.create: invalid area_m2 raw_area={raw_area!r}")
                            ui.notify('Niepoprawna powierzchnia (m²).', color='negative')
                            return

                    type_val = type_select.value
                    ccy_val = currency_select.value

                    submit_btn.props('loading')
                    
                    payload: Dict[str, Any] = {
                        "name": nm,
                        "country": (country_input.value or '').strip() or None,
                        "city": (city_input.value or '').strip() or None,
                        "type": type_val,
                        "area_m2": str(area_val),
                        "purchase_price": str(price),
                        "purchase_currency": ccy_val,
                        "wallet_id": str(wallet_id),
                    }
                    try:
                        user_id = wallet.get_user_id()
                        res = await wallet.wallet_client.create_real_estate(
                            user_id=user_id,
                            payload=payload,
                        )
                        if not res:
                            ui.notify('Nie udało się dodać nieruchomości.', color='negative')
                            return

                        ui.notify('Nieruchomość została dodana.', color='positive')
                        dlg.close()
                        ui.navigate.reload()
                    finally:
                        submit_btn.props(remove='loading')

                submit_btn.on_click(create_real_estate_action)

    dlg.open()


def render_empty_assets_placeholder(message: str) -> None:
    """
    Render a simple empty-state placeholder for assets sections.

    Args:
        message: Message displayed to the user.

    Returns:
        None.
    """
    with ui.row().classes(
        'items-center text-grey-7 justify-center w-full'
    ).style('padding:10px 0;'):
        with ui.column().classes('items-center justify-center q-gutter-xs'):
            ui.icon('sym_o_home_work').classes('text-h5 text-grey-5')
            ui.label(message).classes('text-caption text-grey-6')


async def render_properties_table(wallet, on_refresh=None) -> None:
    """
    Render an editable properties table (real estate) using wallet service data.

    For each property we try to fetch a latest price-per-m2 reference; if missing,
    we fall back to purchase price and collect missing-price info into `wallet.missing_price`.

    Args:
        wallet: Wallet controller providing `selected_wallet`, `view_currency`, FX rates,
                and `wallet_client` methods.
        on_refresh: Optional async callback to rerender after update.

    Returns:
        None. Renders UI elements.
    """
    wallets = wallet.selected_wallet or []

    view_ccy = wallet.view_currency.value or "PLN"
    rows: List[Dict[str, Any]] = []

    missing_price = []
    user_id = wallet.get_user_id()
    
    for w in wallets:
        api_rows: List[RealEstateOut] = await wallet.wallet_client.list_real_estates(user_id=user_id, wallet_id=w.id)
        for p in api_rows:
            purchase_ccy = p.purchase_currency or view_ccy
            price = await wallet.wallet_client.get_latest_real_estate_price(
                type_=str(p.type),
                country=p.country,
                city=p.city,
                currency=p.purchase_currency or view_ccy,
            )

            if price and p.area_m2: 
                base_value = Decimal(p.area_m2) * price.avg_price_per_m2
            else:
                missing_price.append((p.type, p.city))
                base_value = Decimal(p.purchase_price)
                
            purchase_price = Decimal(str(p.purchase_price or "0"))

            val_view: Decimal = change_currency_to(
                amount=base_value,
                view_currency=view_ccy,
                transaction_currency=purchase_ccy,
                rates=wallet.currency_rate,
            )

            rows.append(
                {
                    "id": p.id,
                    "wallet_id": p.wallet_id,
                    "wallet": w.name,
                    "name": p.name,
                    "country": p.country,
                    "city": p.city,
                    "type": p.type,
                    "area_m2": f"{p.area_m2} m²",
                    "purchase_price": purchase_price,
                    "purchase_currency": purchase_ccy,
                    "value_view": float(val_view),
                    "value_fmt": f"{format_pl_amount(val_view, decimals=0)} {view_ccy}",
                }
            )
            
    wallet.missing_price = missing_price

    columns = [
        {"name": "name",   "label": "Nieruchomość", "field": "name", "align": "left"},
        {"name": "area_m2", "label": "Powierzchnia", "field": "area_m2", "align": "center"},
        {"name": "value_fmt",
         "label": f"Wartość ({view_ccy})",
         "field": "value_fmt",
         "align": "right"},
        {"name": "actions", "label": "", "field": "actions", "align": "right"},
    ]

    def open_add_property_dialog() -> None:
        """Open 'add property' dialog."""
        logger.debug("render_properties_table: open_add_property_dialog")
        show_add_property_dialog(wallet)

    async def handle_save(row: Dict[str, Any]) -> None:
        """
        Persist edits (currently: property name only).

        Args:
            row: Table row dict.
        """
        try:
            re_id = to_uuid(str(row["id"]))
        except ValueError:
            ui.notify('Niepoprawne ID nieruchomości.', color='negative')
            return

        name = (row.get("name") or "").strip()
        if not name:
            logger.info(f"render_properties_table.handle_save: invalid re_id row_id={row.get('id')!r}")
            ui.notify('Nazwa nieruchomości nie może być pusta.', color='negative')
            return

        res = await wallet.wallet_client.update_real_estate(
            user_id=user_id,
            real_estate_id=re_id,
            name=name,
        )
        if not res:
            ui.notify('Nie udało się zaktualizować nieruchomości.', color='negative')
            return

        logger.info(f"render_properties_table.handle_save: succeeded re_id={re_id}")
        ui.notify('Nieruchomość została zaktualizowana.', color='positive')
        if on_refresh:
            await on_refresh()
        else:
            ui.navigate.reload()

    async def handle_delete(row: Dict[str, Any]) -> None:
        """
        Delete a property.

        Args:
            row: Table row dict.
        """
        try:
            re_id = to_uuid(str(row["id"]))
        except ValueError:
            logger.info(f"render_properties_table.handle_delete: invalid re_id row_id={row.get('id')!r}")
            ui.notify('Niepoprawne ID nieruchomości.', color='negative')
            return

        ok = await wallet.wallet_client.delete_real_estate(user_id=user_id, real_estate_id=re_id)
        if not ok:
            logger.error(f"render_properties_table.handle_delete: delete failed")
            ui.notify('Nie udało się usunąć nieruchomości.', color='negative')
            return

        ui.notify('Nieruchomość została usunięta.', color='positive')
        ui.navigate.reload()

    with ui.card().classes('w-full').style('''
        border-radius: 16px;
        background: #ffffff;
        border: 1px solid rgba(148,163,184,.35);
        box-shadow: 0 4px 10px rgba(15,23,42,.03);
        padding: 12px 14px 10px;
    '''):

        with ui.row().classes('items-center justify-between q-mb-xs w-full'):
            with ui.row().classes('items-center q-gutter-sm'):
                ui.icon('sym_o_home').classes('text-grey-6')
                ui.label('Nieruchomości').classes('text-sm text-weight-medium')

            with ui.row().classes('items-center q-gutter-xs'):
                ui.button('Ceny m²', on_click=lambda: open_prices_dialog(wallet)) \
                    .props('flat dense no-caps color=secondary') \
                    .classes('text-caption')
                ui.button('Dodaj', on_click=open_add_property_dialog) \
                    .props('flat dense no-caps color=primary') \
                    .classes('text-caption')
        if not rows:
            render_empty_assets_placeholder('Brak dodanych nieruchomości w portfelu.')
            return

        tbl = ui.table(columns=columns, rows=rows, row_key='id') \
            .props('flat dense separator=horizontal') \
            .classes('w-full text-body2')

        tbl.add_slot('body-cell-name', """
        <q-td :props="props">
          <q-input v-model="props.row.name"
                   dense
                   borderless
                   class="q-pa-none"
          />
        </q-td>
        """)

        tbl.add_slot('body-cell-actions', """
        <q-td :props="props">
        <q-btn flat dense icon="save" color="primary"
                @click="$parent.$emit('save', {row: props.row})" />
        <q-btn flat dense icon="delete" color="negative"
                @click="$parent.$emit('delete', {row: props.row})" />
        <q-btn flat dense icon="attach_money" color="positive"
            @click="$parent.$emit('sell', {row: props.row})" />
        </q-td>
        """)

        tbl.on('save', lambda e: handle_save(e.args['row']))
        tbl.on('delete', lambda e: handle_delete(e.args['row']))
        tbl.on('sell', lambda e: show_sell_property_dialog(wallet, e.args['row']))


async def render_metals_table(
    wallet,
    metal_rows: List[MetalHoldingOut],
    quotes_map: Dict[str, Any],  
    on_refresh=None,
) -> None:
    """
    Render an editable metals table using pre-fetched metal holdings and quotes.

    Args:
        wallet: Wallet controller providing `view_currency`, FX rates, and wallet_client.
        metal_rows: Metal holdings list (already fetched).
        quotes_map: Mapping symbol -> quote item (e.g. QuoteBySymbolItem).
        on_refresh: Optional async callback to rerender after actions.

    Returns:
        None.
    """
    view_ccy = wallet.view_currency.value or "PLN"

    rows: List[Dict[str, Any]] = []

    missing_metal_quotes: List[str] = []  
    user_id = wallet.get_user_id()

    for r in metal_rows:
        metal = r.metal
        grams: Decimal = r.grams

        symbol = r.quote_symbol
        quote = quotes_map.get(symbol) if symbol else None

        if quote and grams > 0:
            last_price = Decimal(str(getattr(quote, "price", "0")))
            base_value = (grams / TROY_OUNCE_G) * last_price
            base_ccy = "USD"
        else:
            if symbol:
                missing_metal_quotes.append(f"({metal}, {symbol})")
            base_value = r.cost_basis
            base_ccy = r.cost_currency or view_ccy

        val_view = change_currency_to(
            amount=base_value,
            view_currency=view_ccy,
            transaction_currency=base_ccy,
            rates=wallet.currency_rate,
        )
        rows.append({
            "id": r.id,
            "wallet_id": r.wallet_id,
            "metal": metal,
            "grams": format_pl_amount(r.grams, decimals=1),  
            "grams_fmt": format_pl_amount(r.grams, decimals=2),
            "value_fmt": f"{format_pl_amount(val_view, decimals=0)} {view_ccy}",
        })

    columns = [
        {"name": "metal", "label": "Metal", "field": "metal", "align": "left"},
        {"name": "grams_fmt", "label": "Ilość (g)", "field": "grams_fmt", "align": "center"},
        {"name": "value_fmt", "label": f"Wartość ({view_ccy})", "field": "value_fmt", "align": "center"},
        {"name": "actions", "label": "", "field": "actions", "align": "right"},
    ]

    def open_add_metal_dialog() -> None:
        """Open the add-metal dialog."""
        logger.debug("render_metals_table: open_add_metal_dialog")
        show_add_metal_dialog(wallet, on_refresh=on_refresh)

    async def handle_save(payload: Dict[str, Any]) -> None:
        """
        Persist edited grams for a metal holding.

        Args:
            payload: Event payload from NiceGUI table, containing 'row'.
        """
        row = payload.get("row") or {}
        try:
            mh_id = to_uuid(str(row["id"]))
        except Exception:
            logger.info(f"render_metals_table.handle_save: invalid mh_id row_id={row.get('id')!r}")
            ui.notify("Niepoprawne ID metalu.", color="negative")
            return

        try:
            grams = Decimal(str(row.get("grams_fmt") or "0").replace(",", "."))
        except Exception:
            ui.notify("Podaj poprawną ilość gramów.", color="negative")
            return
        if grams <= 0:
            logger.info(f"render_metals_table.handle_save: invalid grams mh_id={mh_id} raw={raw!r}")
            ui.notify("Ilość gramów musi być > 0.", color="negative")
            return

        res = await wallet.wallet_client.update_metal_holding(
            user_id=user_id,
            metal_holding_id=mh_id,
            grams=grams,
        )
        if not res:
            ui.notify("Nie udało się zaktualizować metalu.", color="negative")
            return

        ui.notify("Zapisano zmiany.", color="positive")
        ui.navigate.reload()

    async def handle_delete(payload: Dict[str, Any]) -> None:
        """
        Delete a metal holding.

        Args:
            payload: Event payload from NiceGUI table, containing 'row'.
        """
        row = payload.get("row") or {}
        try:
            mh_id = to_uuid(str(row["id"]))
        except Exception:
            logger.info(f"render_metals_table.handle_delete: invalid mh_id row_id={row.get('id')!r}")
            ui.notify("Niepoprawne ID metalu.", color="negative")
            return

        ok = await wallet.wallet_client.delete_metal_holding(user_id=user_id, metal_holding_id=mh_id)
        if not ok:
            ui.notify("Nie udało się usunąć metalu.", color="negative")
            return

        ui.notify("Metal został usunięty.", color="positive")
        ui.navigate.reload()

    with ui.card().classes("w-full").style("""
        border-radius: 16px;
        background: #ffffff;
        border: 1px solid rgba(148,163,184,.35);
        box-shadow: 0 4px 10px rgba(15,23,42,.03);
        padding: 12px 14px 10px;
    """):
        with ui.row().classes("items-center justify-between q-mb-xs w-full"):
            with ui.row().classes("items-center q-gutter-sm"):
                ui.icon("sym_o_insights").classes("text-grey-6")
                ui.label("Metale szlachetne").classes("text-sm text-weight-medium")

            ui.button("Dodaj", on_click=open_add_metal_dialog)\
                .props("flat dense no-caps color=primary")\
                .classes("text-caption")

        if not rows:
            render_empty_assets_placeholder("Brak dodanych metali szlachetnych w portfelu.")
            return

        tbl = ui.table(columns=columns, rows=rows, row_key="id")\
            .props("flat dense separator=horizontal")\
            .classes("w-full text-body2")

        tbl.add_slot("body-cell-grams_fmt", """
        <q-td :props="props" class="text-center">
          <q-input v-model="props.row.grams_fmt"
                   dense borderless 
                   class="q-pa-none"
                   input-class="text-center"
                   style="max-width:120px;margin:0 auto;" />
        </q-td>
        """)

        tbl.add_slot("body-cell-actions", """
        <q-td :props="props">
            <q-btn flat dense icon="save" color="primary"
                @click="$parent.$emit('save', {row: props.row})" />
            <q-btn flat dense icon="delete" color="negative"
                @click="$parent.$emit('delete', {row: props.row})" />
            <q-btn flat dense icon="attach_money" color="positive"
                @click="$parent.$emit('sell', {row: props.row})" />
        </q-td>
        """)

        tbl.on("save", lambda e: handle_save(e.args))
        tbl.on("delete", lambda e: handle_delete(e.args))
        tbl.on("sell", lambda e: show_sell_metal_dialog(wallet, e.args["row"], metal_rows))

        if missing_metal_quotes:
            show_sticky_warning(
                "Brak notowań dla: " + " / ".join(missing_metal_quotes),
                title="Brak wycen metali",
            )


async def show_investments_dialog(wallet) -> None:
    """
    Open investments dialog with totals and sections for properties and metals.

    Args:
        wallet: Wallet controller providing totals helpers, FX rates, and clients.

    Returns:
        None. Opens and renders a NiceGUI dialog.
    """
    logger.info("show_investments_dialog: open")
    dlg = ui.dialog()

    view_ccy = wallet.view_currency.value or "PLN"
    stocks_val = wallet.compute_stocks_total_in_view_ccy()
    props_val = wallet.compute_properties_total_in_view_ccy()
    metals_val = wallet.compute_metals_total_in_view_ccy()
    total = stocks_val + props_val + metals_val

    with dlg:
        with ui.card().style('''
            max-width: 920px;
            padding: 32px 32px 24px;
            border-radius: 24px;
            background: linear-gradient(180deg, #ffffff 0%, #f6f9ff 100%);
            box-shadow: 0 12px 30px rgba(15,23,42,.08);
            border: 1px solid rgba(15,23,42,.06);
        '''):

            with ui.row().classes('items-center q-gutter-ad q-mb-ad').style('width: 100%;'):
                ui.icon('sym_o_trending_up').style(
                    '''
                    font-size: 40px;
                    color: #16a34a;
                    background: #dcfce7;
                    padding: 16px;
                    border-radius: 50%;
                    '''
                )
                with ui.column().classes('q-gutter-xs'):
                    ui.label('Szczegóły inwestycji') \
                        .classes('text-h5 text-weight-medium')
                    ui.label('Łączna wartość portfela inwestycyjnego w wybranej walucie.') \
                        .classes('text-body2 text-grey-7')

            with ui.row().classes('w-full justify-center q-mt-xs q-mb-ad'):
                with ui.column().classes(
                    'items-center q-pa-md rounded-2xl bg-white'
                ).style(
                    'border:1px solid rgba(148,163,184,.5); min-width:260px; max-width:340px;'
                ):
                    ui.label('Łączna wartość inwestycji') \
                        .classes('text-xs text-grey-600')
                    ui.label(
                        f"{format_pl_amount(total, decimals=0)} {view_ccy}"
                    ).classes('text-h5 text-weight-semibold q-mb-xs text-center')

            with ui.row().classes('q-gutter-sd q-mb-sd w-full justify-center no-wrap'):
                def small_kpi(label: str, amount: Decimal) -> None:
                    with ui.column().classes(
                        'col q-pa-sm rounded-xl bg-white items-center'
                    ).style('border:1px solid rgba(148,163,184,.4); min-width:0;'):
                        ui.label(label).classes('text-xs text-grey-500')
                        ui.label(
                            f"{format_pl_amount(amount, decimals=0)} {view_ccy}"
                        ).classes('text-sm text-weight-semibold text-center')

                small_kpi('Akcje', stocks_val)
                small_kpi('Nieruchomości', props_val)
                small_kpi('Metale', metals_val)

            ui.separator().classes('q-my-sd')

            with ui.column().classes('w-full').style(
                '''
                max-height: 360px;
                overflow-y: auto;
                padding-right: 4px;
                '''
            ):
                with ui.row().classes('w-full justify-center q-mb-md'):
                    props_container = ui.column().classes('w-[95%] max-w-[720px]')
                    metals_container = ui.column().classes('w-[95%] max-w-[720px]')

            with ui.row().classes('justify-end q-mt-md').style('width: 100%;'):
                ui.button('Zamknij', on_click=dlg.close) \
                    .props('no-caps') \
                    .style('min-width: 110px; height: 40px;')
                    
            async def refresh_dialog() -> None:
                """
                Rerender properties + metals sections and refresh quotes.
                """
                logger.info("show_investments_dialog.refresh_dialog: start")
                props_container.clear()
                metals_container.clear()

                metal_rows: List[MetalHoldingOut] = await fetch_metal_rows(wallet)
                metal_symbols = [mh.quote_symbol for mh in metal_rows if mh.quote_symbol]
 
                quotes_map = await wallet.stock_client.get_latest_quotes_for_symbols(list(dict.fromkeys(metal_symbols)))

                with props_container:
                    await render_properties_table(wallet, on_refresh=refresh_dialog)
                with metals_container:
                    await render_metals_table(
                        wallet,
                        metal_rows=metal_rows,
                        quotes_map=quotes_map,
                        on_refresh=refresh_dialog,
                    )

    dlg.open()
    await refresh_dialog()
    
    if wallet.missing_price:
        show_sticky_warning(
            build_missing_price_message(wallet.missing_price),
            title="Brak cen m²",
        )
