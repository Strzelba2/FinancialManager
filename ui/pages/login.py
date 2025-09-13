
from nicegui import ui
import logging
from fastapi import Request
from starlette.responses import RedirectResponse
import httpx
from components.navbar_footer import nav, footer
from static.style import add_style
from utils.utils import generate_csrf_token, handle_api_error
from utils.validators import is_valid_email, is_valid_password
from exceptions import UnauthorizedError


logger = logging.getLogger(__name__)

pending_logins = {}


class LoginForm:
    def __init__(self, request):
        
        self.headers = request.headers
        self.cookies = request.cookies
        self.client = request.client
        self.query_params = request.query_params
        self.token = generate_csrf_token()
        
        self.dialog = ui.dialog()
        self.already_activated = self.str_to_bool(self.query_params.get("already_activated", None))
        logger.info(f"already_activated init:  {self.already_activated}")

        with self.dialog, ui.card().classes('q-pa-xl q-ma-md rounded-borders shadow-10'):
            if self.already_activated:
                logger.info(f"already_activated state:  {self.already_activated}")
                ui.label("Your account has already been activated. You can log in now.."
                         ).classes('text-h6 text-center q-mb-md')
            else:
                ui.label("Probably your link has expired please try to register some time later.."
                         ).classes('text-h6 text-center q-mb-md')
            ui.button('OK', on_click=self.close_popup).props('unelevated color="primary"'
                                                             ).classes('full-width q-mt-md')
        self.build_ui()
        
        if self.already_activated is not None:
            self.dialog.open()
  
    def close_popup(self):
        self.dialog.close()
        ui.navigate.to('/login')
        
    def create_headers(self):
        headers = dict(self.headers)
        headers['X-Forwarded-For'] = self.client.host
        headers["Referer"] = "http://wallet.localhost:8081/login/"
        headers["Accept"] = "application/json"
        return headers
        
    def build_ui(self):

        with ui.element('div').classes('main-content'):
            with ui.element('div').classes('centered-content'):
                with ui.element('div').style(
                        '''
                        max-width: 450px; margin: 8% auto 8% auto; position: relative;
                        background: rgba(255,255,255,0.95);
                        border-radius: 24px;
                        box-shadow: 0 6px 24px rgba(44,76,124,0.13);
                        padding: 48px 38px 38px 38px;
                        text-align: center;
                        overflow: hidden;
                        '''
                        ):
                    ui.html('''
                    <img src="https://img.icons8.com/color/96/000000/lock--v1.png"
                        style="position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%);
                                opacity: 0.06; pointer-events: none; z-index: 0; width: 260px;">
                    ''')
                    ui.html("""
                        <div style="
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            flex-direction: column;
                            gap: 10px;
                            margin-bottom: 28px;
                        ">
                        <span style="
                            font-size: 2em;
                            font-weight: 700;
                            color: #008080;
                            letter-spacing: 1px;
                            text-shadow: 0 2px 6px rgba(44,76,124,0.07);
                        ">Logowanie</span>

                        <span class="material-icons" style="
                            font-size: 2.3em;
                            color: #008080;
                            opacity: .8;
                        ">login</span>
                        </div>
                        """)
                    with ui.element('q-form'):
                        with ui.row().classes('items-center w-full'):
                            ui.html('<span class="material-icons" style="color:#008080;'
                                    'font-size: 1.5em;">alternate_email</span>')
                            self.email = ui.input('Email').classes('w-full text-lg q-py-md').props('dense')
                        with ui.row().classes('items-center w-full'):
                            ui.html('<span class="material-icons" style="color:#008080; font-size: 1.5em;">lock</span>')
                            self.password = ui.input('Hasło', password=True).classes('w-full text-lg q-py-md').props('dense')
                        ui.html(f'<input type="hidden"  id="csrf_token" value="{self.token}">')

                        ui.button('Zaloguj się').classes('w-full q-mt-md').props('type="submit"'
                                                                                 ).on('click.prevent', self.do_login)
       
    async def confirm_login(self, response):
        result = await self.dialog
        if result == 'Yes' or result is None:
            
            pending_logins[self.client.host] = {
                'sessionid': response.cookies.get('sessionid', ''),
                'hmac': response.cookies.get('hmac_token', '')
            }

            ui.navigate.to('/finalize-login')
   
    async def do_login(self):
        if not all([self.email.value, self.password.value]):
            ui.notify('Wszystkie pola są wymagane!', color='negative')
            return
        
        email_msg = is_valid_email(self.email.value)
        if email_msg:
            ui.notify(email_msg, color='negative')
            return
        
        password_msg = is_valid_password(self.password.value)
        if password_msg:
            ui.notify(password_msg, color='negative')
            return
        
        csrf_token = await ui.run_javascript(' document.getElementById("csrf_token").value')
        
        if csrf_token != self.token:
            raise UnauthorizedError("CSRF validation failed")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://session-auth:8000/login/",
                    json={
                        "email": self.email.value,
                        "password": self.password.value,
                    },
                    headers=self.create_headers(),
                    cookies=self.cookies,
                    timeout=10
                )
            if response.status_code == 200:
                logger.info(f"Received cookies: {response.cookies}")
                logger.info(f"response: {response}")
                with ui.dialog() as self.dialog, ui.card().classes('q-pa-xl q-ma-md rounded-borders shadow-10'):
                    ui.label(f'Zalogowałeś się:({self.email.value})').classes('text-h6 text-center q-mb-md')
                    ui.button('OK', on_click=lambda: self.dialog.submit('Yes')
                              ).props('unelevated color="primary"').classes('full-width q-mt-md')

                await self.confirm_login(response)
            else:
                error_text = handle_api_error(response)
                ui.notify(f'Logowanie nieudane:\n{error_text}', color='negative', close_button=True, multi_line=True)
        except Exception as e:
            ui.notify(f'Błąd połączenia: {e}', color='negative')
                    
    def str_to_bool(self, value: str) -> bool | None:
        if value is None:
            return None
        value = value.lower()
        if value in ('true', '1', 'yes'):
            return True
        elif value in ('false', '0', 'no'):
            return False
        return None


@ui.page('/login')
def login(request: Request):
    add_style()
    nav("Login")
    LoginForm(request)
    footer()
    
    
@ui.page('/finalize-login')
def finalize_login(request: Request):
    logger.info("finalize_login")

    cookie_data = pending_logins.pop(request.client.host, {})
    logger.info(f"cookie_data: {cookie_data}")
    logger.info(f"request.client.host: {request.client.host}")
    
    session_id = cookie_data.get('sessionid', '')
    hmac_token = cookie_data.get('hmac', '')

    response = RedirectResponse(url='/wallet')
    response.set_cookie(
        key='sessionid',
        value=session_id,
        httponly=True,
        samesite='Lax',
    )
    response.set_cookie(
        key='hmac',
        value=hmac_token,
        httponly=True,
        samesite='Lax',
    )

    return response
