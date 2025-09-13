from nicegui import ui
from fastapi import Request

import logging

logger = logging.getLogger(__name__)


def error_page(status_code: int, message: str):
    with ui.column().classes('items-center justify-center h-screen w-full bg-grey-2 relative').style('padding: 30px'):
        
        ui.label(str(status_code)).classes(
            'absolute'
        ).style('''
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 24rem;
            color: #999;
            opacity: 0.1;
            z-index: 0;
            animation: pulse 3s ease-in-out infinite;
            pointer-events: none;
        ''')

        with ui.column().classes('items-center justify-center relative text-center').style('z-index: 1'):
            ui.label('Oops! Something went wrong.').classes('text-h5 text-bold text-red')
            ui.label(message).classes('q-mt-md text-body1')
            ui.button('Go back to login', on_click=lambda: ui.navigate.to('/login')) \
                .props('color=primary unelevated') \
                .classes('q-mt-xl')

    ui.add_head_html('''
        <style>
        @keyframes pulse {
            0% {
                transform: translate(-50%, -50%) scale(0.8);
                opacity: 0.05;
            }
            50% {
                transform: translate(-50%, -50%) scale(1.4);
                opacity: 0.25;
            }
            100% {
                transform: translate(-50%, -50%) scale(0.8);
                opacity: 0.05;
            }
        }
        </style>
    ''')


@ui.page('/error')
def dynamic_error_page(request: Request):
    logger.info("dynamic_error_page")
    code = int(request.query_params.get('status', 403))
    message = request.query_params.get('message', 'Unauthorized')
    
    error_page(code, message)
