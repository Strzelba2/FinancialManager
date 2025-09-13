
from nicegui import ui
import logging
from fastapi import Request
import httpx

from utils.utils import handle_api_error


logger = logging.getLogger(__name__)


def create_headers(request):
    headers = dict(request.headers)
    headers['X-Forwarded-For'] = request.client.host
    headers["Accept"] = "application/json"
    return headers


@ui.page('/logout')
async def logout(request: Request):
    
    dialog = ui.dialog()
    
    async def confirm_logout(self):
        result = await dialog
        if result == 'Yes' or result is None:
            ui.navigate.to('/login')
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://session-auth:8000/logout/",
                headers=create_headers(request),
                cookies=request.cookies,
                timeout=10
            )
        if response.status_code == 200:
            logger.info(f"Received cookies: {response.cookies}")
            logger.info(f"response: {response}")
            with ui.dialog() as dialog, ui.card().classes('q-pa-xl q-ma-md rounded-borders shadow-10'):
                ui.label('Wylogowałeś się').classes('text-h6 text-center q-mb-md')
                ui.button('OK', on_click=lambda: dialog.submit('Yes')
                          ).props('unelevated color="primary"').classes('full-width q-mt-md')

            await confirm_logout(response)
        else:
            error_text = handle_api_error(response)
            ui.notify(f'Wylogowanie nieudane:\n{error_text}', color='negative', close_button=True, multi_line=True)
    except Exception as e:
        ui.notify(f'Błąd połączenia: {e}', color='negative')
