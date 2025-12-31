import datetime
from nicegui import ui
from .panel.card import panel

ALERTS = [
        {
            'id': 'AL-1', 'symbol': 'AAPL', 'type': 'Cena', 'operator': '>', 'threshold': 220.0,
            'severity': 'high', 'status': 'active', 'muted': False,
            'desc': 'Cena > 220.00', 'created_at': datetime.datetime.now().isoformat(timespec='seconds'), 'last_triggered': None,
            'repeat': True, 'cooldown_min': 15, 'market_hours_only': True, 'note': 'Wybicie ATH'
        },
        {
            'id': 'AL-2', 'symbol': 'NVDA', '%': 5, 'type': '% zmiany', 'operator': '≥', 'threshold': 3.0,
            'severity': 'medium', 'status': 'fired', 'muted': False,
            'desc': 'Zmiana 60m ≥ 3%', 'created_at': datetime.datetime.now().isoformat(timespec='seconds'),
            'last_triggered': (datetime.datetime.now() - datetime.timedelta(minutes=12)).isoformat(timespec='seconds'),
            'repeat': True, 'cooldown_min': 30, 'market_hours_only': True, 'note': ''
        },
        {
            'id': 'AL-3', 'symbol': 'TSLA', 'type': 'RSI', 'operator': '<', 'threshold': 30.0,
            'severity': 'low', 'status': 'snoozed', 'muted': False,
            'desc': 'RSI < 30', 'created_at': datetime.datetime.now().isoformat(timespec='seconds'),
            'snooze_until': (datetime.datetime.now()+datetime.timedelta(minutes=45)).isoformat(timespec='seconds'),
            'repeat': False, 'cooldown_min': 0, 'market_hours_only': False, 'note': 'Możliwy dołek'
        },
    ]


def ack_alert(alert_id): 
    for a in ALERTS:
        if a['id'] == alert_id:
            a['status'] = 'ack'
            a['acked_at'] = datetime.datetime.now().isoformat(timespec='seconds')
            break


def snooze_alert(alert_id, minutes=60):
    until = datetime.datetime.now() + datetime.timedelta(minutes=minutes)
    for a in ALERTS:
        if a['id'] == alert_id:
            a['status'] = 'snoozed'
            a['snooze_until'] = until.isoformat(timespec='seconds')
            break


def mute_alert(alert_id, muted=True):
    for a in ALERTS:
        if a['id'] == alert_id:
            a['muted'] = bool(muted)
            a['status'] = 'muted' if muted else 'active'
            break


def _ago(dt_iso: str | None):
    if not dt_iso: 
        return ''
    try:
        dt = datetime.datetime.fromisoformat(dt_iso)
    except Exception:
        return dt_iso
    delta = datetime.datetime.now() - dt
    s = int(delta.total_seconds())
    if s < 60:   
        return f'{s}s temu'
    m = s//60
    if m < 60:   
        return f'{m}m temu'
    h = m//60
    if h < 24:   
        return f'{h}h temu'
    d = h//24
    return f'{d}d temu'


def _sev_color(sev: str):
    return {'low': 'info', 'medium': 'warning', 'high': 'negative'}.get((sev or '').lower(), 'info')


def _status_badge(status: str):
    m = (status or '').lower()
    lbl = {'active': 'Aktywny', 'fired': 'Wyzwolony', 'ack': 'Potwierdzony', 'snoozed': 'Drzemka', 'muted': 'Wyciszony'}.get(m, m)
    col = {'active': 'primary', 'fired': 'warning', 'ack': 'positive', 'snoozed': 'info', 'muted': 'grey'}.get(m, 'grey')
    return lbl, col


def alert_form_dialog(on_save, alert: dict | None = None):
    dlg = ui.dialog()
    with dlg, ui.card().classes('w-[min(900px,95vw)]').style('max-height:90vh'):
        ui.label('Nowy alert' if not alert else 'Edytuj alert').classes('text-base font-semibold q-mb-sm')
        with ui.row().classes('gap-3'):
            sym = ui.input('Ticker').classes('w-32')
            typ = ui.select(
                ['Cena', '% zmiany', 'Wolumen', 'MA crossover', 'RSI', 'P/L dzienny'],
                value='Cena', label='Typ'
            ).classes('w-44')
            op = ui.select(['>', '≥', '<', '≤'], value='>').classes('w-20')
            thr = ui.number(label='Próg', value=0).classes('w-32')
            look = ui.select(['5m', '15m', '60m', '1d'], value='15m', label='Okno').classes('w-28')
            sev = ui.select(['low', 'medium', 'high'], value='medium', label='Priorytet').classes('w-28')
        with ui.row().classes('gap-3'):
            repeat = ui.checkbox('Powtarzaj (po cooldown)').props('dense')
            cooldown = ui.number(label='Cooldown (min)', value=30).classes('w-36')
            quiet = ui.checkbox('Tylko w godzinach handlu').props('dense')
            note = ui.input('Notatka').classes('w-full')

        if alert:
            sym.value = alert['symbol']
            typ.value = alert['type']
            op.value = alert.get('operator', '>')
            thr.value = alert.get('threshold', 0)
            look.value = alert.get('lookback', '15m')
            sev.value = alert.get('severity', 'medium')
            repeat.value = alert.get('repeat', True)
            cooldown.value = alert.get('cooldown_min', 30)
            quiet.value = alert.get('market_hours_only', True)
            note.value = alert.get('note', '')

        with ui.row().classes('justify-end gap-2 q-mt-sm'):
            ui.button('Anuluj', on_click=dlg.close).props('flat')
            
            def _save():
                payload = {
                    'id': (alert['id'] if alert else f'AL-{int(datetime.datetime.now().timestamp())}'),
                    'symbol': sym.value.strip().upper(),
                    'type': typ.value,
                    'operator': op.value,
                    'threshold': float(thr.value or 0),
                    'lookback': look.value,
                    'severity': sev.value,
                    'repeat': bool(repeat.value),
                    'cooldown_min': int(cooldown.value or 0),
                    'market_hours_only': bool(quiet.value),
                    'note': note.value,
                    'status': alert['status'] if alert else 'active',
                    'muted': alert['muted'] if alert else False,
                    'created_at': alert.get('created_at') if alert else datetime.datetime.now().isoformat(timespec='seconds'),
                    'last_triggered': alert.get('last_triggered'),
                }
                on_save(payload)
                dlg.close()
            ui.button('Zapisz', on_click=_save).props('unelevated color=primary')
    return dlg


def alerts_panel_card(alerts: list[dict], title='Alerty giełdowe', top: int = 5):

    def prep(a: dict):
        lbl, col = _status_badge(a.get('status', 'active'))
        return {
            'id': a['id'],
            'symbol': a.get('symbol', ''),
            'condition': a.get('desc') or f"{a.get('type')} {a.get('operator', '')} {a.get('threshold')}",
            'severity': a.get('severity', 'medium'),
            'severity_color': _sev_color(a.get('severity')),
            'status': lbl, 'status_color': col,
            'last': _ago(a.get('last_triggered')) or '—',
            'note': a.get('note', ''),
        }

    # prepared = [prep(a) for a in alerts]

    alerts_sorted = sorted(alerts, key=lambda a: (a.get('last_triggered') or a.get('created_at') or ''), reverse=True)
    top_rows = [prep(a) for a in alerts_sorted[:top]]
           
    cols_compact = [
        {'name': 'symbol', 'label': 'Ticker', 'field': 'symbol', 'align': 'left',
         'style': 'width:90px', 'headerStyle': 'font-weight:700'},
        {'name': 'condition', 'label': 'Warunek', 'field': 'condition', 'align': 'left',
         'headerStyle': 'font-weight:700'},
        {'name': 'severity', 'label': 'Priorytet', 'field': 'severity', 'align': 'left', 
         'style': 'width:100px', 'headerStyle': 'font-weight:700'},
        {'name': 'status', 'label': 'Status', 'field': 'status', 'align': 'left',
         'style': 'width:100px', 'headerStyle': 'font-weight:700'} 
    ]
    cols_full = cols_compact + [
        {'name': 'last', 'label': 'Ostatnio', 'field': 'last', 'align': 'left',
         'style': 'width:100px', 'headerStyle': 'font-weight:700'},
        {'name': 'note', 'label': 'Notatka', 'field': 'note', 'align': 'left', 
         'headerStyle': 'font-weight:700'},
        {'name': 'actions', 'label': 'Akcje', 'field': 'id', 'align': 'right',
         'style': 'width:220px', 'headerStyle': 'font-weight:700'},
    ]

    dlg = ui.dialog()
    with dlg, ui.card().classes('w-[min(1200px,96vw)] max-w-none'):
        ui.label(title).classes('text-base font-semibold q-mb-sm')

        with ui.row().classes('items-center justify-between q-mb-sm w-full'):
            with ui.row().classes('gap-2'):
                def _open_new():
                    def on_save(new_payload):
                        for i, a in enumerate(ALERTS):
                            if a['id'] == new_payload['id']:
                                ALERTS[i] = new_payload
                                break
                        else:
                            ALERTS.append(new_payload)
                        dlg.update()
                    alert_form_dialog(on_save).open()
                ui.button('Dodaj alert', on_click=_open_new).props('unelevated color=primary')

        full_tbl = ui.table(columns=cols_full, rows=[prep(a) for a in alerts_sorted], row_key='id') \
            .props('flat dense separator=horizontal rows-per-page-options=[10,25,50,0]') \
            .classes('q-mt-none w-full')

        full_tbl.add_slot('body-cell-severity', """
        <q-td :props="props">
          <q-badge :color="props.row.severity_color" :label="props.row.severity.toUpperCase()" />
        </q-td>
        """)
        full_tbl.add_slot('body-cell-status', """
        <q-td :props="props">
          <q-badge :color="props.row.status_color" :label="props.row.status" />
        </q-td>
        """)
        full_tbl.add_slot('body-cell-actions', """
        <q-td :props="props" class="text-right">
          <q-btn dense flat icon="done" @click.stop="() => $python.emit('ack', props.row.id)" title="Potwierdź" />
          <q-btn dense flat icon="snooze" @click.stop="() => $python.emit('snooze', props.row.id)" title="Drzemka 1h" />
          <q-btn dense flat icon="notifications_off" @click.stop="() => $python.emit('mute', props.row.id)" title="Wycisz" />
          <q-btn dense flat icon="edit" @click.stop="() => $python.emit('edit', props.row.id)" title="Edytuj" />
        </q-td>
        """)

        def _on_ack(alert_id: str):
            ack_alert(alert_id)
            dlg.update()

        def _on_snooze(alert_id: str):
            snooze_alert(alert_id, 60)
            dlg.update()

        def _on_mute(alert_id: str):
            mute_alert(alert_id, True)
            dlg.update()

        def _on_edit(alert_id: str):
            def on_save(updated):
                for i, a in enumerate(ALERTS):
                    if a['id'] == alert_id:
                        ALERTS[i] = updated
                        break
                dlg.update()
            rec = next((a for a in ALERTS if a['id'] == alert_id), None)
            alert_form_dialog(on_save, rec).open()

        ui.button('Zamknij', on_click=dlg.close).classes('q-mt-sm self-end')
        
        ui.on('ack', _on_ack)
        ui.on('snooze', _on_snooze)
        ui.on('mute', _on_mute)
        ui.on('edit', _on_edit)

    with panel() as card:
        card.classes('w-full max-w-none p-0 cursor-pointer').style('width:100%')
        ui.label(title).classes('text-sm font-semibold').style('padding:6px 12px 2px 12px')

        mini = ui.table(columns=cols_compact, rows=top_rows, row_key='id') \
            .props('flat dense separator=horizontal hide-bottom hide-pagination rows-per-page-options=[5] '
                   'wrap-cells table-style="table-layout:fixed"') \
            .classes('q-mt-none w-full table-compact') \
            .style('margin:0;padding:0;overflow-x:hidden;')

        mini.add_slot('body-cell-severity', """
        <q-td :props="props">
          <q-badge :color="props.row.severity_color" :label="props.row.severity.toUpperCase()" />
        </q-td>
        """)
        mini.add_slot('body-cell-status', """
        <q-td :props="props">
          <q-badge :color="props.row.status_color" :label="props.row.status" />
        </q-td>
        """)

        card.on('click', lambda e: dlg.open())
        
        
def alert_nav_right_section():
    is_quiet = False

    def _active_alerts():
        return [a for a in ALERTS if (a.get('status') in ('active', 'fired')) and not a.get('muted')]

    bell_area = ui.element('div')

    def render_bell():
        bell_area.clear()
        with bell_area:
            if not is_quiet:
                with ui.button(icon='notifications').props('flat color=white'):
                    if not is_quiet:
                        cnt = len(_active_alerts())
                        if cnt:
                            ui.badge(cnt, color='red').props('floating')
                    with ui.menu().classes('settings-menu') as m:
                        m.props('offset=[0,22]')
                        if is_quiet:
                            ui.label('Alerty wyciszone (Quiet ON)').classes('q-pa-md')
                        else:
                            ui.label('Ostatnie alerty').classes('q-px-md q-pt-sm q-mb-xs')
                            for a in _active_alerts()[:5]:
                                text = a.get('desc') or f"{a.get('type')} {a.get('operator', '')} {a.get('threshold')}"
                                with ui.row().classes('items-center q-px-md q-py-xs').style('min-width:340px'):
                                    color = (
                                        '#eab308' if a.get('severity') == 'medium'
                                        else '#ef4444' if a.get('severity') == 'high'
                                        else '#22c55e'
                                    )
                                    ui.element('span').classes('badge-dot').style(
                                        f"background:{color}"
                                    )
                                    ui.label(f"{a.get('symbol')} · {text}").classes('q-ml-sm')
                                    ui.space()
                                    ui.button(icon='done').props('dense flat size=sm') \
                                        .on('click', lambda e, a_id=a['id']: (ack_alert(a_id),  render_bell()))
                                    ui.button(icon='snooze').props('dense flat size=sm') \
                                        .on('click', lambda e, a_id=a['id']: (snooze_alert(a_id, 60),  render_bell()))
                                    ui.button(icon='notifications_off').props('dense flat size=sm') \
                                        .on('click', lambda e, a_id=a['id']: (mute_alert(a_id, True),  render_bell()))

    with ui.row().classes('items-center q-ml-sm'):
        ui.label('Quiet').classes('text-white q-mr-xs')
        quiet = ui.toggle(['OFF', 'ON'], value='OFF').props('dense')

        def _set_quiet(on: bool):
            nonlocal is_quiet
            is_quiet = on
            render_bell() 

        quiet.on('update:model-value', lambda e: _set_quiet(e.sender.value == 'ON'))

    render_bell()
