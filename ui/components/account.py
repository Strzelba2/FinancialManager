from nicegui import ui
from schemas.wallet import Currency, AccountType
from storage.session_state import get_wallets, get_banks
from typing import Dict, Optional

import logging

logger = logging.getLogger(__name__)


def render_create_account_dialog(self):
    """
    Returns: open_dialog() callable that builds the dialog content at open-time.
    This prevents notifications from appearing during navbar initialization.
    """
    dlg = ui.dialog()

    with dlg:
        card = ui.card().style('''
            max-width: 560px;
            padding: 40px 32px;
            border-radius: 24px;
            background: linear-gradient(180deg, #ffffff 0%, #f6f9ff 100%);
            box-shadow: 0 10px 24px rgba(15,23,42,.06);
            border: 1px solid rgba(2,6,23,.06);
        ''')
        with card:
            header_col = ui.column().classes('items-center justify-center').style('width:100%')
            with header_col:
                ui.icon('account_balance').style('''
                    font-size: 48px;
                    color: #3b82f6;
                    background: #e6f0ff;
                    padding: 20px;
                    border-radius: 50%;
                    margin-bottom: 20px;
                ''')
                ui.label('Dodaj konto do portfela').classes('text-h5 text-weight-medium q-mb-xs text-center')
                ui.label('Wypełnij wymagane pola, reszta jest opcjonalna.').classes('text-body2 text-grey-8 q-mb-md text-center')

            body = ui.column().style('width:100%').classes('q-gutter-sm')

    def _fill_body():
        """Build the dialog contents depending on current state."""
        body.clear()

        wallets_map: Dict[str, str] = get_wallets()  
        wallet_count = len(wallets_map)

        if wallet_count == 0:
            with body.classes('items-center').style('width:100%; text-align:center;'):
                ui.icon('account_balance_wallet'
                        ).classes('text-grey-7'
                                  ).style('font-size:36px; margin-top:8px; display:block; margin-left:auto; margin-right:auto;')

                ui.label('Nie masz jeszcze żadnego portfela.').classes('text-subtitle1 text-center')

                ui.label('Najpierw utwórz portfel, a następnie dodaj konto.'
                         ).classes('text-body2 text-grey-7 text-center q-mb-md')

                with ui.row().classes('justify-center q-gutter-md q-mt-md').style('width:100%;'):
                    ui.button('Utwórz portfel', icon='add'
                              ).props('color=primary no-caps'
                                      ).on_click(lambda: (dlg.close(), self.open_create_wallet_dialog()))

                    ui.button('Anuluj').props('flat no-caps').on_click(dlg.close)
            return

        with body:
            name = (ui.input(label='Nazwa konta *', placeholder='np. mBank – ROR')
                    .props('filled clearable counter maxlength=64 input-class=text-center')
                    .style('width:100%')
                    )

            wallet_select = None
            single_wallet_id: Optional[str] = None

            if wallet_count == 1:
                single_wallet_id = next(iter(wallets_map.keys()))
                wallet_select = (
                    ui.select(wallets_map, value=single_wallet_id, label='Wallet *')
                    .props('filled use-input')
                    .style('width:100%')
                    .disable()
                )
            else:
                wallet_select = (ui.select(wallets_map, label='Wallet *')
                                 .props('filled clearable use-input')
                                 .style('width:100%')
                                 )

            account_type = {c.name: c.value for c in AccountType}
            t_select = (ui.select(account_type, value='CURRENT', label='Typ *')
                        .props('filled clearable use-input')
                        .style('width:100%')
                        )

            currencies = {c.name: c.value for c in Currency}
            c_select = (ui.select(currencies, value='PLN', label='Waluta *')
                        .props('filled clearable use-input')
                        .style('width:100%')
                        )
            
            banks = getattr(self, "banks", None)
            
            banks_map: Dict[str, str] = (
                {str(b.id): b.name for b in (banks or [])}
                if banks
                else get_banks()
            )
                
            bank_select = (ui.select(banks_map, label='Bank *')
                           .props('filled clearable use-input')
                           .style('width:100%')
                           )

            account_number = ui.input(label='Numer konta').props(
                'filled clearable input-class=text-center '
                'mask=NN-NNNN-NNNN-NNNN-NNNN-NNNN-NNNN '
                'unmasked-value'
            ).style('width:100%')

            with ui.row().classes('justify-center q-gutter-md q-mt-md'):
                cancel_btn = ui.button('Anuluj').props('no-caps flat').style('min-width:110px; height:44px;')
                submit_btn = (ui.button('Dodaj konto', icon='add')
                              .props('no-caps color=primary')
                              .style('min-width:140px; height:44px; border-radius:8px;')
                              )

                cancel_btn.on_click(dlg.close)

                async def do_create():
                    nm = (name.value or '').strip()
                    if not nm:
                        ui.notify('Podaj nazwę konta.', color='negative') 
                        return

                    acc_type = t_select.value
                    ccy = c_select.value
                    bank_id = bank_select.value
                    if not acc_type or not ccy:
                        ui.notify('Wybierz typ i walutę.', color='negative')
                        return

                    number = (account_number.value or '').strip()
                    if not number:
                        ui.notify('Podaj numer konta.', color='negative')
                        return

                    user_id = self.get_user_id()
                    if not user_id:
                        ui.notify('Niepoprawny użytkownik.', color='negative') 
                        return

                    if single_wallet_id is not None:
                        wid = single_wallet_id
                    else:
                        wid = wallet_select.value
                    if not wid:
                        ui.notify('Niepoprawny wallet.', color='negative')
                        return

                    submit_btn.props('loading')
                    try:
                        payload = {
                            'name': nm,
                            'account_type': acc_type,
                            'currency': ccy,
                            'account_number': number,
                            'bank_id': bank_id,
                            'iban': f'PL{number}',  
                        }
                        logger.info('Creating account for wallet_id=%s', wid)
                        res = await self.wallet_client.create_account(user_id, wid, payload)

                        if not res:
                            logger.warning('Create account failed')
                            ui.notify('Nie udało się utworzyć konta.', color='negative')
                            return

                        if isinstance(res, str):
                            logger.info('Create account detail: %s', res)
                            ui.notify(res, color='negative')
                            return

                        ui.notify(f'Konto „{nm}” dodane.', color='positive')
                        dlg.close()
                        ui.navigate.reload()  
                    except Exception:
                        logger.exception('Create account error')
                        ui.notify('Wystąpił błąd podczas tworzenia konta.', color='negative')
                    finally:
                        submit_btn.props(remove='loading')

                submit_btn.on_click(do_create)

    def open_dialog():
        _fill_body() 
        dlg.open()

    return open_dialog
