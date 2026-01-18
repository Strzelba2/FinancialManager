from nicegui import ui
from typing import Optional
import json
import logging

from utils.utils import fmt_int, fmt_num

logger = logging.getLogger(__name__)


class ChartsDrawMixin:
    
    def build_candlestick_options(
        self,
        symbol: str,
        items: list[dict],
        show_volume: bool,
        extra_hlines: list[float],
    ) -> dict:
        """
        Build ECharts candlestick chart options (option dict) for a single symbol.

        Expected `items` shape (e.g. from SyncDailyResponse.items):
            {
                "date_quote": "YYYY-MM-DD",
                "open":  "...",
                "high":  "...",
                "low":   "...",
                "close": "...",
                "volume": 123
            }

        Args:
            symbol: Instrument symbol displayed on the chart.
            items: List of daily candle dicts (date + OHLC + volume).
            show_volume: If True, adds a second grid with volume bars.
            extra_hlines: Horizontal mark lines (y-axis values).

        Returns:
            ECharts options dict ready to be passed into the chart component.
        """
        xs: list[str] = [str(it.get("date_quote")) for it in items]

        candles: list[list[Optional[float]]] = []
        vols: list[Optional[float]] = []
        for it in items:
            o = fmt_num(it.get("open"))
            c = fmt_num(it.get("close"))
            lo = fmt_num(it.get("low"))
            hi = fmt_num(it.get("high"))
            candles.append([o, c, lo, hi])
            vols.append(fmt_int(it.get("volume")))

        mark_lines = []
        for y in extra_hlines:
            mark_lines.append({"yAxis": y})
            
        LEFT = 50

        grid = [{"left": LEFT, "right": 25, "top": 40, "bottom": 90, "containLabel": False}]
        x_axes = [{"type": "category", "data": xs, "boundaryGap": True, "axisLabel": {"hideOverlap": True}}]
        y_axes = [{"scale": True, "splitLine": {"show": True}}]

        series = [
            {
                "name": symbol,
                "type": "candlestick",
                "data": candles,
                "itemStyle": {
                    "color": "#16a34a",       
                    "color0": "#dc2626",    
                    "borderColor": "#16a34a",
                    "borderColor0": "#dc2626",
                },
                "markLine": {"symbol": ["none", "none"], "data": mark_lines} if mark_lines else {},
            }
        ]

        if show_volume:
            logger.debug("build_candlestick_options: adding volume bar subplot")
            grid = [
                {"left": LEFT, "right": 25, "top": 40, "height": "55%", "containLabel": False},
                {"left": LEFT, "right": 25, "top": "72%", "height": "18%", "containLabel": False},
            ]
            x_axes = [
                {"type": "category", "data": xs, "boundaryGap": True, "axisLabel": {"show": False}},
                {"type": "category", "gridIndex": 1, "data": xs, "boundaryGap": True, "axisLabel": {"hideOverlap": True}},
            ]
            y_axes = [
                {"scale": True, "splitLine": {"show": True}},
                {
                    "gridIndex": 1,
                    "splitNumber": 2,
                    "scale": True,
                    "minInterval": 1,               
                    "axisLabel": {"hideOverlap": True},
                },
            ]
            series.append(
                {
                    "name": "Volume",
                    "type": "bar",
                    "xAxisIndex": 1,
                    "yAxisIndex": 1,
                    "data": vols,
                }
            )

        return {
            "title": {"left": "center"},
            "tooltip": {"trigger": "axis"},
            "axisPointer": {"link": [{"xAxisIndex": "all"}]},
            "toolbox": {
                "feature": {
                    "dataZoom": {"yAxisIndex": "none"},
                    "restore": {},
                    "saveAsImage": {},
                }
            },
            "dataZoom": [
                {"type": "inside", "xAxisIndex": [0, 1] if show_volume else [0]},
                {"type": "slider", "xAxisIndex": [0, 1] if show_volume else [0]},
            ],
            "grid": grid,
            "xAxis": x_axes,
            "yAxis": y_axes,
            "series": series,
        }

    def build_line_options(
        self,
        title: str,
        series_map: dict[str, list[dict]],
        field: str = "close",  
        extra_hlines: list[float] = (),
    ) -> dict:
        """
        Build ECharts multi-series line chart options (option dict).

        The chart will include one line per symbol from `series_map`.
        X-axis is the union of all dates across all symbols.

        Args:
            title: Chart title (displayed at the top).
            series_map: Map of {symbol -> list of candle dicts}, each dict must include "date_quote".
            field: Candle field to chart (default: "close").
            extra_hlines: Horizontal mark lines (y-axis values).

        Returns:
            ECharts options dict ready to be passed into the chart component.
        """
    
        all_dates: list[str] = sorted({str(it["date_quote"]) for items in series_map.values() for it in items})

        series = []
        for sym, items in series_map.items():
            by_date = {str(it["date_quote"]): fmt_num(it.get(field)) for it in items}
            data = [by_date.get(d) for d in all_dates]
            series.append({"name": sym, "type": "line", "showSymbol": False, "data": data})

        mark_lines = [{"yAxis": float(y)} for y in extra_hlines] if extra_hlines else []

        return {
            "title": {"text": title, "left": "center"},
            "tooltip": {"trigger": "axis"},
            "legend": {"top": 28},
            "grid": {
                "left": 40,          
                "right": 25,
                "top": 70,
                "bottom": 35,
                "containLabel": True,  
            },
            "toolbox": {
                "feature": {
                    "dataZoom": {"yAxisIndex": "none"},
                    "restore": {},
                    "saveAsImage": {},
                }
            },
            "dataZoom": [{"type": "inside"}, {"type": "slider"}],
            "xAxis": {"type": "category", "data": all_dates},
            "yAxis": {"type": "value", "scale": True},
            "series": series,
            "markLine": {"symbol": ["none", "none"], "data": mark_lines} if mark_lines else {},
        }
        
    def _chart_state_key(self, opts: dict) -> str:
        """
        Build a stable key for saving/restoring analysis state per chart.

        Strategy:
        - Looks at the first series in `opts["series"]`
        - Uses series name and type to generate a stable storage key
        * candlestick -> "candles:<symbol>"
        * other types -> "chart:<name>"
        - Falls back to "chart:default" if name/type is missing or invalid

        Args:
            opts: ECharts options dict (must contain "series" list to be precise).

        Returns:
            Stable storage key string for chart analysis persistence.
        """
        try:
            s0 = (opts.get("series") or [{}])[0]
            name = s0.get("name") or ""
            typ = s0.get("type") or ""
            if name and typ == "candlestick":
                return f"candles:{name}"
            if name:
                return f"chart:{name}"
        except Exception as ex:
            logger.debug(f"_chart_state_key: failed to build key: {ex!r}")
        return "chart:default"
    
    def _render_echart_with_toolbar(self, opts: dict, height_px: int = 560, show_top_bar: bool = True) -> None:
        """
        Render an ECharts widget with a vertical analysis toolbar and optional top bar.

        Features:
        - Draw tools: trend line, horizontal line, vertical line, channel
        - Crosshair toggle
        - Undo last draw
        - Save analysis state (persist plugin)
        - Clear all drawings
        - Optional top bar:
            * fullscreen toggle
            * interval aggregation selector (D/W/M)
            * indicator selector (SMA / Bollinger Bands)

        Args:
            opts: ECharts options dict.
            height_px: Chart height in pixels.
            show_top_bar: If True, renders the extra controls row above the chart.

        Returns:
            None
        """
        cid_ref = {"id": ""}
        
        def _attach_plugins(_cid: str) -> None:
            """
            Attach custom JS plugins to the ECharts instance.

            Args:
                _cid: Fully formatted cid string, e.g. "c123".
            """
            js = [
                f'window.NG_ECHART_DRAW?.attach("{_cid}");',
                f'window.NG_ECHART_VOLFMT?.attach("{_cid}");',
                f'window.NG_ECHART_PERSIST?.load("{_cid}", {json.dumps(self._chart_state_key(opts))});',
            ]
            if show_top_bar:
                js += [
                    f'window.NG_ECHART_AGG?.attach("{_cid}");',
                    f'window.NG_ECHART_IND?.attach("{_cid}");',
                ]
            ui.run_javascript("\n".join(js))

        def _js(template: str) -> None:
            """
            Run a JS template that requires `{cid}` formatting.

            Args:
                template: JS string template containing "{cid}" placeholder.
            """
            if not cid_ref["id"]:
                ui.notify("Chart not ready yet", type="warning")
                return
            cid = f'c{cid_ref["id"]}'
            ui.run_javascript(template.format(cid=cid))
            
        def _cid() -> str:
            """Return the chart DOM id in your convention: c<chart.id>."""
            return f'c{cid_ref["id"]}'
            
        def _js_raw(js: str) -> None:
            """
            Run raw JS with "__CID__" placeholder replacement.

            Args:
                js: JS string containing "__CID__" placeholder.
            """
            if not cid_ref["id"]:
                ui.notify("Chart not ready yet", type="warning")
                return
            ui.run_javascript(js.replace("__CID__", _cid()))

        with ui.row().classes("w-full items-start gap-2 no-wrap").style("flex-wrap: nowrap;"):
            with ui.card().classes("q-pa-xs").style(
                f"""
                width:54px; min-width:54px; border-radius:8px;
                flex:0 0 54px;
                margin-top: 18px;
                height: {int(height_px * 0.72)}px;
                display:flex;
                """
            ):
                with ui.column().classes("gap-1 items-center").style("padding:10px 2px; height:100%; width:100%;"):
                    ui.button(icon="timeline").props("round flat color=primary").tooltip("Trend line").on_click(
                        lambda: _js('window.NG_ECHART_DRAW?.setMode("{cid}", "trend")')
                    )
                    ui.button(icon="horizontal_rule").props("round flat color=primary").tooltip("Horizontal line").on_click(
                        lambda: _js('window.NG_ECHART_DRAW?.setMode("{cid}", "hline")')
                    )
                    ui.button(icon="vertical_align_center").props("round flat color=primary").tooltip("Vertical line").on_click(
                        lambda: _js('window.NG_ECHART_DRAW?.setMode("{cid}", "vline")')
                    )
                    ui.button(icon="stacked_line_chart").props("round flat color=primary").tooltip("Channel (parallel)").on_click(
                        lambda: _js('window.NG_ECHART_DRAW?.setMode("{cid}", "channel")')
                    )

                    ui.separator()

                    (ui.button(icon="center_focus_strong")
                        .props("round flat color=primary")
                        .tooltip("Toggle crosshair / tooltip")
                        .on_click(
                            lambda: _js('window.NG_ECHART_DRAW?.toggleCrosshair("{cid}")')
                        )
                     )

                    ui.separator()

                    ui.button(icon="undo").props("round flat color=primary").tooltip("Undo last").on_click(
                        lambda: _js('window.NG_ECHART_DRAW?.undo("{cid}")')
                    )
                    ui.button(icon="save").props("round flat color=primary").tooltip("Save analysis").on_click(
                        lambda: _js_raw(f'window.NG_ECHART_PERSIST?.save("__CID__", {json.dumps(self._chart_state_key(opts))})')
                    )
                    ui.button(icon="delete_sweep").props("round flat color=negative").tooltip("Clear all").on_click(
                        lambda: _js('window.NG_ECHART_DRAW?.clear("{cid}")')
                    )

            with ui.column().classes("flex-1 min-w-0").style("gap:8px;"):
                if show_top_bar:
                    with ui.card().classes("q-pa-xs").style(
                        """
                        margin-left: 20px;
                        border-radius:10px;
                        background: rgba(255,255,255,.92);
                        border: 1px solid rgba(2,6,23,.10);
                        box-shadow: 0 8px 20px rgba(15,23,42,.08);
                        """
                    ):
                        with ui.row().classes("items-center gap-2"):
                            ui.button(icon="fullscreen").props("dense flat").tooltip("Fullscreen").on_click(
                                lambda: _js_raw('window.NG_ECHART_UI?.toggleFullscreen("__CID__")')
                            )

                            interval = ui.select(
                                {"D": "Daily", "W": "Weekly", "M": "Monthly"},
                                value="D",
                                label="Interval",
                            ).props("dense outlined options-dense").classes("w-[160px]")

                            indicators = ui.select(
                                {"sma-1": "SMA-1", "sma-2": "SMA-2", "sma-3": "SMA-3", "bb": "Bollinger Bands"},
                                value=[],
                                label="Indicators",
                                multiple=True,
                            ).props("dense outlined options-dense use-chips").classes("w-[260px]")

                    def _set_interval(e):
                        """
                        Handle aggregation interval selection changes (D/W/M).
                        """
                        
                        val = e.sender.value or "D"
                        
                        logger.info(f"val: {val}")
                        _js_raw(f'window.NG_ECHART_AGG?.setInterval("__CID__", {json.dumps(val)})')

                    interval.on("update:model-value", _set_interval)

                    def _set_indicators(e):
                        """
                        Handle indicator selection changes (SMA / BB).
                        """
                        vals = list(e.sender.value or [])
                        logger.info(f"vals: {vals}")
                        logger.info(f"{json.dumps(vals)}")
                        _js_raw(f'window.NG_ECHART_IND?.setEnabled("__CID__", {json.dumps(vals)})')

                    indicators.on("update:model-value", _set_indicators)

                chart = ui.echart(opts).classes("w-full").style(f"height: {height_px}px;")
                cid_ref["id"] = chart.id 
                
                ui.timer(
                    0.25,
                    lambda _cid=f"c{chart.id}": _attach_plugins(_cid),
                    once=True,
                )
                                
    def _echart_draw_js(self) -> str:
        """
        Return the JavaScript bundle that extends ECharts with analysis tools.

        This JS is injected into the browser (typically via NiceGUI `ui.add_head_html(...)`)
        and registers multiple helper modules under `window.*`, such as:
        - window.NG_ECHART_DRAW: drawing annotations (trend / hline / vline / channel)
        - window.NG_ECHART_VOLFMT: volume axis formatting (K/M/B style)
        - window.NG_ECHART_UI: fullscreen helpers
        - window.NG_ECHART_AGG: client-side aggregation (D/W/M)
        - window.NG_ECHART_IND: indicators (SMA / Bollinger Bands)
        - window.NG_ECHART_PERSIST: save/load analysis state to storage

        Notes:
        - The JS is idempotent: it uses `window.__NG_ECHART_DRAW_LOADED__` guard
        to prevent duplicate initialization.
        - The returned string is raw JS source and should be executed on the client.

        Returns:
            A raw JavaScript string with the full ECharts plugin implementation.
        """
        return r"""
            (function () {
            if (window.__NG_ECHART_DRAW_LOADED__) {
                console.log("[NG_ECHART_DRAW] already loaded");
                return;
            }
            window.__NG_ECHART_DRAW_LOADED__ = true;

            var DEBUG = true;
            function log() { if (DEBUG) console.log.apply(console, ["[NG_ECHART_DRAW]"].concat([].slice.call(arguments))); }

            var STORE = new Map(); // domId -> state
            var CTX = null;

            function resolveDomId(anyId) {
                if (!anyId) return null;
                var s = String(anyId);
                if (document.getElementById(s)) return s;
                if (s[0] !== "c" && document.getElementById("c" + s)) return "c" + s;
                return s;
            }

            function getChartInstance(domId) {
                if (!domId || !window.echarts) return null;
                var root = document.getElementById(domId);
                if (!root) return null;

                var inst = window.echarts.getInstanceByDom(root);
                if (inst) return inst;

                // fallback for unusual DOM nesting
                var inner = root.querySelector && root.querySelector('[_echarts_instance_]');
                if (inner) {
                inst = window.echarts.getInstanceByDom(inner);
                if (inst) return inst;
                }
                return null;
            }

            function gridRect(chart) {
                try {
                var grid = chart.getModel().getComponent("grid", 0);
                return grid.coordinateSystem.getRect();
                } catch (e) { return null; }
            }

            function inRect(px, rect) {
                return px[0] >= rect.x && px[0] <= rect.x + rect.width && px[1] >= rect.y && px[1] <= rect.y + rect.height;
            }

            function toData(chart, px) {
                try { return chart.convertFromPixel({ xAxisIndex: 0, yAxisIndex: 0 }, px); }
                catch (e) { return null; }
            }

            function toPx(chart, data) {
                try { return chart.convertToPixel({ xAxisIndex: 0, yAxisIndex: 0 }, data); }
                catch (e) { return null; }
            }

            function deepClone(x) {
                try { return JSON.parse(JSON.stringify(x)); } catch (e) { return null; }
            }

            function ensureContextMenu() {
                if (CTX) return;

                CTX = document.createElement("div");
                CTX.style.cssText =
                "position:fixed;" +
                "display:none;" +
                "z-index:99999999;" +
                "background:#fff;" +
                "border:1px solid rgba(2,6,23,.12);" +
                "border-radius:10px;" +
                "box-shadow:0 12px 30px rgba(15,23,42,.18);" +
                "padding:8px;" +
                "font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;" +
                "font-size:13px;" +
                "min-width:200px;" +
                "user-select:none;";
                document.body.appendChild(CTX);

                window.addEventListener("mousedown", function (e) {
                if (CTX.style.display === "block" && !CTX.contains(e.target)) hideMenu();
                }, true);

                window.addEventListener("keydown", function (e) {
                if (e.key === "Escape") hideMenu();
                }, true);
            }

            function hideMenu() {
                if (!CTX) return;
                CTX.style.display = "none";
                CTX._target = null;
            }

            function menuItem(label, onClick) {
                var b = document.createElement("button");
                b.textContent = label;
                b.style.cssText =
                "display:block;" +
                "width:100%;" +
                "text-align:left;" +
                "padding:8px 10px;" +
                "margin:0;" +
                "border:0;" +
                "background:transparent;" +
                "cursor:pointer;" +
                "border-radius:8px;";
                b.addEventListener("mouseenter", function () { b.style.background = "rgba(2,6,23,.06)"; });
                b.addEventListener("mouseleave", function () { b.style.background = "transparent"; });
                b.addEventListener("click", function (e) {
                e.preventDefault(); e.stopPropagation();
                onClick();
                });
                return b;
            }

            function menuSep() {
                var d = document.createElement("div");
                d.style.cssText = "height:1px;background:rgba(2,6,23,.10);margin:6px 0;";
                return d;
            }

            function defaultStyle() { return { color: "#111827", width: 1 }; }

            function nextId(st) { return "a" + Date.now().toString(36) + "_" + (st.annos.length + 1); }

            function scheduleRender(st) {
                if (st._raf) return;
                st._raf = requestAnimationFrame(function () {
                st._raf = null;
                render(st);
                });
            }

            function applyCrosshair(st) {
                if (!st) return;

                if (st.crosshairOn) {
                // restore originals
                if (st._origTooltip != null) st.chart.setOption({ tooltip: deepClone(st._origTooltip) }, { lazyUpdate: true });
                if (st._origAxisPointer != null) st.chart.setOption({ axisPointer: deepClone(st._origAxisPointer) }, { lazyUpdate: true });
                } else {
                // simplest: fully disable tooltip (removes crosshair + labels)
                st.chart.setOption({ tooltip: { show: false }, axisPointer: { link: [] } }, { lazyUpdate: true });
                }
            }

            function distPointToSegment(p, a, b) {
                var x = p[0], y = p[1];
                var x1 = a[0], y1 = a[1];
                var x2 = b[0], y2 = b[1];
                var dx = x2 - x1, dy = y2 - y1;
                if (dx === 0 && dy === 0) return Math.hypot(x - x1, y - y1);
                var t = ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy);
                var tt = Math.max(0, Math.min(1, t));
                var xx = x1 + tt * dx, yy = y1 + tt * dy;
                return Math.hypot(x - xx, y - yy);
            }

            function pick(st, px) {
                var chart = st.chart;
                var rect = gridRect(chart);
                if (!rect) return null;

                var TH_LINE = 6;
                var TH_HANDLE = 10;

                var best = null;
                var bestDist = 1e9;

                for (var i = 0; i < st.annos.length; i++) {
                var a = st.annos[i];

                if (a.type === "trend") {
                    var p1 = toPx(chart, [a.x1, a.y1]);
                    var p2 = toPx(chart, [a.x2, a.y2]);
                    if (!p1 || !p2) continue;

                    var d1 = Math.hypot(px[0] - p1[0], px[1] - p1[1]);
                    var d2 = Math.hypot(px[0] - p2[0], px[1] - p2[1]);
                    if (d1 < TH_HANDLE) return { id: a.id, part: "p1" };
                    if (d2 < TH_HANDLE) return { id: a.id, part: "p2" };

                    var dl = distPointToSegment(px, p1, p2);
                    if (dl < TH_LINE && dl < bestDist) { best = { id: a.id, part: "line" }; bestDist = dl; }
                }

                if (a.type === "hline") {
                    var mid = toData(chart, [rect.x + rect.width * 0.5, rect.y + rect.height * 0.5]);
                    if (!mid) continue;
                    var ypx = toPx(chart, [mid[0], a.y]);
                    if (!ypx) continue;
                    var dh = Math.abs(px[1] - ypx[1]);
                    if (dh < TH_LINE && dh < bestDist) { best = { id: a.id, part: "line" }; bestDist = dh; }
                }

                if (a.type === "vline") {
                    var mid2 = toData(chart, [rect.x + rect.width * 0.5, rect.y + rect.height * 0.5]);
                    if (!mid2) continue;
                    var xpx = toPx(chart, [a.x, mid2[1]]);
                    if (!xpx) continue;
                    var dv = Math.abs(px[0] - xpx[0]);
                    if (dv < TH_LINE && dv < bestDist) { best = { id: a.id, part: "line" }; bestDist = dv; }
                }

                if (a.type === "channel") {
                    var bp1 = toPx(chart, [a.x1, a.y1]);
                    var bp2 = toPx(chart, [a.x2, a.y2]);
                    var pp1 = toPx(chart, [a.x1, a.y1 + a.dy]);
                    var pp2 = toPx(chart, [a.x2, a.y2 + a.dy]);

                    if (bp1 && bp2) {
                    var bd1 = Math.hypot(px[0] - bp1[0], px[1] - bp1[1]);
                    var bd2 = Math.hypot(px[0] - bp2[0], px[1] - bp2[1]);
                    if (bd1 < TH_HANDLE) return { id: a.id, part: "p1" };
                    if (bd2 < TH_HANDLE) return { id: a.id, part: "p2" };

                    var bdl = distPointToSegment(px, bp1, bp2);
                    if (bdl < TH_LINE && bdl < bestDist) { best = { id: a.id, part: "base" }; bestDist = bdl; }
                    }

                    if (pp1 && pp2) {
                    var pdl = distPointToSegment(px, pp1, pp2);
                    if (pdl < TH_LINE && pdl < bestDist) { best = { id: a.id, part: "parallel" }; bestDist = pdl; }
                    }
                }
                }
                return best;
            }

            function showContextMenu(st, annoId, clientX, clientY) {
                ensureContextMenu();
                hideMenu();

                var a = null;
                for (var i = 0; i < st.annos.length; i++) if (st.annos[i].id === annoId) { a = st.annos[i]; break; }
                if (!a) return;

                CTX.innerHTML = "";
                CTX._target = { domId: st.domId, annoId: annoId };

                function setColor(c) { a.style = a.style || defaultStyle(); a.style.color = c; hideMenu(); scheduleRender(st); }
                function setWidth(w) { a.style = a.style || defaultStyle(); a.style.width = w; hideMenu(); scheduleRender(st); }
                function del() {
                st.annos = st.annos.filter(function (x) { return x.id !== annoId; });
                if (st.selectedId === annoId) st.selectedId = null;
                hideMenu(); scheduleRender(st);
                }

                CTX.appendChild(menuItem("Delete", del));
                CTX.appendChild(menuSep());

                CTX.appendChild(menuItem("Color", function () {}));
                var colors = [
                ["Black", "#111827"], ["Blue", "#2563eb"], ["Green", "#16a34a"],
                ["Red", "#dc2626"], ["Purple", "#7c3aed"], ["Orange", "#f59e0b"]
                ];
                for (var i = 0; i < colors.length; i++) {
                (function (name, c) { CTX.appendChild(menuItem("• " + name, function () { setColor(c); })); })(colors[i][0], colors[i][1]);
                }

                CTX.appendChild(menuSep());
                CTX.appendChild(menuItem("Width", function () {}));
                var widths = [1, 1.5, 2, 3];
                for (var j = 0; j < widths.length; j++) {
                (function (w) { CTX.appendChild(menuItem("• " + w, function () { setWidth(w); })); })(widths[j]);
                }

                var vw = window.innerWidth, vh = window.innerHeight;
                CTX.style.left = Math.min(clientX, vw - 230) + "px";
                CTX.style.top  = Math.min(clientY, vh - 280) + "px";
                CTX.style.display = "block";
            }

            function styleFor(st, a) {
                var s = (a && a.style) ? a.style : defaultStyle();
                var isSel = (st.selectedId === a.id);
                return {
                stroke: s.color || "#111827",
                lineWidth: (s.width || 1) + (isSel ? 0.8 : 0),
                opacity: 0.95
                };
            }

            function render(st) {
                if (!st) return;

                var rect = gridRect(st.chart);
                
                if (!rect) return;

                var els = [];
                var chart = st.chart;

                function addLine(x1, y1, x2, y2, style, dashed, showHandles, annoId, handleBase) {
                var p1 = toPx(chart, [x1, y1]);
                var p2 = toPx(chart, [x2, y2]);
                if (!p1 || !p2) return;

                var dash = dashed ? [6, 4] : null;
                var stl = { stroke: style.stroke, lineWidth: style.lineWidth, opacity: style.opacity };
                if (dash) stl.lineDash = dash;

                els.push({ id: annoId + ":line:" + handleBase, type: "line", silent: true,
                    shape: { x1: p1[0], y1: p1[1], x2: p2[0], y2: p2[1] }, style: stl
                });

                if (showHandles) {
                    els.push({ id: annoId + ":h1:" + handleBase, type: "circle", silent: true,
                    shape: { cx: p1[0], cy: p1[1], r: 5 }, style: { fill: style.stroke, opacity: 0.95 }
                    });
                    els.push({ id: annoId + ":h2:" + handleBase, type: "circle", silent: true,
                    shape: { cx: p2[0], cy: p2[1], r: 5 }, style: { fill: style.stroke, opacity: 0.95 }
                    });
                }
                }

                function addHLine(y, style, dashed, annoId) {
                var mid = toData(chart, [rect.x + rect.width * 0.5, rect.y + rect.height * 0.5]);
                if (!mid) return;
                var p = toPx(chart, [mid[0], y]);
                if (!p) return;
                var stl = { stroke: style.stroke, lineWidth: style.lineWidth, opacity: style.opacity };
                if (dashed) stl.lineDash = [6, 4];
                els.push({ id: annoId + ":hline", type: "line", silent: true,
                    shape: { x1: rect.x, y1: p[1], x2: rect.x + rect.width, y2: p[1] }, style: stl
                });
                }

                function addVLine(x, style, dashed, annoId) {
                var mid = toData(chart, [rect.x + rect.width * 0.5, rect.y + rect.height * 0.5]);
                if (!mid) return;
                var p = toPx(chart, [x, mid[1]]);
                if (!p) return;
                var stl = { stroke: style.stroke, lineWidth: style.lineWidth, opacity: style.opacity };
                if (dashed) stl.lineDash = [6, 4];
                els.push({ id: annoId + ":vline", type: "line", silent: true,
                    shape: { x1: p[0], y1: rect.y, x2: p[0], y2: rect.y + rect.height }, style: stl
                });
                }

                // existing
                for (var i = 0; i < st.annos.length; i++) {
                var a = st.annos[i];
                var stl = styleFor(st, a);
                var showHandles = (st.selectedId === a.id);

                if (a.type === "trend") {
                    addLine(a.x1, a.y1, a.x2, a.y2, stl, false, showHandles, a.id, "trend");
                } else if (a.type === "hline") {
                    addHLine(a.y, stl, false, a.id);
                } else if (a.type === "vline") {
                    addVLine(a.x, stl, false, a.id);
                } else if (a.type === "channel") {
                    // base: handles when selected
                    addLine(a.x1, a.y1, a.x2, a.y2, stl, false, showHandles, a.id, "base");
                    // parallel: no handles (ever)
                    addLine(a.x1, a.y1 + a.dy, a.x2, a.y2 + a.dy, stl, false, false, a.id, "par");
                }
                }

                if (st.mode && st.cursorPx && inRect(st.cursorPx, rect)) {
                var d = toData(chart, st.cursorPx);
                if (d) {
                    var pv = { stroke: "#94a3b8", lineWidth: 1, opacity: 0.9 };

                    if (st.mode === "trend") {
                    if (st.stage === 1 && st.start) addLine(st.start.x, st.start.y, d[0], d[1], pv, true, false, "__pv__", "t");
                    }
                    if (st.mode === "hline") addHLine(d[1], pv, true, "__pv__");
                    if (st.mode === "vline") addVLine(d[0], pv, true, "__pv__");

                    if (st.mode === "channel") {
                    if (st.stage === 1 && st.start) {
                        addLine(st.start.x, st.start.y, d[0], d[1], pv, true, false, "__pv__", "c1");
                    } else if (st.stage === 2 && st.base) {
                        var b = st.base;
                        addLine(b.x1, b.y1, b.x2, b.y2, pv, true, false, "__pv__", "cb");

                        var xCur = d[0], yCur = d[1];
                        var dx = (b.x2 - b.x1);
                        var t = (dx === 0) ? 0 : ((xCur - b.x1) / dx);
                        var yBase = b.y1 + t * (b.y2 - b.y1);
                        st.dyPreview = (yCur - yBase);

                        addLine(b.x1, b.y1 + st.dyPreview, b.x2, b.y2 + st.dyPreview, pv, true, false, "__pv__", "cp");
                    }
                    }
                }
                }

                var wrapped = [{
                id: "__ng_draw_layer__",
                type: "group",
                x: 0,
                y: 0,
                silent: true,
                clipPath: {
                    type: "rect",
                    shape: { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
                },
                children: els
                }];

                st.chart.setOption(
                { graphic: { elements: wrapped } },
                { lazyUpdate: true, replaceMerge: ["graphic"] }
                );
            }

            function attach(anyId) {
                var domId = resolveDomId(anyId);
                var chart = getChartInstance(domId);
                if (!chart) { log("attach failed (no chart)", anyId, domId); return; }

                if (STORE.has(domId)) { log("already attached", domId); return; }

                var opt = chart.getOption ? chart.getOption() : {};
                var st = {
                domId: domId,
                chart: chart,
                zr: chart.getZr(),
                annos: [],
                selectedId: null,

                mode: null,        
                stage: 0,          
                start: null,       
                base: null,         
                dyPreview: null,    
                cursorPx: null,

                // dragging
                drag: null,       
                _raf: null,

                // crosshair
                _origTooltip: deepClone(opt.tooltip),
                _origAxisPointer: deepClone(opt.axisPointer),
                crosshairOn: false, 
                };

                STORE.set(domId, st);
                
                st.chart.on("dataZoom", function () { scheduleRender(st); });
                st.chart.on("restore", function () { scheduleRender(st); });
                st.chart.on("finished", function () { scheduleRender(st); });

                window.addEventListener("resize", function () { scheduleRender(st); });

                applyCrosshair(st);

                ensureContextMenu();

                var root = document.getElementById(domId);
                if (root) {
                root.addEventListener("contextmenu", function (e) { e.preventDefault(); }, { passive: false });
                }

                st.zr.on("mousemove", function (ev) {
                var e = ev.event || ev;
                st.cursorPx = [e.offsetX, e.offsetY];

                if (st.drag) {
                    var curData = toData(st.chart, st.cursorPx);
                    if (!curData) return;

                    var a = null;
                    for (var i = 0; i < st.annos.length; i++) if (st.annos[i].id === st.drag.id) { a = st.annos[i]; break; }
                    if (!a) return;

                    var dx = curData[0] - st.drag.startData[0];
                    var dy = curData[1] - st.drag.startData[1];

                    var base = st.drag.startAnnoClone;

                    if (a.type === "trend") {
                    if (st.drag.part === "p1") { a.x1 = curData[0]; a.y1 = curData[1]; }
                    else if (st.drag.part === "p2") { a.x2 = curData[0]; a.y2 = curData[1]; }
                    else { a.x1 = base.x1 + dx; a.y1 = base.y1 + dy; a.x2 = base.x2 + dx; a.y2 = base.y2 + dy; }
                    }

                    if (a.type === "hline") a.y = curData[1];
                    if (a.type === "vline") a.x = curData[0];

                    if (a.type === "channel") {
                    if (st.drag.part === "p1") { a.x1 = curData[0]; a.y1 = curData[1]; }
                    else if (st.drag.part === "p2") { a.x2 = curData[0]; a.y2 = curData[1]; }
                    else if (st.drag.part === "base") {
                        a.x1 = base.x1 + dx; a.y1 = base.y1 + dy;
                        a.x2 = base.x2 + dx; a.y2 = base.y2 + dy;
                    } else if (st.drag.part === "parallel") {
                        // only change offset (vertical)
                        a.dy = base.dy + dy;
                    }
                    }

                    scheduleRender(st);
                    return;
                }

                // update preview while drawing
                if (st.mode) scheduleRender(st);
                });

                st.zr.on("click", function (ev) {
                var e = ev.event || ev;
                var px = [e.offsetX, e.offsetY];
                var rect = gridRect(st.chart);
                if (!rect || !inRect(px, rect)) return;

                if (!st.mode) {
                    // selection
                    var hit = pick(st, px);
                    st.selectedId = hit ? hit.id : null;
                    hideMenu();
                    scheduleRender(st);
                    return;
                }

                var d = toData(st.chart, px);
                if (!d) return;
                var x = d[0], y = d[1];

                if (st.mode === "trend") {
                    if (st.stage === 0) {
                    st.start = { x: x, y: y };
                    st.stage = 1;
                    } else {
                    var id = nextId(st);
                    st.annos.push({ id: id, type: "trend", x1: st.start.x, y1: st.start.y, x2: x, y2: y, style: defaultStyle() });
                    st.selectedId = id;

                    st.mode = null; st.stage = 0; st.start = null;
                    }
                    scheduleRender(st);
                    return;
                }

                if (st.mode === "hline") {
                    var hid = nextId(st);
                    st.annos.push({ id: hid, type: "hline", y: y, style: defaultStyle() });
                    st.selectedId = hid;
                    st.mode = null; st.stage = 0;
                    scheduleRender(st);
                    return;
                }

                if (st.mode === "vline") {
                    var vid = nextId(st);
                    st.annos.push({ id: vid, type: "vline", x: x, style: defaultStyle() });
                    st.selectedId = vid;
                    st.mode = null; st.stage = 0;
                    scheduleRender(st);
                    return;
                }

                if (st.mode === "channel") {
                    if (st.stage === 0) {
                    st.start = { x: x, y: y };
                    st.stage = 1;
                    scheduleRender(st);
                    return;
                    }
                    if (st.stage === 1) {
                    st.base = { x1: st.start.x, y1: st.start.y, x2: x, y2: y };
                    st.stage = 2;
                    scheduleRender(st);
                    return;
                    }
                    if (st.stage === 2) {
                    var dy = (st.dyPreview == null) ? 0 : st.dyPreview;
                    var cid = nextId(st);
                    st.annos.push({ id: cid, type: "channel", x1: st.base.x1, y1: st.base.y1, x2: st.base.x2, y2: st.base.y2, dy: dy, style: defaultStyle() });
                    st.selectedId = cid;

                    st.mode = null; st.stage = 0; st.start = null; st.base = null; st.dyPreview = null;
                    scheduleRender(st);
                    return;
                    }
                }
                });

                st.zr.on("mousedown", function (ev) {
                var e = ev.event || ev;
                if (e.button !== 0) return;
                if (st.mode) return; // no dragging while drawing

                var px = [e.offsetX, e.offsetY];
                var rect = gridRect(st.chart);
                if (!rect || !inRect(px, rect)) return;

                var hit = pick(st, px);
                if (!hit) return;

                var d = toData(st.chart, px);
                if (!d) return;

                var a = null;
                for (var i = 0; i < st.annos.length; i++) if (st.annos[i].id === hit.id) { a = st.annos[i]; break; }
                if (!a) return;

                st.selectedId = hit.id;

                var clone = deepClone(a) || {};
                st.drag = { id: hit.id, part: hit.part, startData: d, startAnnoClone: clone };

                hideMenu();
                scheduleRender(st);
                });

                st.zr.on("mouseup", function () { st.drag = null; });

                if (root) {
                root.addEventListener("contextmenu", function (e) {
                    e.preventDefault();

                    if (st.mode) return; // don't style while drawing
                    var r = root.getBoundingClientRect();
                    var px = [e.clientX - r.left, e.clientY - r.top];
                    var rect = gridRect(st.chart);
                    if (!rect || !inRect(px, rect)) return;

                    var hit = pick(st, px);
                    if (!hit) { hideMenu(); return; }

                    st.selectedId = hit.id;
                    scheduleRender(st);
                    showContextMenu(st, hit.id, e.clientX, e.clientY);
                }, { passive: false });
                }

                window.addEventListener("keydown", function (e) {
                if (e.key !== "Escape") return;
                if (!st.mode) return;
                st.mode = null; st.stage = 0; st.start = null; st.base = null; st.dyPreview = null;
                scheduleRender(st);
                });

                scheduleRender(st);
                log("attached OK", domId);
            }

            window.NG_ECHART_DRAW = {
                attach: function (anyId) { attach(anyId); },

                setMode: function (anyId, mode) {
                var domId = resolveDomId(anyId);
                var st = STORE.get(domId);
                if (!st) { attach(domId); st = STORE.get(domId); }
                if (!st) return;

                st.mode = String(mode || "") || null;
                st.stage = 0;
                st.start = null;
                st.base = null;
                st.dyPreview = null;
                hideMenu();
                scheduleRender(st);
                },

                undo: function (anyId) {
                var st = STORE.get(resolveDomId(anyId));
                if (!st) return;
                st.annos.pop();
                if (st.selectedId && !st.annos.some(function (a) { return a.id === st.selectedId; })) st.selectedId = null;
                hideMenu();
                scheduleRender(st);
                },

                clear: function (anyId) {
                var st = STORE.get(resolveDomId(anyId));
                if (!st) return;
                st.annos = [];
                st.selectedId = null;
                st.mode = null; st.stage = 0; st.start = null; st.base = null; st.dyPreview = null;
                hideMenu();
                scheduleRender(st);
                },

                toggleCrosshair: function (anyId) {
                var st = STORE.get(resolveDomId(anyId));
                if (!st) return;
                st.crosshairOn = !st.crosshairOn;
                applyCrosshair(st);
                log("crosshair:", st.crosshairOn);
                },
                
                _exportState: function(anyId) {
                var st = STORE.get(resolveDomId(anyId));
                if (!st) return null;
                return deepClone({
                    annos: st.annos || [],
                    crosshairOn: !!st.crosshairOn,
                });
                },

                _importState: function(anyId, state) {
                var domId = resolveDomId(anyId);
                var st = STORE.get(domId);
                if (!st) { attach(domId); st = STORE.get(domId); }
                if (!st || !state) return;

                st.annos = Array.isArray(state.annos) ? deepClone(state.annos) : [];
                st.selectedId = null;

                if (typeof state.crosshairOn === "boolean") {
                    st.crosshairOn = state.crosshairOn;
                    applyCrosshair(st);
                }

                hideMenu();
                scheduleRender(st);
                },
            };
            
            window.NG_ECHART_VOLFMT = {
                attach: function (anyId) {
                    var domId = resolveDomId(anyId);
                    var tries = 0;
                    var timer = setInterval(function () {
                    tries += 1;

                    var chart = getChartInstance(domId);
                    if (!chart) {
                        if (tries > 40) clearInterval(timer);
                        return;
                    }
                    clearInterval(timer);

                    function trim1(x) { return String(x).replace(/\.0$/, ''); }

                    function fmtVol(v) {
                        v = Number(v);
                        if (!isFinite(v)) return '';
                        var av = Math.abs(v);

                        if (av < 1e6) return String(Math.round(v));

                        if (av < 1e9) {
                        var m = Math.round((v / 1e6) * 10) / 10;
                        return trim1(m).replace('.', ',') + 'M'; // 1,5M
                        }

                        var b = Math.round((v / 1e9) * 10) / 10;
                        return trim1(b).replace('.', ',') + 'B';
                    }

                    function apply() {
                        var opt = chart.getOption && chart.getOption();
                        if (!opt || !opt.yAxis || opt.yAxis.length < 2) return; // no volume axis

                        chart.setOption({
                        yAxis: [
                            {}, // keep candles axis untouched
                            {
                            minInterval: 1,
                            axisLabel: {
                                hideOverlap: true,
                                formatter: fmtVol,
                            },
                            },
                        ],
                        }, { lazyUpdate: true });
                    }

                    apply();
                    chart.on('dataZoom', apply);
                    chart.on('restore', apply);
                    chart.on('finished', apply);
                    window.addEventListener('resize', apply);
                    }, 150);
                },
            };
            
            window.NG_ECHART_UI = window.NG_ECHART_UI || {
            toggleFullscreen: function(anyId) {
                var domId = resolveDomId(anyId);
                var el = document.getElementById(domId);
                if (!el) return;

                function resizeLater() {
                var ch = getChartInstance(domId);
                if (ch) setTimeout(function(){ ch.resize(); }, 50);
                }

                if (!document.fullscreenElement) {
                if (el.requestFullscreen) el.requestFullscreen().then(resizeLater).catch(function(){});
                } else {
                if (document.exitFullscreen) document.exitFullscreen().then(resizeLater).catch(function(){});
                }

                document.addEventListener("fullscreenchange", resizeLater, { once: true });
            }
            };

            // ---------------------------------------------------------------------
            // Interval aggregation: D / W / M (client-side, keeps same chart instance)
            // ---------------------------------------------------------------------
            (function () {
            var AGG = new Map(); 

            function parseYMD(s) {
                var y = +s.slice(0, 4), m = +s.slice(5, 7) - 1, d = +s.slice(8, 10);
                return new Date(y, m, d);
            }

            function weekKey(dt) {
                var tmp = new Date(dt.getTime());
                tmp.setHours(0,0,0,0);
                tmp.setDate(tmp.getDate() + 3 - ((tmp.getDay() + 6) % 7));
                var week1 = new Date(tmp.getFullYear(), 0, 4);
                var weekNo = 1 + Math.round(((tmp.getTime() - week1.getTime()) / 86400000 - 3 + ((week1.getDay() + 6) % 7)) / 7);
                return tmp.getFullYear() + "-W" + String(weekNo).padStart(2, "0");
            }

            function monthKey(dt) {
                return dt.getFullYear() + "-" + String(dt.getMonth() + 1).padStart(2, "0");
            }

            function attach(anyId) {
                var domId = resolveDomId(anyId);
                var chart = getChartInstance(domId);
                if (!chart) return;

                var opt = chart.getOption();
                if (!opt || !opt.series || !opt.series.length) return;

                var xAxis = opt.xAxis;
                var xs = Array.isArray(xAxis) ? (xAxis[0] && xAxis[0].data) : xAxis.data;
                var candles = opt.series[0] && opt.series[0].data;
                if (!xs || !candles) return;

                var hasV = (opt.series.length >= 2 && opt.series[1] && opt.series[1].type === "bar");
                var vols = hasV ? opt.series[1].data : null;

                AGG.set(domId, {
                interval: "D",
                rawX: xs.slice(),
                rawC: candles.slice(),
                rawV: vols ? vols.slice() : null,
                hasV: !!hasV,
                });
            }

            function applySeries(chart, xs, candles, vols, hasV) {
                var opt = chart.getOption();
                var xAxis = opt.xAxis;

                var newXAxis;
                if (Array.isArray(xAxis)) {
                newXAxis = xAxis.map(function(ax, idx){
                    var o = Object.assign({}, ax);
                    o.data = xs;
                    return o;
                });
                } else {
                newXAxis = Object.assign({}, xAxis);
                newXAxis.data = xs;
                }

                var series = (opt.series || []).slice();
                if (series[0]) series[0] = Object.assign({}, series[0], { data: candles });
                if (hasV && series[1]) series[1] = Object.assign({}, series[1], { data: vols });

                chart.setOption(
                { xAxis: newXAxis, series: series },
                { lazyUpdate: true, replaceMerge: ["xAxis", "series"] }
                );
            }

            function aggregate(domId, interval) {
                var st = AGG.get(domId);
                var chart = getChartInstance(domId);
                if (!st || !chart) return;

                if (!interval || interval === "D") {
                st.interval = "D";
                applySeries(chart, st.rawX, st.rawC, st.rawV, st.hasV);
                window.NG_ECHART_IND?.refresh(domId);
                return;
                }

                var keyFn = (interval === "W") ? weekKey : monthKey;

                var outX = [];
                var outC = [];
                var outV = st.hasV ? [] : null;

                var curKey = null;
                var gOpen = null, gClose = null, gHigh = null, gLow = null;
                var gVol = 0;
                var gLastDate = null;

                for (var i = 0; i < st.rawX.length; i++) {
                var ds = st.rawX[i];
                var dt = parseYMD(ds);
                var k = keyFn(dt);

                var c = st.rawC[i]; // [open, close, low, high]
                if (!Array.isArray(c) || c.length < 4) continue;

                var o = +c[0], cl = +c[1], lo = +c[2], hi = +c[3];
                var v = st.hasV ? +(st.rawV[i] || 0) : 0;

                if (curKey === null) {
                    curKey = k;
                    gOpen = o; gClose = cl; gHigh = hi; gLow = lo;
                    gVol = v;
                    gLastDate = ds;
                } else if (k !== curKey) {
                    outX.push(gLastDate);
                    outC.push([gOpen, gClose, gLow, gHigh]);
                    if (st.hasV) outV.push(gVol);

                    curKey = k;
                    gOpen = o; gClose = cl; gHigh = hi; gLow = lo;
                    gVol = v;
                    gLastDate = ds;
                } else {
                    gClose = cl;
                    gHigh = Math.max(gHigh, hi);
                    gLow = Math.min(gLow, lo);
                    gVol += v;
                    gLastDate = ds;
                }
                }

                if (curKey !== null) {
                outX.push(gLastDate);
                outC.push([gOpen, gClose, gLow, gHigh]);
                if (st.hasV) outV.push(gVol);
                }

                st.interval = interval;
                applySeries(chart, outX, outC, outV, st.hasV);
                window.NG_ECHART_IND?.refresh(domId);
            }

            window.NG_ECHART_AGG = window.NG_ECHART_AGG || {
                attach: function(anyId) { attach(anyId); },
                
                setInterval: function(anyId, interval) {
                var domId = resolveDomId(anyId);
                if (!AGG.has(domId)) attach(domId);
                aggregate(domId, String(interval || "D"));
                },
                
                _exportState: function(anyId) {
                    var domId = resolveDomId(anyId);
                    var st = AGG.get(domId);
                    if (!st) return null;
                    return { interval: st.interval || "D" };
                },

                _importState: function(anyId, state) {
                    var domId = resolveDomId(anyId);
                    if (!AGG.has(domId)) attach(domId);
                    if (!state) return;
                    aggregate(domId, String(state.interval || "D"));
                },
            };
            })();

            // ---------------------------------------------------------------------
            // Indicators: SMA + Bollinger Bands + right-click menu (top-left anchor)
            // ---------------------------------------------------------------------
            (function () {
            var IND = new Map(); // domId -> state
            var MENU = null;

            function ensureMenu() {
                if (MENU) return;
                MENU = document.createElement("div");
                MENU.style.cssText =
                "position:fixed;display:none;z-index:99999999;" +
                "background:#fff;border:1px solid rgba(2,6,23,.12);" +
                "border-radius:10px;box-shadow:0 12px 30px rgba(15,23,42,.18);" +
                "padding:8px;min-width:220px;font-family:system-ui,Segoe UI,Arial;font-size:13px;user-select:none;";
                document.body.appendChild(MENU);

                window.addEventListener("mousedown", function (e) {
                if (MENU.style.display === "block" && !MENU.contains(e.target)) hideMenu();
                }, true);

                window.addEventListener("keydown", function (e) {
                if (e.key === "Escape") hideMenu();
                }, true);
            }

            function hideMenu() {
                if (!MENU) return;
                MENU.style.display = "none";
                MENU._target = null;
            }

            function item(label, fn) {
                var b = document.createElement("button");
                b.textContent = label;
                b.style.cssText =
                "display:block;width:100%;text-align:left;padding:8px 10px;" +
                "border:0;background:transparent;cursor:pointer;border-radius:8px;";
                b.addEventListener("mouseenter", function () { b.style.background = "rgba(2,6,23,.06)"; });
                b.addEventListener("mouseleave", function () { b.style.background = "transparent"; });
                b.addEventListener("click", function (e) { e.preventDefault(); e.stopPropagation(); fn(); });
                return b;
            }

            function sep() {
                var d = document.createElement("div");
                d.style.cssText = "height:1px;background:rgba(2,6,23,.10);margin:6px 0;";
                return d;
            }

            function defaults() {
                return {
                enabled: [],

                sma: {
                    "sma-1": { period: 20, color: "#2563eb", width: 1.5 },
                    "sma-2": { period: 50, color: "#16a34a", width: 1.5 },
                    "sma-3": { period: 200, color: "#dc2626", width: 1.5 },
                },

                bb: { period: 20, std: 2, color: "#f59e0b", width: 1.2 },
                };
            }

            function getBaseData(chart) {
                var opt = chart.getOption();
                if (!opt || !opt.series || !opt.series[0]) return null;

                var xAxis = opt.xAxis;
                var xs = Array.isArray(xAxis) ? (xAxis[0] && xAxis[0].data) : xAxis.data;
                if (!xs) return null;

                var candles = opt.series[0].data;
                if (!candles) return null;

                var closes = candles.map(function (c) {
                if (!Array.isArray(c) || c.length < 2) return null;
                var v = +c[1];
                return isFinite(v) ? v : null;
                });

                return { opt: opt, xs: xs, closes: closes };
            }

            function sma(values, period) {
                var n = values.length;
                var out = new Array(n).fill(null);
                var p = Math.max(1, parseInt(period || 20, 10));
                var sum = 0;

                for (var i = 0; i < n; i++) {
                var v = values[i];
                sum += (v == null ? 0 : v);

                if (i >= p) {
                    var old = values[i - p];
                    sum -= (old == null ? 0 : old);
                }
                if (i >= p - 1) out[i] = sum / p;
                }
                return out;
            }

            function bollinger(values, period, stdMul) {
                var n = values.length;
                var mid = new Array(n).fill(null);
                var up = new Array(n).fill(null);
                var lo = new Array(n).fill(null);

                var p = Math.max(2, parseInt(period || 20, 10));
                var k = Number(stdMul || 2);
                if (!isFinite(k) || k <= 0) k = 2;

                var sum = 0, sumsq = 0;

                for (var i = 0; i < n; i++) {
                var v = values[i];
                var vv = (v == null) ? 0 : v;
                sum += vv;
                sumsq += vv * vv;

                if (i >= p) {
                    var old = values[i - p];
                    var oo = (old == null) ? 0 : old;
                    sum -= oo;
                    sumsq -= oo * oo;
                }

                if (i >= p - 1) {
                    var mean = sum / p;
                    var varr = (sumsq / p) - (mean * mean);
                    var std = Math.sqrt(Math.max(0, varr));
                    mid[i] = mean;
                    up[i] = mean + k * std;
                    lo[i] = mean - k * std;
                }
                }

                return { mid: mid, up: up, lo: lo };
            }

            function baseSeriesCount(opt) {
                var series = opt.series || [];
                if (series[1] && series[1].type === "bar") return 2; // candles + volume
                return 1; // only candles
            }

            function apply(st) {
                if (st._lock) return;
                st._lock = true;

                try {
                var chart = st.chart;
                var base = getBaseData(chart);
                if (!base) return;

                var opt = base.opt;
                var series = (opt.series || []).slice();
                var baseCount = baseSeriesCount(opt);
                var baseSeries = series.slice(0, baseCount);

                var enabled = st.cfg.enabled || [];
                var indSeries = [];

                ["sma-1", "sma-2", "sma-3"].forEach(function (slot) {
                    if (!enabled.includes(slot)) return;
                    var cfg = (st.cfg.sma && st.cfg.sma[slot]) || { period: 20, color: "#2563eb", width: 1.5 };
                    var p = Math.max(1, parseInt(cfg.period || 20, 10));
                    var data = sma(base.closes, p);

                    indSeries.push({
                    id: "ng_ind:" + slot,
                    name: slot.toUpperCase() + " SMA(" + p + ")",
                    type: "line",
                    data: data,
                    showSymbol: false,
                    yAxisIndex: 0,
                    lineStyle: { width: cfg.width || 1.5, color: cfg.color || "#2563eb" },
                    emphasis: { disabled: true },
                    tooltip: { show: false },
                    });
                });

                if (enabled.includes("bb")) {
                    var bp = Math.max(2, parseInt(st.cfg.bb.period || 20, 10));
                    var bs = Number(st.cfg.bb.std || 2);
                    if (!isFinite(bs) || bs <= 0) bs = 2;

                    var bb = bollinger(base.closes, bp, bs);
                    var c = st.cfg.bb.color || "#f59e0b";
                    var w = st.cfg.bb.width || 1.2;

                    indSeries.push({
                    id: "ng_ind:bb:mid",
                    name: "BB Mid(" + bp + "," + bs + ")",
                    type: "line",
                    data: bb.mid,
                    showSymbol: false,
                    yAxisIndex: 0,
                    lineStyle: { width: w, color: c },
                    tooltip: { show: false },
                    });
                    indSeries.push({
                    id: "ng_ind:bb:up",
                    name: "BB Upper",
                    type: "line",
                    data: bb.up,
                    showSymbol: false,
                    yAxisIndex: 0,
                    lineStyle: { width: w, color: c, type: "dashed" },
                    tooltip: { show: false },
                    });
                    indSeries.push({
                    id: "ng_ind:bb:lo",
                    name: "BB Lower",
                    type: "line",
                    data: bb.lo,
                    showSymbol: false,
                    yAxisIndex: 0,
                    lineStyle: { width: w, color: c, type: "dashed" },
                    tooltip: { show: false },
                    });
                }

                chart.setOption(
                    { series: baseSeries.concat(indSeries) },
                    { lazyUpdate: true, replaceMerge: ["series"], silent: true } // ✅ no flicker loop
                );
                } finally {
                st._lock = false;
                }
            }

            function anchorMenuTopLeft(domId) {
                var root = document.getElementById(domId);
                if (!root) return { x: 10, y: 10 };
                var r = root.getBoundingClientRect();
                return { x: r.left + 12, y: r.top + 12 };
            }

            function showMenu(domId, key) {
                ensureMenu();
                hideMenu();

                var st = IND.get(domId);
                if (!st) return;

                MENU.innerHTML = "";

                MENU.appendChild(item("Remove indicator", function () {
                st.cfg.enabled = (st.cfg.enabled || []).filter(function (x) { return x !== key; });
                apply(st);
                hideMenu();
                }));
                MENU.appendChild(sep());

                function colorItems(setColor) {
                [["Black","#111827"],["Blue","#2563eb"],["Green","#16a34a"],["Red","#dc2626"],["Purple","#7c3aed"],["Orange","#f59e0b"]]
                    .forEach(function (cc) {
                    MENU.appendChild(item("Color: " + cc[0], function () { setColor(cc[1]); apply(st); hideMenu(); }));
                    });
                }

                if (key.startsWith("sma-")) {
                var cfg = st.cfg.sma[key];

                MENU.appendChild(item("Set period…", function () {
                    var v = prompt(key.toUpperCase() + " period", String(cfg.period || 20));
                    if (v == null) return;
                    var p = Math.max(1, parseInt(v, 10));
                    if (!isFinite(p)) return;
                    cfg.period = p;
                    apply(st); hideMenu();
                }));
                MENU.appendChild(sep());
                colorItems(function (c) { cfg.color = c; });
                MENU.appendChild(sep());
                [1, 1.5, 2, 3].forEach(function (w) {
                    MENU.appendChild(item("Width: " + w, function () { cfg.width = w; apply(st); hideMenu(); }));
                });
                }

                if (key === "bb") {
                MENU.appendChild(item("Set period…", function () {
                    var v = prompt("Bollinger period", String(st.cfg.bb.period || 20));
                    if (v == null) return;
                    var p = Math.max(2, parseInt(v, 10));
                    if (!isFinite(p)) return;
                    st.cfg.bb.period = p;
                    apply(st); hideMenu();
                }));
                MENU.appendChild(item("Set std dev…", function () {
                    var v = prompt("Bollinger std dev", String(st.cfg.bb.std || 2));
                    if (v == null) return;
                    var s = Number(v);
                    if (!isFinite(s) || s <= 0) return;
                    st.cfg.bb.std = s;
                    apply(st); hideMenu();
                }));
                MENU.appendChild(sep());
                colorItems(function (c) { st.cfg.bb.color = c; });
                MENU.appendChild(sep());
                [1, 1.2, 1.5, 2, 3].forEach(function (w) {
                    MENU.appendChild(item("Width: " + w, function () { st.cfg.bb.width = w; apply(st); hideMenu(); }));
                });
                }

                var pos = anchorMenuTopLeft(domId);
                MENU.style.left = pos.x + "px";
                MENU.style.top = pos.y + "px";
                MENU.style.display = "block";
            }

            function pickIndicatorKey(domId, clientX, clientY) {
                var st = IND.get(domId);
                if (!st) return null;

                var chart = st.chart;
                var rect = gridRect(chart);
                if (!rect) return null;

                var root = document.getElementById(domId);
                if (!root) return null;
                var r = root.getBoundingClientRect();
                var px = [clientX - r.left, clientY - r.top];

                if (!inRect(px, rect)) return null;

                var base = getBaseData(chart);
                if (!base) return null;

                var d = toData(chart, px);
                if (!d) return null;

                var xVal = d[0];
                var idx = -1;

                if (typeof xVal === "number") idx = Math.max(0, Math.min(base.xs.length - 1, Math.round(xVal)));
                else if (typeof xVal === "string") idx = base.xs.indexOf(xVal);

                if (idx < 0) return null;

                var bestKey = null;
                var bestDist = 1e9;
                var TH = 10;

                function testY(y) {
                if (y == null) return null;
                var p = toPx(chart, [base.xs[idx], y]);
                if (!p) return null;
                return Math.abs(px[1] - p[1]);
                }

                ["sma-1", "sma-2", "sma-3"].forEach(function (slot) {
                if (!(st.cfg.enabled || []).includes(slot)) return;
                var cfg = st.cfg.sma[slot];
                var arr = sma(base.closes, Math.max(1, parseInt(cfg.period || 20, 10)));
                var dist = testY(arr[idx]);
                if (dist != null && dist < TH && dist < bestDist) {
                    bestDist = dist;
                    bestKey = slot;
                }
                });

                if ((st.cfg.enabled || []).includes("bb")) {
                var bp = Math.max(2, parseInt(st.cfg.bb.period || 20, 10));
                var bs = Number(st.cfg.bb.std || 2);
                var bb = bollinger(base.closes, bp, (isFinite(bs) && bs > 0) ? bs : 2);

                [bb.mid[idx], bb.up[idx], bb.lo[idx]].forEach(function (yv) {
                    var dist = testY(yv);
                    if (dist != null && dist < TH && dist < bestDist) {
                    bestDist = dist;
                    bestKey = "bb";
                    }
                });
                }

                return bestKey;
            }

            function attach(anyId) {
                var domId = resolveDomId(anyId);
                var chart = getChartInstance(domId);
                if (!chart) return;

                if (!IND.has(domId)) {
                IND.set(domId, { domId: domId, chart: chart, cfg: defaults(), _lock: false });

                var root = document.getElementById(domId);
                if (root) {
                    root.addEventListener("contextmenu", function (e) {
                    var key = pickIndicatorKey(domId, e.clientX, e.clientY);
                    if (!key) return; // let other contextmenus work
                    e.preventDefault();
                    e.stopPropagation();
                    showMenu(domId, key);
                    }, { passive: false, capture: true });
                }
                }

                apply(IND.get(domId));
            }

            window.NG_ECHART_IND = window.NG_ECHART_IND || {
                attach: function (anyId) { attach(anyId); },
                setEnabled: function (anyId, keys) {
                var domId = resolveDomId(anyId);
                if (!IND.has(domId)) attach(domId);
                var st = IND.get(domId);
                if (!st) return;

                st.cfg.enabled = Array.isArray(keys) ? keys.slice() : [];
                apply(st);
                hideMenu();
                },
                refresh: function (anyId) {
                var domId = resolveDomId(anyId);
                var st = IND.get(domId);
                if (st) apply(st);
                },
                
                _exportState: function(anyId) {
                    var domId = resolveDomId(anyId);
                    var st = IND.get(domId);
                    if (!st) return null;
                    return deepClone({ cfg: st.cfg });
                },

                _importState: function(anyId, state) {
                    var domId = resolveDomId(anyId);
                    if (!IND.has(domId)) attach(domId);
                    var st = IND.get(domId);
                    if (!st || !state) return;

                    // merge with defaults (so missing keys won't break)
                    var d = defaults();
                    var incoming = state.cfg || state;

                    st.cfg = Object.assign({}, d, incoming);
                    st.cfg.sma = Object.assign({}, d.sma, (incoming.sma || {}));
                    st.cfg.bb  = Object.assign({}, d.bb,  (incoming.bb  || {}));

                    apply(st);
                    hideMenu();
                },
            };
            })();

            // ---------------------------------------------------------------------
            // Persist: Save/Load full analysis state (draw + indicators + interval + zoom)
            // Uses localStorage (preferred), cookie fallback
            // ---------------------------------------------------------------------
            (function () {

            function storageKey(userKey) {
                return "ng_chart_state:" + String(userKey || "default");
            }

            function setCookie(name, value, days) {
                var exp = "";
                if (days) {
                    var d = new Date();
                    d.setTime(d.getTime() + (days * 86400000));
                    exp = "; expires=" + d.toUTCString();
                }
                document.cookie = name + "=" + value + exp + "; path=/; SameSite=Lax";
            }

            function getCookie(name) {
                var prefix = name + "=";
                var parts = document.cookie.split(";");
                for (var i = 0; i < parts.length; i++) {
                    var c = parts[i].trim();
                    if (c.indexOf(prefix) === 0) return c.substring(prefix.length);
                }
                return null;
            }

            function setStorage(key, value) {
                try {
                    localStorage.setItem(key, value);
                    return true;
                } catch (e) {
                    // fallback to cookie (may overflow!)
                    try {
                        setCookie(key, encodeURIComponent(value), 365);
                        return true;
                    } catch (e2) {
                        return false;
                    }
                }
            }

            function getStorage(key) {
                try {
                    var v = localStorage.getItem(key);
                    if (v != null) return v;
                } catch (e) { /* ignore */ }

                var c = getCookie(key);
                if (c != null) {
                    try { return decodeURIComponent(c); } catch (e2) { return c; }
                }
                return null;
            }

            function exportZoom(chart) {
                try {
                    var opt = chart.getOption();
                    var dz = opt.dataZoom;
                    if (!Array.isArray(dz)) return null;

                    return dz.map(function(z){
                        var o = {};
                        if (z.type) o.type = z.type;
                        if (z.xAxisIndex != null) o.xAxisIndex = z.xAxisIndex;
                        if (z.start != null) o.start = z.start;
                        if (z.end != null) o.end = z.end;
                        if (z.startValue != null) o.startValue = z.startValue;
                        if (z.endValue != null) o.endValue = z.endValue;
                        return o;
                    });
                } catch (e) {
                    return null;
                }
            }

            function importZoom(chart, dzState) {
                if (!dzState || !Array.isArray(dzState)) return;
                try {
                    chart.setOption(
                        { dataZoom: dzState },
                        { lazyUpdate: true, replaceMerge: ["dataZoom"] }
                    );
                } catch (e) { /* ignore */ }
            }

            function save(anyId, userKey) {
                var domId = resolveDomId(anyId);
                var chart = getChartInstance(domId);
                if (!chart) return;

                var payload = {
                    v: 1,
                    ts: Date.now(),
                    draw: window.NG_ECHART_DRAW?._exportState?.(domId) || null,
                    ind:  window.NG_ECHART_IND?._exportState?.(domId)  || null,
                    agg:  window.NG_ECHART_AGG?._exportState?.(domId)  || null,
                    zoom: exportZoom(chart),
                };

                var ok = setStorage(storageKey(userKey), JSON.stringify(payload));
                console.log("[NG_ECHART_PERSIST] save", userKey, "ok=", ok);
            }

            function load(anyId, userKey) {
                var domId = resolveDomId(anyId);
                var chart = getChartInstance(domId);
                if (!chart) return;

                var raw = getStorage(storageKey(userKey));
                if (!raw) return;

                var payload = null;
                try { payload = JSON.parse(raw); } catch (e) { return; }
                if (!payload) return;

                if (payload.agg && window.NG_ECHART_AGG?._importState) {
                    window.NG_ECHART_AGG._importState(domId, payload.agg);
                }

                if (payload.ind && window.NG_ECHART_IND?._importState) {
                    window.NG_ECHART_IND._importState(domId, payload.ind);
                }
                if (payload.draw && window.NG_ECHART_DRAW?._importState) {
                    window.NG_ECHART_DRAW._importState(domId, payload.draw);
                }

                importZoom(chart, payload.zoom);

                console.log("[NG_ECHART_PERSIST] load", userKey, "ts=", payload.ts);
            }

            window.NG_ECHART_PERSIST = window.NG_ECHART_PERSIST || {
                save: save,
                load: load,
                clear: function(userKey) {
                    try { localStorage.removeItem(storageKey(userKey)); } catch(e) {}
                    setCookie(storageKey(userKey), "", -1);
                },
            };

            })();

            console.log("[NG_ECHART_DRAW] loaded OK =", !!window.NG_ECHART_DRAW);
            })();
            """  
