import datetime
import uuid
import logging
from typing import Any, Callable, Dict, Optional

from nicegui import ui

from schemas.wallet import Currency
from .date import attach_date_time_popups

logger = logging.getLogger(__name__)


async def render_brokerage_event_form(
    self: Any,  
    container: Any,  
    brokerage_accounts: Dict[uuid.UUID, str],
    on_success: Callable[[], Any],  
    default_account_id: Optional[uuid.UUID] = None,
    default_mic: Optional[str] = None,
    default_symbol: Optional[str] = None,
) -> None:
    """
    Render the brokerage event creation form.

    The UI is rendered progressively:
    1) Select brokerage account
    2) Select market (MIC)
    3) Select instrument
    4) Fill event fields and submit

    Args:
        self: Page/controller instance providing `stock_client`, `wallet_client`,
              `get_user_id()`, and dialog open methods.
        container: NiceGUI container element to render into (will be cleared).
        brokerage_accounts: Mapping of brokerage account id -> display name.
        on_success: Async callback executed after a successful submit (e.g., reload page).
        default_account_id: Optional default brokerage account to preselect.
        default_mic: Optional default MIC to preselect.
        default_symbol: Optional default instrument symbol to preselect.

    Returns:
        None. Renders UI into `container`.
    """

    container.clear()

    with container:
        if not brokerage_accounts:
            with ui.element('div') as body:
                body.classes('items-center').style('width:100%; text-align:center;')

                ui.icon('account_balance_wallet') \
                    .classes('text-grey-7') \
                    .style('font-size:36px; margin-top:8px; display:block; margin-left:auto; margin-right:auto;')

                ui.label('Nie masz jeszcze żadnego konta maklerskiego.').classes('text-subtitle1 text-center')
                ui.label('Najpierw utwórz konto, a następnie dodaj transakcje.') \
                    .classes('text-body2 text-grey-7 text-center q-mb-md')

                with ui.row().classes('justify-center q-gutter-md q-mt-md').style('width:100%;'):
                    ui.button('Utwórz konto', icon='add').props('color=primary no-caps') \
                        .on_click(lambda: self.open_create_account_dialog())
                    ui.button('Anuluj').props('flat no-caps')
            return

        ui.label('Wybierz konto, rynek i instrument').classes('text-subtitle2 text-weight-medium q-mb-sm')

        dep_sel = ui.select(brokerage_accounts, label='Rachunek depozytowy (BROKERAGE) *') \
            .props('filled clearable use-input') \
            .style('width:420px')

        if default_account_id and default_account_id in brokerage_accounts:
            dep_sel.value = default_account_id

        market_slot = ui.element('div')
        instrument_slot = ui.element('div')
        form_slot = ui.element('div')

        market_sel = None
        instr_sel = None
        instruments: Dict[str, str] = {}

        async def load_markets_if_needed() -> None:
            """Load markets list into `market_sel` if it exists."""
            nonlocal market_sel
            try:
                market_sel.props('loading')
                data = await self.stock_client.get_markets()
                if not data:
                    ui.notify("Any stock market is not available")
                    return
                markets = {m.get("mic"): m.get("name") for m in (data or [])}
                market_sel.options = markets
                if default_mic and default_mic in markets:
                    market_sel.value = default_mic
                    on_market_change()
            except Exception:
                logger.exception("render_brokerage_event_form: failed to load markets")
                ui.notify("Failed to load markets", color="negative")
            finally:
                market_sel.props(remove='loading')

        async def load_instruments_for_market() -> None:
            """Load instruments for currently selected MIC into `instr_sel`."""
            nonlocal instruments, instr_sel
            mic = market_sel.value
            if not mic:
                instr_sel.set_options([])
                return
            
            logger.info(f"render_brokerage_event_form: loading instruments for mic={mic!r}")
            try:
                instr_sel.props('loading')
                data = await self.stock_client.list_instruments(mic=mic)
                if not data:
                    ui.notify(f"Any stock instrument for {mic} is not available")
                    return
                instruments = {m.get("symbol"): m.get("shortname") for m in (data or [])}
                instr_sel.options = instruments
                if default_symbol and default_symbol in instruments:
                    instr_sel.value = default_symbol
                    on_instr_change()
            except Exception:
                logger.exception(f"render_brokerage_event_form: failed to load instruments for mic={mic!r}")
                ui.notify("Failed to load instruments", color="negative")
            finally:
                instr_sel.props(remove='loading')

        def local_filter(e) -> None:
            """
            Local (client-side) filter for instrument select.
            """
            nonlocal instr_sel, instruments
            raw = e.args if isinstance(e.args, str) else (e.args[0] if isinstance(e.args, list) and e.args else "")
            query = (raw or '').strip().lower()
            if not query:
                instr_sel.set_options(instruments)
                return
            filtered = {k: v for k, v in instruments.items() if query in k.lower() or query in v.lower()}
            instr_sel.set_options(filtered)

        def on_dep_change() -> None:
            """Handle brokerage account change: show market selector."""
            nonlocal market_sel, instr_sel
            market_slot.clear()
            instrument_slot.clear()
            form_slot.clear()
            if not dep_sel.value:
                return
            
            logger.info(f"render_brokerage_event_form: selected account_id={dep_sel.value}")

            with market_slot:
                ui.label('Rynek *').classes('text-caption text-grey-7')
                market_sel = ui.select({}, label='Rynek *') \
                    .props('filled clearable use-input') \
                    .style('width:420px')
                market_sel.on('update:model-value', lambda *_: on_market_change())
                ui.timer(0.01, load_markets_if_needed, once=True)

        def on_market_change() -> None:
            """Handle market change: show instrument selector."""
            nonlocal instr_sel
            instrument_slot.clear()
            form_slot.clear()
            mic = market_sel.value if market_sel else None
            if not mic:
                logger.debug("render_brokerage_event_form: market cleared")
                return

            with instrument_slot:
                instr_sel = ui.select({}, label='Instrument *') \
                    .props('filled clearable use-input virtual-scroll') \
                    .style('width:420px')
                instr_sel.on('filter', local_filter)
                instr_sel.on('update:model-value', lambda *_: on_instr_change())
                ui.timer(0.01, load_instruments_for_market, once=True)

        def on_instr_change() -> None:
            """Handle instrument change: show event form fields."""
            form_slot.clear()
            instr_symbol = instr_sel.value if instr_sel else None
            if not instr_symbol:
                logger.debug("render_brokerage_event_form: instrument cleared")
                return

            logger.info(
                "render_brokerage_event_form: selected instrument "
                f"symbol={instr_symbol!r} name={instruments.get(instr_symbol)!r}"
            )
            
            with form_slot:
                kind = ui.select({'BUY': 'BUY', 'SELL': 'SELL', 'DIV': 'DIV'}, value='BUY', label='Rodzaj *') \
                    .props('filled clearable use-input') \
                    .style('width:420px')

                qty = ui.input(label='Ilość', value='0') \
                    .props('filled clearable use-input') \
                    .style('width:420px')

                price = ui.input(label='Cena / Kwota', value='0') \
                    .props('filled clearable use-input') \
                    .style('width:420px')

                currency = ui.select([c.value for c in Currency], value='PLN') \
                    .props('filled clearable use-input') \
                    .style('width:420px')

                trade_dt = ui.input('Data *', value=datetime.datetime.now().strftime('%Y-%m-%dT%H:%M')) \
                    .props('filled clearable use-input') \
                    .style('width:420px')
                attach_date_time_popups(trade_dt)

                with ui.row().classes('justify-center q-gutter-md q-mt-sm'):
                    submit_btn = ui.button('Post event', icon='addchart') \
                        .props('color=primary no-caps') \
                        .style('min-width:160px;height:44px;border-radius:8px')

                async def do_submit() -> None:
                    """Submit event creation request to wallet service."""
                    try:
                        payload = {
                            "brokerage_account_id": str(dep_sel.value),
                            "instrument_symbol": instr_symbol,
                            "instrument_mic": market_sel.value,
                            "instrument_name": instruments.get(instr_symbol),
                            "kind": kind.value,
                            "quantity": qty.value,
                            "price": price.value,
                            "currency": currency.value,
                            "split_ratio": "0",
                            "trade_at": trade_dt.value,
                        }
                        submit_btn.props('loading')
                        user_id = self.get_user_id()
                        
                        ok = await self.wallet_client.create_brokerage_event(user_id, payload)
                        if not ok:
                            logger.error(
                                "render_brokerage_event_form: submit failed "
                                f"user_id={user_id} account_id={dep_sel.value} mic={market_sel.value!r} symbol={instr_symbol!r}"
                            )
                            ui.notify('Nie udało się zapisać zdarzenia.', color='negative')
                            return
                        ui.notify('Zdarzenie maklerskie zapisane.', color='positive')
                        await on_success()
                    except Exception as e:
                        logger.exception(f"render_brokerage_event_form: submit error: {e}")
                        ui.notify(f'Error: {e}', color='negative')
                    finally:
                        submit_btn.props(remove='loading')

                submit_btn.on_click(do_submit)

        dep_sel.on('update:model-value', lambda *_: on_dep_change())

        if dep_sel.value:
            on_dep_change()
