from nicegui import ui
from schemas.wallet import Currency, AccountType
import uuid
import logging

logger = logging.getLogger(__name__)


def render_create_account_dialog(self, wallet_id: uuid.UUID):
    """
    Modal dialog for adding the first (or another) account to a wallet.
    
    Args:
    - wallet_id: UUID of the active wallet

    Returns: open_dialog() callable
    """
    dlg = ui.dialog()

    with dlg:
        with ui.card().style('''
            max-width: 560px;
            padding: 40px 32px;
            border-radius: 24px;
            background: linear-gradient(180deg, #ffffff 0%, #f6f9ff 100%);
            box-shadow: 0 10px 24px rgba(15,23,42,.06);
            border: 1px solid rgba(2,6,23,.06);
        '''):
            with ui.column().classes('items-center justify-center').style('width:100%'):
                ui.icon('account_balance').style('''
                    font-size: 48px;
                    color: #3b82f6;
                    background: #e6f0ff;
                    padding: 20px;
                    border-radius: 50%;
                    margin-bottom: 20px;
                ''')
                ui.label('Dodaj konto do portfela').classes('text-h5 text-weight-medium q-mb-xs text-center')
                ui.label('Wypełnij wymagane pola, reszta jest opcjonalna.'
                         ).classes('text-body2 text-grey-8 q-mb-md text-center')

                name = ui.input(label='Nazwa konta *', placeholder='np. mBank – ROR'
                                ).props('filled clearable counter maxlength=64 input-class=text-center'
                                        ).style('width:100%').classes('q-mb-sm')
                                
                account_type = {c.name: c.value for c in AccountType}
                t_select = ui.select(account_type, value="CURRENT", label='Typ *') \
                    .props('filled clearable use-input') \
                    .style('width:100%')
                    
                currents = {c.name: c.value for c in Currency}
                c_select = ui.select(currents, value="PLN", label='Waluta *') \
                    .props('filled clearable use-input') \
                    .style('width:100%')
                
                banks = {bank["id"]: bank["name"] for bank in self.banks}
                bank_id = ui.select(banks, label='Bank *') \
                    .props('filled clearable use-input') \
                    .style('width:100%')

                account_number = ui.input(label='Numer konta').props(
                    'filled clearable input-class=text-center '
                    'mask=NN-NNNN-NNNN-NNNN-NNNN-NNNN-NNNN '
                    'unmasked-value'
                    ).style('width:100%')

                with ui.row().classes('justify-center q-gutter-md q-mt-md'):
                    ui.button('Anuluj').props('no-caps flat').style(
                        'min-width: 110px; height: 44px;').on_click(dlg.close)

                    submit_btn = ui.button('Dodaj konto', icon='add') \
                        .props('no-caps color=primary').style(
                            'min-width: 140px; height: 44px; border-radius: 8px;')

                    async def do_create():
                        """
                        Validate inputs and call wallet service to create an account.
                        Shows NiceGUI notifications on errors/success.
                        """
                        nm = (name.value or '').strip()
                        if not nm:
                            ui.notify('Podaj nazwę konta.', color='negative')
                            return
                        
                        acc_type = t_select.value
                        ccy = c_select.value
                        bank = bank_id.value
                        if not acc_type or not ccy:
                            ui.notify('Wybierz typ i walutę.', color='negative')
                            return
                        
                        number = (account_number.value or '').strip()
                        if not number:
                            ui.notify('Podaj numer konta.', color='negative')
                            return
                        
                        user_id = self.get_user_id()
                        if not user_id:
                            ui.notify('Nie poprawny user', color='negative')
                            return

                        submit_btn.props('loading')
                        try:
                            payload = {
                                'name': nm,
                                'account_type': acc_type,
                                'currency': ccy,
                                'account_number': number,
                                'bank_id': bank,
                                'iban': f'PL{number}'
                            }
                            logger.info("Creating account")
                        
                            res = await self.wallet_client.create_account(user_id, wallet_id, payload)
                            if not res:
                                logger.warning("Create account failed")
                                ui.notify('Nie udało się utworzyć konta.', color='negative')
                                return
                            if isinstance(res, str):
                                logger.info("Create account conflict/detail: %s", res)
                                ui.notify(f'{res}', color='negative')
                                return
                            
                            logger.debug("Create account response validated: %r", res)

                            ui.notify(f'Konto „{nm}” dodane.', color='positive')
  
                            dlg.close()
                        except Exception as e:
                            logger.exception('Create account error')
                            ui.notify(f'Błąd: {e}', color='negative')
                        finally:
                            submit_btn.props(remove='loading')

                    submit_btn.on_click(do_create)

    def open_dialog():
        """Open the prepared Create Account dialog."""
        dlg.open()

    return open_dialog