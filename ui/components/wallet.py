from nicegui import ui
from storage.session_state import upsert_wallet, list_wallets, remove_wallet
import uuid
import logging

from schemas.wallet import WalletCreationResponse

logger = logging.getLogger(__name__)


def render_create_wallet_dialog(self):

    dlg = ui.dialog()
    with dlg:
        with ui.card().style('''
            max-width: 480px;
            padding: 48px 36px;
            border-radius: 24px;
            background: linear-gradient(180deg, #ffffff 0%, #f6f9ff 100%);
            box-shadow: 0 10px 24px rgba(15,23,42,.06);
            border: 1px solid rgba(2,6,23,.06);
        '''):

            with ui.column().classes('items-center justify-center').style('width: 100%'):

                ui.icon('account_balance_wallet').style(
                    '''
                    font-size: 48px;
                    color: #3b82f6;
                    background: #e6f0ff;
                    padding: 20px;
                    border-radius: 50%;
                    margin-bottom: 24px;
                    '''
                )

                ui.label('Utwórz nowy portfel').classes('text-h5 text-weight-medium q-mb-sm text-center')

                ui.label('Podaj krótką, rozpoznawalną nazwę. Pola z gwiazdką (*) są wymagane.')\
                    .classes('text-body2 text-grey-8 q-mb-xl text-center')
                    
                name = ui.input(placeholder='Nazwa portfela *')\
                    .props('filled clearable counter maxlength=40 input-class=text-center')\
                    .style('width: 100%').classes('q-mb-sm')

                ui.label('Wskazówka: użyj nazwy opisującej cel lub zakres, np. „Wspólne wydatki”.')\
                    .classes('text-caption text-grey-7 q-mb-lg text-center').style('padding: 0 20px;')
                    
                with ui.row().classes('justify-center q-gutter-md q-mt-md'):
                    
                    ui.button('Anuluj').props('no-caps flat').style('min-width: 100px; height: 44px; padding: 0 20px;'
                                                                    ).on_click(dlg.close)
                    submit_btn = ui.button('Utwórz', icon='add').props('no-caps color=primary').style(
                        'min-width: 120px; height: 44px; border-radius: 8px; padding: 0 20px;')
  
                    async def create():
                        nm = (name.value or '').strip()
                        if not nm:
                            ui.notify('Podaj nazwę portfela.', color='negative')
                            return
                        user_id = self.get_user_id()
                        if not user_id:
                            ui.notify('Nie poprawny user', color='negative')
                            return
                        
                        submit_btn.props('loading')
                        try:
                            res: WalletCreationResponse = await self.wallet_client.create_wallet(
                                name=nm,
                                user_id=user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
                            )
                            if not res:
                                ui.notify('Nie udało się utworzyć portfela (błąd usługi).', color='negative')
                                return
                            ui.notify(f"Portfel „{nm}” został utworzony.", color='positive')

                            upsert_wallet(res)
                            
                            ui.navigate.reload()
                                
                        finally:
                            submit_btn.props(remove='loading')
                        
                    submit_btn.on_click(create)

    def open_dialog():
        dlg.open()

    return open_dialog


def render_delete_wallet_dialog(self):
    """
    Render a dialog to delete one or more wallets.
    wallets: Iterable[WalletLike] where WalletLike has .id and .name (or keys 'id','name')
    Returns: callable open_dialog()
    """
    from nicegui import ui
    import uuid

    items = {}
    for w in list_wallets() or []:
        items[str(w.get('id'))] = w.get('name')

    dlg = ui.dialog()

    with dlg:
        with ui.card().style('''
            max-width: 520px;
            padding: 40px 32px;
            border-radius: 24px;
            background: linear-gradient(180deg, #ffffff 0%, #fff7f7 100%);
            box-shadow: 0 10px 24px rgba(15,23,42,.06);
            border: 1px solid rgba(220, 38, 38, .14);
        '''):

            with ui.column().classes('items-center justify-center').style('width: 100%'):

                ui.icon('delete_forever').style('''
                    font-size: 48px;
                    color: #ef4444;
                    background: #fee2e2;
                    padding: 20px;
                    border-radius: 50%;
                    margin-bottom: 20px;
                ''')

                ui.label('Usuń portfele').classes('text-h5 text-weight-medium q-mb-xs text-center')
                ui.label('Wybierz portfele do usunięcia. Tej operacji nie można cofnąć.'
                         ).classes('text-body2 text-grey-8 q-mb-md text-center')

                select = ui.select(
                    items,
                    label='Portfele',
                    multiple=True,
                    with_input=True,
                    clearable=True
                ).props('use-chips filled').style('width:100%').classes('q-mb-md')

                ui.label('Aby potwierdzić, wpisz: USUŃ').classes('text-caption text-grey-7 q-mb-xs')
                confirm = ui.input(placeholder='USUŃ').props('filled clearable input-class=text-center') \
                    .style('width: 100%').classes('q-mb-md')

                with ui.element('div').style('''
                    width:100%;
                    background:#fff1f2;
                    border:1px solid #ffe4e6;
                    color:#be123c;
                    border-radius:12px;
                    padding:10px 12px;
                    font-size:13px;
                    margin-bottom:12px;
                '''):
                    ui.html('''<b>Uwaga:</b> usunięcie portfela może spowodować usunięcie powiązanych danych
                    (transakcje, ustawienia). Upewnij się, że wybrałeś właściwe portfele.''')

                with ui.row().classes('justify-center q-gutter-md q-mt-sm'):
                    ui.button('Anuluj').props('no-caps flat').style(
                        'min-width: 110px; height: 44px; padding: 0 20px;').on_click(dlg.close)

                    delete_btn = ui.button('Usuń', icon='delete_forever') \
                        .props('no-caps color=negative').style(
                            'min-width: 140px; height: 44px; border-radius: 8px; padding: 0 20px;')

                    async def do_delete():
                        chosen = select.value or []
                        phrase = (confirm.value or '').strip().upper()

                        if not chosen:
                            ui.notify('Wybierz co najmniej jeden portfel.', color='warning')
                            return
                        if phrase != 'USUŃ':
                            ui.notify('Wpisz dokładnie: USUŃ', color='negative')
                            return
                        
                        user_id = self.get_user_id()
                        if not user_id:
                            ui.notify('Nie poprawny user', color='negative')
                            return

                        delete_btn.props('loading')
                        try:

                            ok = True
                            for wid in chosen:
                                try:
                                    res = await self.wallet_client.delete_wallet(
                                        wallet_id=(uuid.UUID(wid) if not isinstance(wid, uuid.UUID) else wid),
                                        user_id=user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
                                    )
                                    ok = res
                                except Exception as e:
                                    ok = False
                                    ui.notify(f'Nie udało się usunąć portfela (id={wid}): {e}', color='negative')

                            if ok:
                                ui.notify('Wybrane portfele zostały usunięte.', color='positive')
                                if hasattr(self, 'upsert_wallet'):
                                    try:
                                        for wid in chosen:
                                            remove_wallet(wid) 
                                    except Exception:
                                        pass
                                dlg.close()

                                ui.navigate.reload()
                        finally:
                            delete_btn.props(remove='loading')

                    delete_btn.on_click(do_delete)

    def open_dialog():
        dlg.open()

    return open_dialog