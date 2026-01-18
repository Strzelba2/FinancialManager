from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional

from nicegui import ui
from starlette.requests import Request

from clients.stock_client import StockClient  
from components.context.nav_context import NavContextBase
from components.navbar_footer import footer
from .quotes import MIC_CHOICES, MIC_BY_CODE
from static.style import add_style, add_user_style, add_table_style
from components.context.chart.chart_draw import ChartsDrawMixin
from utils.utils import parse_date

logger = logging.getLogger(__name__)


class ChartsPage(NavContextBase, ChartsDrawMixin): 
    """
    Instruments charts page: sync daily candles and show candlestick/line charts.

    Responsibilities:
    - Provide UI for selecting market (MIC) + instruments
    - Choose chart type/layout + date range presets or custom range
    - Sync candles via StockClient and cache results
    - Render charts using ECharts + toolbar (from ChartsDrawMixin)

    Notes:
    - Uses internal caches:
        * self._data_cache[symbol] -> list[dict] candles
        * self._instrument_names[symbol] -> display name
    - UI is built lazily via `ui.timer(..., self._init_async, once=True)`
    """
    def __init__(self, request: Request, mic: str) -> None:
        """
        Create ChartsPage instance and schedule async initialization.

        Args:
            request: Incoming HTTP request (NiceGUI/Starlette).
            mic: Market identifier code string (e.g. 'XWAR', 'XNCO', etc.).
        """
        logger.info(f"ChartsPage: init mic={mic!r}")

        self.request = request
        self.mic = mic
        self.stock_client = StockClient()

        self.header_card = None
        self.manage_card = None
        self.charts_card = None
        
        self.range_state = {"value": "ALL"}
        self.range_labels = {"ALL": "All", "1M": "Last Month", "3M": "Last 3 Months", "1Y": "Last Year", "CUSTOM": "Date"}
        
        self.range_btn = None
        self.custom_row = None

        self.state: dict[str, Any] = {
            'mic':  MIC_BY_CODE.get(self.mic),
            "search": "",
            "instrument_options": {},     
            "selected_symbols": [],      
            "chart_type": "candlestick",  
            "layout": "separate",          
            "show_volume": True,
            "date_from": None,
            "date_to": None,
            "overlap_days": 7,
            "include_items": True,       
            "hlines": [],                 
        }

        self._chart_widgets: dict[str, Any] = {}  
        self._data_cache: dict[str, list[dict]] = {}
        self._instrument_names: dict[str, str] = {}

        ui.timer(0.01, self._init_async, once=True)

    async def _init_async(self) -> None:
        """
        Async initialization sequence.

        Steps:
        - Render navbar
        - Inject ECharts analysis JS once per client
        - Build UI + footer
        - Load instrument options
        """
        logger.debug("ChartsPage._init_async: start")
        self.render_navbar()
        client = ui.context.client
        if not getattr(client, "_echart_draw_loaded", False):
            client._echart_draw_loaded = True
            ui.run_javascript(self._echart_draw_js()) 
            ui.run_javascript('console.log("[PY] injected, NG_ECHART_DRAW =", !!window.NG_ECHART_DRAW)')
        self.build_ui()
        footer()

        await self.refresh_instrument_options()

    def build_ui(self) -> None:
        """
        Build the full page UI skeleton and render all major sections.

        Sections:
        - header (status)
        - manage panel (filters + sync controls)
        - charts shell (output area)
        """
        logger.debug("ChartsPage.build_ui: building page cards")
        with ui.column().classes("w-[100vw] gap-1"):
            self.header_card = ui.card().classes("elevated-card q-pa-sm q-mb-md") \
                .style("width:min(1600px,98vw); margin:0 auto 1px;")
            self.manage_card = ui.card().classes("elevated-card q-pa-sm q-mb-md") \
                .style("width:min(1600px,98vw); margin:0 auto 1px;")
            self.charts_card = ui.card().classes("elevated-card q-pa-sm q-mb-md") \
                .style("width:min(1600px,98vw); margin:0 auto 1px;")

        self.render_header()
        self.render_manage()
        self.render_charts_shell()

    def render_header(self) -> None:
        """
        Render top header section with title + status label.
        """
        self.header_card.clear()
        with self.header_card:
            with ui.row().classes("items-center justify-between w-full").style("padding: 6px 18px;"):
                ui.label("Wykresy: świecowe/liniowe").classes("header-title")
                self.status_label = ui.label("Ready").classes("text-grey-6 text-sm")
                
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
    
    def _set_range(self, mode: str) -> None:
        """
        Set a date range preset or enable custom date pickers.

        Supported modes:
        - ALL: no date filtering
        - 1M: last 30 days
        - 3M: last 90 days
        - 1Y: last 365 days
        - CUSTOM: show FROM/TO buttons and allow picking manually

        Args:
            mode: One of the range modes described above.
        """
        logger.info(f"ChartsPage._set_range: mode={mode!r}")
        self.range_state["value"] = mode

        if self.range_btn:
            self.range_btn.text = f"{self.range_labels.get(mode, mode)} ▾"
            self.range_btn.update()

        if mode == "CUSTOM":
            if self.custom_row:
                self.custom_row.style("display:flex")
            return

        if self.custom_row:
            self.custom_row.style("display:none")

        today = date.today()

        if mode == "ALL":
            self.state["date_from"] = None
            self.state["date_to"] = None
        elif mode == "1M":
            self.state["date_from"] = (today - timedelta(days=30)).strftime("%Y-%m-%d")
            self.state["date_to"] = today.strftime("%Y-%m-%d")
        elif mode == "3M":
            self.state["date_from"] = (today - timedelta(days=90)).strftime("%Y-%m-%d")
            self.state["date_to"] = today.strftime("%Y-%m-%d")
        elif mode == "1Y":
            self.state["date_from"] = (today - timedelta(days=365)).strftime("%Y-%m-%d")
            self.state["date_to"] = today.strftime("%Y-%m-%d")

    def _open_date_picker(self, title: str, which: str) -> None:
        """
        Open a date picker dialog and store the result in the page state.

        Args:
            title: Dialog title (e.g. "From date", "To date").
            which: State key to set (expected: "date_from" or "date_to").
        """
        logger.debug(f"ChartsPage._open_date_picker: title={title!r}, which={which!r}")
        dlg = ui.dialog()
        with dlg, ui.card().classes("w-[min(360px,95vw)]"):
            ui.label(title).classes("text-base font-semibold q-mb-sm")

            val = self.state.get(which) or date.today().strftime("%Y-%m-%d")
            picker = ui.date(value=val).classes("w-full")

            with ui.row().classes("justify-end gap-2 q-mt-sm"):
                ui.button("Cancel", on_click=dlg.close).props("flat")

                def _ok():
                    self.state[which] = picker.value
                    dlg.close()

                ui.button("OK", on_click=_ok).props("unelevated color=primary")

        dlg.open()

    def render_manage(self) -> None:
        """
        Render the management controls row:
        - MIC selector
        - symbol multi-select
        - search input
        - chart type / layout / volume checkbox
        - date range presets + custom pickers
        - Sync & Render button
        """
        if not self.manage_card:
            logger.warning("ChartsPage.render_manage: manage_card is not initialized")
            return
        
        self.manage_card.clear()
        with self.manage_card:
            with ui.row().classes("items-center justify-between w-full").style("padding: 10px 18px; gap: 10px; flex-wrap: wrap;"):
                with ui.row().classes("items-center gap-2").style("flex-wrap: wrap;"):
                    mices = list(MIC_CHOICES.keys())

                    self.sel_mic = self.make_select(mices, self.state['mic'], 'Rynek', icon='public')

                    def _on_mic_changed(e):
                        val = e.sender.value
                        if not val:
                            return
                        mic_code = MIC_CHOICES.get(val)
                        ui.navigate.to(f"/stock/charts/{mic_code}")

                    self.sel_mic.on("update:model-value", _on_mic_changed)

                    self.sel_symbols = ui.select(
                        self.state["instrument_options"],
                        value=self.state["selected_symbols"],
                        label="Instruments",
                        multiple=True,
                    ).props("outlined dense use-chips options-dense color=primary") \
                     .classes("min-w-[220px]")

                    def _on_symbols(_):
                        self.state["selected_symbols"] = list(self.sel_symbols.value or [])
                        
                        logger.info(f'self.state["selected_symbols"]: {self.state["selected_symbols"]}')

                    self.sel_symbols.on("update:model-value", _on_symbols)

                    self.search_inp = ui.input(
                        value=self.state["search"],
                        label="Instrument search",
                        placeholder="Symbol or name…",
                    ).props("outlined dense clearable debounce=250").classes("min-w-[220px]")

                    async def _on_search(_):
                        self.state["search"] = self.search_inp.value or ""
                        await self.refresh_instrument_options()

                    self.search_inp.on("update:model-value", lambda _: ui.timer(0.05, _on_search, once=True))

                with ui.row().classes("items-center gap-2").style("flex-wrap: wrap;"):
                    self.chart_type = ui.select(
                        {"candlestick": "Candlestick", "line": "Line"},
                        value=self.state["chart_type"],
                        label="Chart type",
                    ).props("outlined dense options-dense color=primary").classes("min-w-[180px]")

                    self.layout = ui.select(
                        {"separate": "Separate", "combined": "Combined"},
                        value=self.state["layout"],
                        label="Layout",
                    ).props("outlined dense options-dense color=primary").classes("min-w-[160px]")

                    self.chk_volume = ui.checkbox("Volume", value=self.state["show_volume"])
                    
                    self.range_btn = ui.button(
                        f"{self.range_labels.get(self.range_state.get('value'))} ▾",
                        icon="event",
                    )
                    self.range_btn.props("flat color=primary")

                    with self.range_btn:
                        with ui.menu() as m:
                            m.props("offset=[0,8]")
                            ui.menu_item("Last Month", on_click=lambda: self._set_range("1M"))
                            ui.menu_item("Last 3 Months", on_click=lambda: self._set_range("3M"))
                            ui.menu_item("Last Year", on_click=lambda: self._set_range("1Y"))
                            ui.menu_item("All", on_click=lambda: self._set_range("ALL"))
                            ui.separator()
                            ui.menu_item("Date range…", on_click=lambda: self._set_range("CUSTOM"))

                    self.custom_row = ui.row().classes("items-center gap-1").style("display:none")
                    with self.custom_row:
                        ui.button("FROM", 
                                  icon="event", 
                                  on_click=lambda: self._open_date_picker("From date", "date_from")
                                  ).props("flat color=primary")
                        ui.button("TO", 
                                  icon="event", 
                                  on_click=lambda: self._open_date_picker("To date", "date_to")
                                  ).props("flat color=primary")

                    async def _on_render():
                        await self.sync_and_render()

                    ui.button("Sync & Render", on_click=_on_render).props("unelevated color=primary")

        self.chart_type.on("update:model-value", lambda e: self._set_state("chart_type", e.sender.value))
        self.layout.on("update:model-value", lambda e: self._set_state("layout", e.sender.value))
        self.chk_volume.on("update:model-value", lambda e: self._set_state("show_volume", bool(e.value)))
        
        logger.debug("ChartsPage.render_manage: done")

    def _set_state(self, k: str, v: Any) -> None:
        """
        Set a key in the page state.

        Args:
            k: State key.
            v: New value.
        """
        self.state[k] = v

    def render_charts_shell(self) -> None:
        """
        Render the charts output container (cleared on each render).
        """
        self.charts_card.clear()
        with self.charts_card:
            with ui.row().classes("items-start justify-between w-full").style("padding: 12px 18px; flex-wrap: wrap; gap: 14px;"):
                self.charts_area = ui.column().classes("w-full gap-3")

    async def refresh_instrument_options(self) -> None:
        """
        Load instrument list for current MIC and update selector options.

        Notes:
        - Updates:
            * self.state["instrument_options"]
            * self.sel_symbols.options
            * header status label
        """
        mic_label = self.sel_mic.value
        if not mic_label:
            return
        mic_code = MIC_CHOICES.get(mic_label)
        if not mic_code:
            return

        self.status_label.text = f"Loading instruments… ({mic_code})"
        self.status_label.update()

        items = await self.stock_client.list_instruments(mic=mic_code)

        options: dict[str, str] = {}
        for it in items:
            sym = str(it.get("symbol") or "").strip()
            name = str(it.get("name") or "").strip()
            if sym:
                options[sym] = f"{sym} — {name}" if name else sym

        self.state["instrument_options"] = options

        if getattr(self, "sel_symbols", None):
            self.sel_symbols.options = options
            self.sel_symbols.update()

        self.status_label.text = f"Ready ({len(options)} instruments)"
        self.status_label.update()

    async def sync_and_render(self) -> None:
        """
        Sync candles for selected symbols and render charts.

        Flow:
        - Validate selection
        - Resolve date range to `d_from` / `d_to`
        - Call `stock_client.sync_daily_candles(...)` per symbol
        - Fill internal caches
        - Render from cache
        """
        symbols = list(self.state["selected_symbols"] or [])

        if not symbols:
            ui.notify("Select at least one instrument", type="warning")
            return
        
        return_all = True

        d_from = parse_date(self.state.get("date_from"))
        d_to = parse_date(self.state.get("date_to"))
        
        if d_from:
            return_all = False
            if not d_to:
                d_to = date.today()
                self.state["date_to"] = d_to.strftime("%Y-%m-%d")
                logger.info(f"Auto-filled date_to with today: {self.state['date_to']}")

        self.status_label.text = "Syncing…"
        self.status_label.update()

        self._data_cache.clear()
        self._instrument_names.clear()

        for sym in symbols:
            res = await self.stock_client.sync_daily_candles(
                symbol=sym,
                date_from=d_from,
                date_to=d_to,
                include_items=True,              
                return_all=return_all,
                overlap_days=int(self.state["overlap_days"] or 0),
            )
            
            if res is None:
                ui.notify(f"Sync failed: {sym}", type="negative")
                continue

            items = (res.items or []) if getattr(res, "items", None) is not None else []
            self._data_cache[sym] = [it.model_dump() if hasattr(it, "model_dump") else dict(it) for it in items]
            self._instrument_names[sym] = (res.sync.name or "").strip()
            
            logger.info(
                f"sync ok: {sym} fetched={res.sync.fetched_rows} upserted={res.sync.upserted_rows} "
                f"returned={res.returned_count}"
            )

        self.status_label.text = "Rendering…"
        self.status_label.update()

        self.render_charts_from_cache()

        self.status_label.text = "Done"
        self.status_label.update()

    def render_charts_from_cache(self) -> None:
        """
        Render charts based on the current cached candle data.

        Uses:
        - chart_type: "candlestick" | "line"
        - layout: "separate" | "combined"
        - show_volume: bool
        - hlines: horizontal reference levels
        """
        if not self.charts_area:
            logger.warning("ChartsPage.render_charts_from_cache: charts_area not initialized")
            return
        
        self.charts_area.clear()

        chart_type = self.state["chart_type"]
        layout = self.state["layout"]
        show_volume = bool(self.state["show_volume"])
        hlines = list(self.state["hlines"] or [])

        series_map = {sym: items for sym, items in self._data_cache.items() if items}

        if not series_map:
            with self.charts_area:
                ui.label("No data to display (empty response).").classes("text-grey-7")
            return

        if layout == "combined":
            if chart_type == "line" and len(series_map) >= 1:
                with self.charts_area:
                    opts = self.build_line_options(
                        title="Close (overlay)",
                        series_map=series_map,
                        field="close",
                        extra_hlines=hlines,
                    )
                    self._render_echart_with_toolbar(opts, height_px=560, show_top_bar=False)
                return

            if chart_type == "candlestick" and len(series_map) == 1:
                sym = next(iter(series_map.keys()))
                with self.charts_area:
                    opts = self.build_candlestick_options(
                        symbol=sym,
                        items=series_map[sym],
                        show_volume=show_volume,
                        extra_hlines=hlines,
                    )
                    self._render_echart_with_toolbar(opts, height_px=560)
                return

            with self.charts_area:
                ui.label("Combined mode works best for Line charts or a single Candlestick. Showing Separate instead."
                         ).classes("text-grey-7")

        with self.charts_area:
            for sym, items in series_map.items():
                name = getattr(self, "_instrument_names", {}).get(sym, "")
                
                with ui.card().classes("q-pa-md w-full"):
                    with ui.row().classes("items-center justify-between w-full"):
                        title = f"{sym}  -  {name}".strip(" —")
                        ui.label(title).classes("text-subtitle1 truncate max-w-[520px] ml-[50px]").tooltip(title)
                        ui.label(f"{len(items)} points").classes("text-grey-6 text-sm")

                    if chart_type == "candlestick":
                        opts = self.build_candlestick_options(
                            symbol=sym,
                            items=items,
                            show_volume=show_volume,
                            extra_hlines=hlines,
                        )
                        self._render_echart_with_toolbar(opts, height_px=560)
                    else:
                        opts = self.build_line_options(
                            title=f"{sym} close",
                            series_map={sym: items},
                            field="close",
                            extra_hlines=hlines,
                        )
                        self._render_echart_with_toolbar(opts, height_px=560, show_top_bar=False)
    
                                      
@ui.page("/stock/charts/{mic}")
async def charts_route(request: Request, mic: str):
    add_style()
    add_user_style()
    add_table_style()  
    ChartsPage(request, mic)
