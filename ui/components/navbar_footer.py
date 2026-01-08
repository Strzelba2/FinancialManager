from nicegui import ui
from .alerts import alert_form_dialog, ALERTS, alert_nav_right_section
from services.current_user import get_username
import logging

logger = logging.getLogger(__name__)


def nav(current: str = '', ctx=None):
    with ui.element('div').classes('navbar'):
        def nav_link(label, path):
            return (
                ui.link(label, path)
                .classes('flex items-center justify-center q-px-md  text-white')
                .style('padding-left: 5px; padding-right: 5px;margin-left: 0;')
                )
            
        if current == 'Home':
            with ui.element('div').classes('nav-left'):
                pass
            with ui.element('div').classes('nav-right'): 
                ui.link('Home', '/home')
                ui.link('Login', '/login')
                ui.link('Rejestracja', '/register')
                ui.link('O nas', '#')
        elif current == 'Login':
            with ui.element('div').classes('nav-left'):
                pass
            with ui.element('div').classes('nav-right'): 
                nav_link('Home', '/home')
                nav_link('Rejestracja', '/register')
        elif current == 'Register':
            with ui.element('div').classes('nav-left'):
                pass
            with ui.element('div').classes('nav-right'):
                ui.link('Home', '/home')
                ui.link('Login', '/login')
        elif current == "User":
            with ui.element('div').classes('nav-left'):
                nav_link('Portfolio', '/wallet')
                with ui.button('Portfel', icon='account_balance_wallet').props('flat color=white'):
                    with ui.menu().classes('settings-menu') as menu:
                        menu.props('offset=[0,22]')
                        ui.menu_item('Dodaj portfel…', on_click=lambda: ctx.open_create_wallet_dialog()).classes('text-white')
                        ui.menu_item('Usuń portfel…', on_click=lambda: ctx.open_delete_wallet_dialog()).classes('text-white')
                        ui.separator().classes('bg-white')
                        ui.menu_item('Dodaj konto…', on_click=lambda: ctx.open_create_account_dialog()).classes('text-white')
                        ui.separator().classes('bg-white')
                        ui.menu_item('Zarządzaj portfelami',
                                     on_click=lambda: ui.navigate.to('/wallet-manager')).classes('text-white')
                        ui.separator().classes('bg-white')

                nav_link('Transakcje', '/transactions')
                
                with ui.button('Makler', icon='account_balance_wallet').props('flat color=white'):
                    with ui.menu().classes('settings-menu') as menu:
                        menu.props('offset=[0,22]')
                        ui.menu_item('Konta', on_click=lambda: ui.navigate.to('/stock/accounts')).classes('text-white')
                        ui.separator().classes('bg-white')
                        ui.menu_item('Notowania', on_click=lambda: ui.navigate.to('/stock/quotes/XWAR')).classes('text-white')
                        ui.separator().classes('bg-white')
                        ui.menu_item('Operacje', on_click=lambda: ui.navigate.to('/brokerage/events')).classes('text-white')
                        ui.separator().classes('bg-white')
                        ui.menu_item('Pozycje', on_click=lambda: ui.navigate.to('/brokerage/holdings')).classes('text-white')
                        ui.separator().classes('bg-white')
                        ui.menu_item('alerts', on_click=lambda: ui.navigate.to('/stock/alesrts')).classes('text-white')
            
            with ui.element('div').classes('nav-right'): 
                display_name = get_username()
                
                with ui.element('div').classes('user-name-chip'):
                    ui.element('span').classes('user-name-dot')  
                    ui.label(display_name).classes('user-name')   
                    ui.icon('expand_more').props('size=18')
                
                alert_nav_right_section()
                
                with ui.button(icon='add').props('flat color=white'):
                    with ui.menu().classes('settings-menu') as addm:
                        addm.props('offset=[0,22]')
                        ui.menu_item('Alert', on_click=lambda: alert_form_dialog(lambda payload: (ALERTS.append(payload), 
                                                                                                  ui.emit('alerts:refresh',
                                                                                                          payload['id']))).open())
                        ui.separator().classes('bg-white')
                        ui.menu_item('Transakcja maklerska', on_click=lambda: ui.emit('tx:open-broker'))
                        ui.separator().classes('bg-white')
                        ui.menu_item('Transakcja gotówkowa', on_click=lambda: ui.emit('tx:open-cash'))
                        ui.separator().classes('bg-white')
                        ui.menu_item('Stały wydatek', on_click=lambda: ui.emit('exp:open'))
                        
                with ui.button('Settings', icon='account_circle').props('flat color=white'):
                    with ui.menu().classes('settings-menu') as menu:
                        menu.props('offset=[0,22]')
                        ui.menu_item('Profile', on_click=lambda: ui.navigate.to('/settings/profile'))
                        ui.separator().classes('bg-white')
                        ui.menu_item('Preferences', on_click=lambda: ui.navigate.to('/settings/preferences'))
                        ui.separator().classes('bg-white')
                        ui.menu_item('Security', on_click=lambda: ui.navigate.to('/settings/security'))
                        ui.separator().classes('bg-white')
                        ui.menu_item('Logout', on_click=lambda: ui.navigate.to('/logout'))


def footer():
    with ui.element('footer').classes('footer'):
        ui.html('<div><strong>FinansowaEg</strong> © 2025</div>')
        ui.html('<div><a href="#">Polityka prywatności</a> | <a href="#">Kontakt</a></div>')
