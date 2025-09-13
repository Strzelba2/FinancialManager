from contextlib import contextmanager
from nicegui import ui


@contextmanager
def panel(title: str | None = None):
    with ui.card().classes('elevated-card q-pa-md') as c:
        if title:
            ui.html(f'<h3 style="margin:0 0 .5rem;font-size:15px;font-weight:600;color:#0f172a">{title}</h3>')
        yield c
