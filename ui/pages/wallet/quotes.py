from nicegui import ui, app
from fastapi import Request
from typing import List, Dict, Optional
from datetime import datetime
import math
from decimal import Decimal
import logging

from static.style import add_style, add_user_style, add_table_style
from components.context.nav_context import NavContextBase
from components.navbar_footer import footer
from schemas.quotes import QuoteRow
from clients.stock_client import StockClient
from utils.dates import next_quarter_business, TZ

logger = logging.getLogger(__name__)

MIC_CHOICES = {'GPW': 'XWAR', 'NEWCONNECT': 'XNCO'}
MIC_BY_CODE = {v: k for k, v in MIC_CHOICES.items()}


class Quotes(NavContextBase):
    """
    Quotes page: shows latest stock quotes for a given MIC with filters, summary,
    and a live “flash” effect when prices change.
    """
    def __init__(self, request: Request, mic: str) -> None:
        """
        Initialize the Quotes page.

        Args:
            request: FastAPI request object for the current page.
            mic: Market MIC (e.g. "XWAR", "XNCO").
        """
        logger.info(f"Quotes: initializing page for mic={mic!r}")
        
        self.stock_client = StockClient()
        
        self.request = request
        self.mic: str = mic
        
        self.header_card = None
        self.manage_card = None
        self.table_card = None
        self.table = None
        
        self.state = {
            'search': '',
            'mic':  MIC_BY_CODE.get(self.mic),
            'sort': ('symbol', 'asc'),
        }
        
        self._prev_map: Dict[str, QuoteRow] = {}
        
        ui.timer(0.01, self._init_async, once=True)
        
    async def _init_async(self) -> None:
        """
        Async initialization: render navbar, build UI, and footer.
        """
        logger.info(f"Quotes._init_async: building UI for mic={self.mic!r}")
        self.render_navbar()
        self.build_ui()
        footer()
        
    def apply_filters(self, rows: List[QuoteRow]) -> List[QuoteRow]:
        """
        Apply search filter and sorting to the list of quote rows.

        Filters:
            - search in symbol or name (case-insensitive)
        Sorting:
            - by column stored in self.state['sort'] (tuple: (column, 'asc'/'desc'))

        Args:
            rows: List of QuoteRow objects to filter and sort.

        Returns:
            Filtered and sorted list of QuoteRow objects.
        """
        logger.debug(
            f"Quotes.apply_filters: starting with {len(rows)} rows, "
            f"state={self.state!r}"
        )
        s = (self.state['search'] or '').strip().lower()
        if s:
            rows = [r for r in rows if s in r.symbol.lower() or s in (r.name or '').lower()]
        col, direction = self.state['sort']
        reverse = (direction == 'desc')
        
        def key(r: QuoteRow):
            return getattr(r, col) if col != 'last_trade_at' else (r.last_trade_at or '')
        try:
            rows.sort(key=key, reverse=reverse)
        except Exception as e:  
            logger.exception(f"Quotes.apply_filters: sorting failed: {e!r}")
        return rows
        
    async def read_rows(self, mic: str) -> List[QuoteRow]:
        """
        Read latest quotes for a given MIC.

        Prefer Redis cache if available:
            - key: `latest_quote:{mic}` (HASH with symbol->payload)
            - rows are built with `QuoteRow.from_redis`

        If Redis cache is missing:
            - query STOCK service via `StockClient.get_all_quotes(mic)`.

        Args:
            mic: Market MIC (e.g. "XWAR").

        Returns:
            Filtered and sorted list of QuoteRow objects.
        """
        logger.info(f"Quotes.read_rows: loading rows for mic={mic!r}")
        
        key = f'latest_quote:{mic}'
        if await app.storage.stock.exists(key):
            raw = await app.storage.stock.hgetall(key)
            logger.info(f"fields: {raw}")
            out: List[QuoteRow] = []
            for sym, payload in raw.items():
                try:
                    out.append(QuoteRow.from_redis(sym, payload))
                except Exception as e: 
                    logger.exception(
                        f"Quotes.read_rows: failed to parse payload for symbol={sym!r}: {e!r}"
                    )
            return self.apply_filters(out)
        else:
            raws = await self.stock_client.get_all_quotes(mic)
            return self.apply_filters(raws)
        
    def make_select(self, options, value, label, width='w-[260px]', icon: Optional[str] = None):
        """
        Helper to create a styled NiceGUI select used in filters.

        Args:
            options: Mapping or list of options accepted by NiceGUI `ui.select`.
            value: Initial selected value.
            label: Select label text.
            width: Tailwind-style width class.
            icon: Optional icon name to show in prepend slot.

        Returns:
            The created NiceGUI select element.
        """
        s = (
            ui.select(options, value=value, label=label)
            .classes(f'filter-field min-w-[220px] {width}')
            .props('outlined dense options-dense clearable color=primary popup-content-class=filter-popup')
        )
        if icon:
            with s.add_slot('prepend'):
                ui.icon(icon).classes('text-primary')
        return s
    
    def make_search_input(self, value: str, width: str = 'w-[260px]', label: str = 'Szukaj'):
        """
        Create a search input bound to `self.state['search']` and trigger refresh.

        Args:
            value: Initial value of the search string.
            width: Tailwind-style width class.
            label: Field label (defaults to 'Szukaj').

        Returns:
            The created NiceGUI input element.
        """
        
        def _search_changed(e):
            """
            Handle search value change: update state and refresh table once.
            """
            logger.info(f"Quotes.make_search_input: search changed -> {e.value!r}")
            self.state['search'] = e.value or ''
            ui.timer(0.05, self.refresh_once, once=True)
            
        s = (
            ui.input(
                value=value,
                placeholder='Szukaj symbol / nazwa…',
                label=label,
                on_change=lambda e: _search_changed(e),
            )
            .classes(f'filter-field min-w-[220px] {width}')
            .props(
                'outlined dense clearable color=primary input-class="q-pa-xs" '
                'clear-icon="close"'
            )
        )
        with s.add_slot('prepend'):
            ui.icon('search').classes('text-primary')

        s.props('debounce="250"')
        return s
    
    def update_summary(self, rows: list['QuoteRow']) -> None:
        """
        Update summary chips (+/-) based on price change.

        Args:
            rows: Current list of QuoteRow objects.
        """
        logger.debug(
            f"Quotes.update_summary: updating summary for {len(rows)} rows"
        )
        pos = 0
        neg = 0
        for r in rows:
            cp = r.change_pct if r.change_pct is not None else Decimal('0')
            if cp >= 0:
                pos += 1
            else:
                neg += 1

        if getattr(self, 'plus_chip', None):
            self.plus_chip.text = f'+{pos}'
            self.plus_chip.update()
        if getattr(self, 'minus_chip', None):
            self.minus_chip.text = f'−{neg}'
            self.minus_chip.update()

    def build_ui(self):
        """
        Create the main layout cards and trigger initial rendering.
        """
        logger.info("Quotes.build_ui: building main layout")
        with ui.column().classes('w-[100vw] gap-1'):
            self.header_card = ui.card().classes('elevated-card q-pa-sm q-mb-md') \
                .style('width:min(1600px,98vw); margin:0 auto 1px;')
            self.manage_card = ui.card().classes('elevated-card q-pa-sm q-mb-md') \
                .style('width:min(1600px,98vw); margin:0 auto 1px;')
            self.table_card = ui.card().classes('elevated-card q-pa-sm q-mb-md') \
                .style('width:min(1600px,98vw); margin:0 auto 1px;')

        self.render_all()
        
    async def refresh_once(self):
        """
        Reload rows for current MIC once and apply flashing effect on price changes.
        """
        logger.info(f"Quotes.refresh_once: refreshing rows for mic={self.mic!r}")
        rows = await self.read_rows(self.mic)
        self.patch_rows_with_flash(rows)
        
    def render_all(self):
        """
        Render header, manage area and an empty table, then asynchronously
        fill it with data and update summary.
        """
        logger.info("Quotes.render_all: rendering header, manage and table shell")
        self.render_header()
        self.render_manage()
        self.render_table([])

        async def _fill():
            logger.info("Quotes.render_all._fill: loading initial rows")
            rows = await self.read_rows(self.mic)
            self.patch_rows_with_flash(rows)
            self.update_summary(rows)
        ui.timer(0.05, _fill, once=True)

    def render_header(self):
        """
        Render header card with title and countdown to next refresh.
        """
        logger.debug("Quotes.render_header: rendering header card")
        self.header_card.clear()
        with self.header_card:
            with ui.row().style(
                "display:flex;justify-content:space-between;align-items:center;"
                "flex-wrap:wrap;gap:10px;width:100%;padding:1px 20px;"
            ):
                with ui.row().style('display:flex;align-items:center;flex-wrap:wrap;gap:10px;'):
                    ui.label('Notowania').classes('header-title')
                with ui.row().classes('items-center gap-2'):
                    self.last_ref_label = ui.label('Last update: --:--:--').classes('text-grey-6 text-sm')
                    
                    self._next_tick_at = next_quarter_business(datetime.now(TZ))

                    def _update_labels():
                        """
                        Periodically update next refresh countdown labels.
                        """
                        now = datetime.now(TZ)
                        target = self._next_tick_at

                        if now >= target:
                            target = next_quarter_business(now)
                            self._next_tick_at = target

                        delta = target - now
                        total_sec = int(delta.total_seconds())
                        if total_sec < 0:
                            total_sec = 0
                        mm, ss = divmod(total_sec, 60)

                        self.next_tick_label.text = (
                            "Następne odświeżenie: "
                            f"{target.strftime('%d.%m.%Y %H:%M')}"
                        )
                        self.countdown_label.text = f"{mm:02d}:{ss:02d}"

                    ui.timer(1.0, _update_labels)

    def render_manage(self):
        """
        Render management/filter row: MIC selector, search, and summary chips.
        """
        logger.debug("Quotes.render_manage: rendering manage card")
        self.manage_card.clear()
        with self.manage_card:
            with ui.row().style(
                "display:flex;justify-content:space-between;align-items:center;"
                "flex-wrap:wrap;gap:10px;width:100%;padding:1px 30px;"
            ):
                with ui.row().classes('items-center gap-2'):
                    
                    mices = list(MIC_CHOICES.keys())
                    
                    self.sel_mic = self.make_select(mices, self.state['mic'], 'Rynek', icon='public')
                    
                    def _on_mic_changed(e):
                        """
                        Navigate to selected MIC page when market selection changes.
                        """
                        selected = e.sender.value
                        
                        logger.info(selected)
                        
                        if not selected:
                            return
                        
                        mic = MIC_CHOICES.get(selected)
                        ui.navigate.to(f'/stock/quotes/{mic}')

                    self.sel_mic.on('update:model-value', _on_mic_changed)

                    self.search_input = self.make_search_input(self.state['search'])
                    
                with ui.row().classes('items-center gap-2'):
                    ui.separator().props('vertical').classes('mx-2 hidden md:block')

                    ui.label('Podsumowanie:').classes('text-grey-7 text-sm')

                    self.plus_chip = ui.chip('+0') \
                        .props('color=positive text-color=white') \
                        .classes('q-px-sm')

                    self.minus_chip = ui.chip('−0') \
                        .props('color=negative text-color=white') \
                        .classes('q-px-sm')

    def render_table(self, rows: List[QuoteRow]):
        """
        Render quotes table card with given rows.

        Args:
            rows: Initial list of QuoteRow objects to render.
        """
        logger.debug(
            f"Quotes.render_table: rendering table with {len(rows)} initial rows"
        )
        self.table_card.clear()
        with self.table_card:
            with ui.element('div').classes('card-body w-full'):
                cols = [
                    {'name': 'symbol', 'label': 'Symbol', 'field': 'symbol', 'sortable': True, 'align': 'left',
                     'style': 'width:120px;white-space:nowrap;', 'headerStyle': 'white-space:nowrap;'},
                    {'name': 'name', 'label': 'Nazwa', 'field': 'name', 'align': 'left',
                     'style': 'max-width:280px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;',
                     'headerStyle': 'white-space:nowrap;'},
                    {'name': 'last_price_fmt', 'label': 'Kurs', 'field': 'last_price_fmt', 'align': 'right',
                     'style': 'width:120px;white-space:nowrap;', 'headerStyle': 'white-space:nowrap;'},
                    {'name': 'change_pct', 'label': 'Zmiana %', 'field': 'change_pct', 'sortable': True, 'align': 'right',
                     'style': 'width:120px;white-space:nowrap;', 'headerStyle': 'white-space:nowrap;'},
                    {'name': 'volume', 'label': 'Wolumen', 'field': 'volume', 'align': 'right',
                     'style': 'width:120px;white-space:nowrap;', 'headerStyle': 'white-space:nowrap;'},
                    {'name': 'last_trade_at', 'label': 'Ostatni handel', 'field': 'last_trade_at', 'align': 'left',
                     'style': 'width:180px;white-space:nowrap;', 'headerStyle': 'white-space:nowrap;'},
                    {'name': 'detail', 'label': '', 'field': 'symbol', 'align': 'right',
                     'style': 'width:80px;white-space:nowrap;', 'headerStyle': 'white-space:nowrap;'},
                ]

                self.table = (
                    ui.table(
                        columns=cols,
                        rows=[r.model_dump() for r in rows],
                        row_key='symbol',
                        pagination={'page': 1, 'rowsPerPage': 100, 'sortBy': 'symbol', 'descending': False},
                    )
                    .props(
                        'flat separator=horizontal wrap-cells '
                        'table-style="width:100%;table-layout:auto" '
                        'rows-per-page-options=[20,50,100,200,0]' 
                    )
                    .classes('q-mt-none w-full table-modern')
                )

                self.table.add_slot('body-cell-change_pct', """
                <q-td :props="props" :class="(parseFloat(props.row.change_pct || 0) >= 0 ? 'text-positive' : 'text-negative')">
                <q-icon :name="parseFloat(props.row.change_pct || 0) >= 0 ? 'trending_up' : 'trending_down'" size="16px" class="q-mr-xs" />
                {{ props.row.change_pct_fmt }}
                </q-td>
                """)
                
                self.table.add_slot('body-cell-last_trade_at', """
                <q-td :props="props">
                <div class="text-no-wrap">
                    <span class="text-grey-7">{{ props.row.last_trade_date_fmt || '—' }}</span>
                    <span class="q-ml-sm text-weight-bold text-primary">{{ props.row.last_trade_time_fmt || '' }}</span>
                </div>
                </q-td>
                """)

                self.table.add_slot('body-cell-detail', """
                <q-td :props="props" class="text-right">
                  <q-btn flat round dense icon="more_vert" color="primary">
                    <q-menu anchor="bottom right" self="top right">
                      <q-list style="min-width: 160px">
                        <q-item clickable v-close-popup @click.stop="$parent.$emit('on_quote_alert', props.row)">
                          <q-item-section avatar><q-icon name="add_alert"/></q-item-section>
                          <q-item-section>Utwórz alert</q-item-section>
                        </q-item>
                        <q-item clickable v-close-popup @click.stop="$parent.$emit('on_quote_details', props.row)">
                          <q-item-section avatar><q-icon name="show_chart"/></q-item-section>
                          <q-item-section>Szczegóły</q-item-section>
                        </q-item>
                        <q-separator />

                        <q-item clickable v-close-popup @click.stop="$parent.$emit('on_quote_favorite', props.row)">
                        <q-item-section avatar><q-icon name="star_border"/></q-item-section>
                        <q-item-section>Ulubione</q-item-section>
                        </q-item>
                      </q-list>
                    </q-menu>
                  </q-btn>
                </q-td>
                """)

                self.table.on('on_quote_alert', lambda e: ui.notify(f"Alert for {e.args['symbol']} (TODO)"))
                self.table.on('on_quote_details', lambda e: ui.notify(f"Details for {e.args['symbol']} (TODO)"))
                self.table.on('on_quote_favorite', lambda e: ui.notify(f"Ulubione for {e.args['symbol']} (TODO)"))
        
    def patch_rows_with_flash(self, new_rows: List[QuoteRow]) -> None:
        """
        Update table rows and apply CSS flash class for rows
        where last_price has changed compared to previous snapshot.

        Args:
            new_rows: Fresh list of QuoteRow objects.
        """
        if not self.table:
            logger.debug("Quotes.patch_rows_with_flash: table not ready, skipping")
            return

        flashes: Dict[str, str] = {}
        new_map = {r.symbol: r for r in new_rows}

        for sym, row in new_map.items():
            prev = self._prev_map.get(sym)
            if prev:
                lp, ln = prev.last_price, row.last_price
                if lp is not None and ln is not None and not math.isclose(float(lp), float(ln), rel_tol=1e-9, abs_tol=1e-9):
                    flashes[sym] = 'flash-up' if ln > lp else 'flash-down'

        self.table.rows = [r.model_dump() for r in new_rows]
        self.table.update()

        for sym, css in flashes.items():
            self.table.run_javascript(f"""
            (function(){{
              const rows = Array.from(document.querySelectorAll('tr'));
              const row = rows.find(tr => tr.innerText.startsWith('{sym}\\n'));
              if (row) {{
                row.classList.add('{css}');
                setTimeout(() => row.classList.remove('{css}'), 600);
              }}
            }})();
            """)

        self._prev_map = new_map


@ui.page('/stock/quotes/{mic}')
async def quotes_route(request: Request, mic: str):
    
    add_style()
    add_user_style()
    add_table_style()
    
    Quotes(request, mic)
    
    