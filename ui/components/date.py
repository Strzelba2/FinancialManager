import datetime
from nicegui import ui
import logging

logger = logging.getLogger(__name__)


def attach_date_time_popups(input_el: ui.input) -> None:
    """
    Attach two popup dialogs (date & time) to a single NiceGUI input.

    Behaviour:
    - `input_el.value` holds text in the format: 'YYYY-MM-DD HH:MM'.
    - Left icon opens a date picker (calendar).
    - Right icon opens a time picker.

    Args:
        input_el: NiceGUI input element to which date and time popups will be attached.
    """

    now = datetime.datetime.now()
    default_date = now.strftime('%Y-%m-%d')
    default_time = now.strftime('%H:%M')

    def parse_current():
        """
        Read the current value of the input and return (date_str, time_str).

        Expected format: 'YYYY-MM-DD HH:MM'.
        Falls back to (default_date, default_time) on error or empty value.
        """
        value = (input_el.value or '').strip()
        if not value:
            logger.debug(
                "parse_current: value empty, using defaults "
                f"({default_date}, {default_time})"
            )
            return default_date, default_time
        try:
            dt = datetime.datetime.strptime(value, '%Y-%m-%d %H:%M')
            return dt.strftime('%Y-%m-%d'), dt.strftime('%H:%M')
        except Exception as e:
            logger.warning(
                f"parse_current: failed to parse '{value}' as 'YYYY-MM-DD HH:MM': {e}; "
                f"using defaults ({default_date}, {default_time})"
            )
            return default_date, default_time

    date_dialog = ui.dialog()
    with date_dialog, ui.card().classes('w-[min(340px,95vw)]'):
        ui.label('Wybierz datę').classes('text-base font-semibold q-mb-sm')
        d_str, t_str = parse_current()
        date_picker = ui.date(value=d_str).classes('w-full')

        def apply_date() -> None:
            """
            Apply the selected date to the input, preserving current time.
            """
            date_val = date_picker.value or default_date
            _, time_val = parse_current()
            input_el.value = f'{date_val} {time_val}'
            date_dialog.close()

        with ui.row().classes('justify-end q-mt-sm'):
            ui.button('Zamknij', on_click=date_dialog.close).props('flat')
            ui.button('OK', on_click=apply_date).props('unelevated color=primary')

    time_dialog = ui.dialog()
    with time_dialog, ui.card().classes('w-[min(340px,95vw)]'):
        ui.label('Wybierz godzinę').classes('text-base font-semibold q-mb-sm')
        d_str, t_str = parse_current()
        time_picker = ui.time(value=t_str).props('format24h').classes('w-full')

        def apply_time() -> None:
            """
            Apply the selected time to the input, preserving current date.
            """
            date_val, _ = parse_current()
            time_val = time_picker.value or default_time
            input_el.value = f'{date_val} {time_val}'
            time_dialog.close()

        with ui.row().classes('justify-end q-mt-sm'):
            ui.button('Zamknij', on_click=time_dialog.close).props('flat')
            ui.button('OK', on_click=apply_time).props('unelevated color=primary')

    with input_el.add_slot('prepend'):
        ui.icon('event').classes('cursor-pointer').on('click', date_dialog.open)

    with input_el.add_slot('append'):
        ui.icon('access_time').classes('cursor-pointer').on('click', time_dialog.open)

    input_el.on('click', date_dialog.open)
