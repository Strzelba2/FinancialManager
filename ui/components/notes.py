from nicegui import ui
import uuid
import logging

logger = logging.getLogger(__name__)


def build_notes_dialog(wallet):
    """
    Build and return an async function that opens a 'My Note' dialog.

    The dialog loads the user's note from the backend when opened and allows saving
    (upsert) the note content via the wallet client.

    Args:
        wallet: Wallet/controller object providing:
            - get_user_id() -> uuid.UUID | str | None
            - wallet_client.get_my_note(user_id=uuid.UUID)
            - wallet_client.upsert_my_note(user_id=uuid.UUID, text=str)

    Returns:
        Async callable that opens the dialog and loads the current note.
    """
    logger.info("build_notes_dialog: init")
    dlg = ui.dialog()

    with dlg:
        with ui.card().style('''
            width: min(760px, 92vw);
            padding: 32px 28px 22px;
            border-radius: 24px;
            background: linear-gradient(180deg, #ffffff 0%, #f6f9ff 100%);
            box-shadow: 0 12px 30px rgba(15,23,42,.08);
            border: 1px solid rgba(15,23,42,.06);
        '''):

            with ui.row().classes('items-center q-gutter-md q-mb-md'):
                ui.icon('sym_o_edit_note').style('''
                    font-size: 40px;
                    color: #3b82f6;
                    background: #e6f0ff;
                    padding: 16px;
                    border-radius: 50%;
                ''')
                with ui.column().classes('q-gutter-xs'):
                    ui.label('Notatki').classes('text-h5 text-weight-medium')
                    ui.label('Jedna notatka dla użytkownika (autosave po “Zapisz”).') \
                        .classes('text-body2 text-grey-7')

            note_area = ui.textarea(
                placeholder='Twoje notatki…'
            ).props('autogrow outlined').classes('w-full')

            with ui.row().classes('justify-end q-gutter-sm q-mt-md'):
                ui.button('Zamknij', on_click=dlg.close).props('no-caps flat') \
                    .style('min-width: 110px; height: 40px;')
                save_btn = ui.button('Zapisz', icon='save').props('no-caps color=primary') \
                    .style('min-width: 120px; height: 40px; border-radius: 10px;')

    async def open_notes() -> None:
        """
        Load the current user's note and open the dialog.
        """
        
        user_id = wallet.get_user_id()
        if not user_id:
            ui.notify('Niepoprawny user.', color='negative', timeout=0, close_button='OK')
            return
        uid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))

        try:
            obj = await wallet.wallet_client.get_my_note(user_id=uid)
            
            note_area.value = obj.text if obj else ''
            note_area.update()
        except Exception:
            logger.exception(f"open_notes: failed to load note user_id={uid}")
            ui.notify("Nie udało się wczytać notatki.", color="negative")
            return

        dlg.open()

    async def save_note() -> None:
        """
        Save (upsert) the note for current user.
        """
        
        user_id = wallet.get_user_id()
        if not user_id:
            ui.notify('Niepoprawny user.', color='negative', timeout=0, close_button='OK')
            return
        uid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))

        save_btn.props('loading')
        try:
            res = await wallet.wallet_client.upsert_my_note(user_id=uid, text=str(note_area.value or ''))
            if not res:
                ui.notify('Nie udało się zapisać notatki.', color='negative', timeout=0, close_button='OK')
                return
            ui.notify('Zapisano notatkę.', color='positive')
        except Exception:
            logger.exception(f"save_note: exception during upsert user_id={uid}")
            ui.notify("Błąd zapisu notatki.", color="negative", timeout=0, close_button="OK")
        finally:
            save_btn.props(remove='loading')

    save_btn.on_click(save_note)

    return open_notes