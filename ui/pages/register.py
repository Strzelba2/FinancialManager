from nicegui import ui
from fastapi import Request
import httpx
import logging

from components.navbar_footer import nav, footer
from static.style import add_style
from utils.validators import is_valid_email, is_valid_password
from utils.utils import generate_csrf_token, handle_api_error

logger = logging.getLogger(__name__)


class RegisterForm:
    def __init__(self, request):
        
        self.headers = request.headers
        self.cookies = request.cookies
        self.client = request.client
        self.token = generate_csrf_token()

        self.build_ui()
        
    def build_ui(self):
    
        with ui.element('div').classes('main-content'):
            with ui.element('div').classes('centered-content'):
                with ui.element('div').style(
                    '''
                    max-width: 500px; width: 100%;
                    background: rgba(255,255,255,0.97);
                    border-radius: 24px;
                    box-shadow: 0 6px 24px rgba(44,76,124,0.13);
                    padding: 48px 38px 38px 38px;
                    text-align: center;
                    position: relative;
                    overflow: hidden;
                    margin: 0;
                    '''
                ):
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
                        ">
                            Rejestracja
                        </span>

                        <span class="material-icons" style="
                            font-size: 2.3em;
                            color: #008080;
                            opacity: .8;
                        ">
                            person_add
                        </span>
                        </div>
                        """)
                    with ui.element('q-form'):
                        with ui.row().classes('items-center w-full'):
                            ui.html('<span class="material-icons" style="color:#008080; font-size: 1.5em;">person</span>')
                            self.first_name = ui.input('Imię').classes('w-full text-lg q-py-md'
                                                                       ).props('dense autocomplete="given-name"')
                        with ui.row().classes('items-center w-full'):
                            ui.html('<span class="material-icons" style="color:#008080; font-size: 1.5em;">badge</span>')
                            self.last_name = ui.input('Nazwisko').classes('w-full text-lg q-py-md'
                                                                          ).props('dense autocomplete="family-name"')
                        with ui.row().classes('items-center w-full'):
                            ui.html('<span class="material-icons" style="color:#008080; font-size: 1.5em;">person_outline</span>')
                            self.username = ui.input('Nazwa użytkownika').classes('w-full text-lg q-py-md'
                                                                                  ).props('dense autocomplete="username"')
                        with ui.row().classes('items-center w-full'):
                            ui.html('<span class="material-icons"'
                                    'style="color:#008080; font-size: 1.5em;">alternate_email</span>')
                            self.email = ui.input('Email').classes('w-full text-lg q-py-md').props('dense autocomplete="email"')
                        with ui.row().classes('items-center w-full'):
                            ui.html('<span class="material-icons" style="color:#008080; font-size: 1.5em;">lock</span>')
                            self.password = ui.input('Hasło', password=True).classes('w-full text-lg q-py-md'
                                                                                     ).props('dense autocomplete="new-password"')
                            
                            ui.html(f'<input type="hidden"  id="csrf_token" value="{self.token}">')
                        ui.button('ZAREJESTRUJ SIĘ').classes('w-full q-mt-md').props('type="submit"'
                                                                                     ).on('click.prevent', self.do_register)
                        
    def create_headers(self):
        headers = dict(self.headers)
        headers['X-Forwarded-For'] = self.client.host
        headers["Referer"] = "http://wallet.localhost:8081/register/"
        headers["Accept"] = "application/json"
        return headers
                    
    async def confirm_register(self):
        result = await self.dialog
        if result == 'Yes' or result is None:
            ui.navigate.to('/login')

    async def do_register(self):
        if not all([self.first_name.value, self.last_name.value, self.username.value, self.email.value, self.password.value]):
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
            ui.notify("token is not valid", color='negative')
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://session-auth:8000/register/",
                    json={
                        "first_name": self.first_name.value,
                        "last_name": self.last_name.value,
                        "username": self.username.value,
                        "email": self.email.value,
                        "password": self.password.value,
                    },
                    headers=self.create_headers(),
                    cookies=self.cookies,
                    timeout=10
                )
            if response.status_code == 201:
                with ui.dialog() as self.dialog, ui.card().classes('q-pa-xl q-ma-md rounded-borders shadow-10'):
                    ui.label(f'Utworzono konto dla: {self.username.value} ({self.email.value})'
                             ).classes('text-h6 text-center q-mb-md')
                    ui.button('OK', on_click=lambda: self.dialog.submit('Yes')
                              ).props('unelevated color="primary"').classes('full-width q-mt-md')
                await self.confirm_register()  
            else:
                error_text = handle_api_error(response)
                ui.notify(f'Rejestracja nieudana:\n{error_text}', color='negative', close_button=True, multi_line=True)
                
        except Exception as e:
            ui.notify(f'Błąd połączenia: {e}', color='negative')
        
        
@ui.page('/register')
def register(request: Request):

    add_style()
    nav("Register")
    RegisterForm(request)
    footer()
