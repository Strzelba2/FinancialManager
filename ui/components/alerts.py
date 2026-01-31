from nicegui import ui, app
from typing import List, Any, Dict
import logging

from utils.money import fmt_level, fmt_money, dec

POLL_SECONDS = 30 * 60
logger = logging.getLogger(__name__)


def alerts_panel_card(
    alerts: list[dict],
    top: int = 5,
    view_ccy: str = "PLN",
) -> None:
    """
    Render a compact table card showing the most recent price alerts.

    The function sorts alerts by `last_triggered` (fallback: `created_at`) and shows
    at most `top` items. It prepares display-friendly formatted values using
    `fmt_level` and `fmt_money`.

    Args:
        alerts: Raw alert items (dict-like objects) from the API/client layer.
        top: Maximum number of alerts to display (default: 5).
        view_ccy: Currency code used to format the "Now" column (default: "PLN").

    Returns:
        None. This function renders NiceGUI UI elements.
    """

    alerts_sorted = sorted(
        alerts or [],
        key=lambda a: (a.get("last_triggered") or a.get("created_at") or ""),
        reverse=True,
    )[:top]

    prepared = []
    for i, a in enumerate(alerts_sorted, start=1):
        sym = str(a.get("symbol", "") or "")

        below = a.get("below_price", None)
        above = a.get("above_price", None)
        now = a.get("current_price", None)

        prepared.append({
            "rank": i,
            "symbol": sym,
            "below": below,
            "above": above,
            "now": now,
            "below_fmt": fmt_level(below),
            "above_fmt": fmt_level(above),
            "now_fmt": fmt_money(now, view_ccy),
        })
        
    logger.debug(
        f"alerts_panel_card: prepared_rows={len(prepared)} (requested top={top})"
    )

    if not prepared:
        logger.debug("alerts_panel_card: no alerts to render -> showing empty state")
        with ui.row().classes("items-center justify-center w-full text-grey-7").style("padding:10px 0;"):
            with ui.column().classes("items-center justify-center q-gutter-xs"):
                ui.icon("sym_o_notifications_off").classes("text-h5 text-grey-5")
                ui.label("Brak alertów").classes("text-caption text-grey-6")
        return

    cols = [
        {"name": "rank", "label": "#", "field": "rank", "align": "left",
            "style": "width:40px", "headerStyle": "font-weight:700"},
        {"name": "symbol", "label": "Symbol", "field": "symbol", "align": "left",
            "style": "width:90px", "headerStyle": "font-weight:700"},
        {"name": "below_fmt", "label": "Below", "field": "below_fmt", "align": "right",
            "style": "width:90px", "headerStyle": "font-weight:700"},
        {"name": "above_fmt", "label": "Above", "field": "above_fmt", "align": "right",
            "style": "width:90px", "headerStyle": "font-weight:700"},
        {"name": "now_fmt", "label": f"Now ({view_ccy})", "field": "now_fmt", "align": "right",
            "style": "width:140px", "headerStyle": "font-weight:700"},
    ]

    (
        ui.table(columns=cols, rows=prepared, row_key="symbol")
        .props("flat dense separator=horizontal hide-bottom hide-pagination rows-per-page-options=[5]")
        .classes("top4-table q-mt-none")
        .style("margin-top:-6px")
    )
        
        
def alert_nav_right_section(self) -> None:
    """
    Render the right-side navigation alert bell with a monitoring toggle.

    Behavior:
      - Periodically polls alerts from wallet-service.
      - Enriches alerts with current prices from stock-service.
      - Shows a badge with the number of active (non-muted, enabled) alerts.
      - Allows deleting alerts directly from the dropdown menu.
      - Monitoring state is stored in user storage.

    Args:
        self: Context object providing `get_user_id()`, `wallet_client`, and `stock_client`.

    Returns:
        None. This function renders NiceGUI UI elements and registers timers/callbacks.
    """

    store_key = "alerts_monitoring_enabled"
    monitoring_enabled: bool = bool(app.storage.user.get(store_key, True))

    poll_timer = None
    poll_in_flight = False

    alerts_cache: List[Dict[str, Any]] = []

    bell_area = ui.element("div").classes("q-ml-sm")

    def _active_alerts() -> List[Dict[str, Any]]:
        """Filter alerts_cache to those that should count as active/fired and visible in the bell."""
        out = []
        for a in alerts_cache:
            status = (a.get("status") or "active")
            if status not in ("active", "fired"):
                continue
            if bool(a.get("muted")):
                continue
            if not bool(a.get("enabled", True)):
                continue
            out.append(a)
        return out

    async def _load_alerts_and_prices() -> None:
        """
        Pull alerts from wallet-service and enrich with current price from stock-service.
        If your backend already computes status, we keep it. Otherwise we can compute a simple fired-now status.
        """
        nonlocal alerts_cache

        try:
            user_id = self.get_user_id()
        except Exception:
            logger.exception("alert_nav_right_section: cannot resolve user_id")
            alerts_cache = []
            return
        try:
            raw_alerts = await self.wallet_client.list_alerts(user_id=user_id)
            alerts: List[Dict[str, Any]] = []
            for a in (raw_alerts or []):
                if isinstance(a, dict):
                    alerts.append(a)
                else:
                    alerts.append(a.model_dump() if hasattr(a, "model_dump") else dict(a))
        except Exception:
            logger.exception("alert_nav_right_section: list_alerts failed")
            alerts_cache = []
            return

        def _key(a: Dict[str, Any]) -> str:
            return str(a.get("last_triggered") or a.get("updated_at") or a.get("created_at") or "")

        alerts = sorted(alerts, key=_key, reverse=True)

        symbols = [str(a.get("symbol") or "").strip().upper() for a in alerts]
        symbols = [s for s in symbols if s]
        symbols = list(dict.fromkeys(symbols))

        quotes_map: Dict[str, Any] = {}
        if symbols:
            try:
                quotes_map = await self.stock_client.get_latest_quotes_for_symbols(symbols)
            except Exception:
                logger.exception("alert_nav_right_section: get_latest_quotes_for_symbols failed")
                quotes_map = {}

        enriched: List[Dict[str, Any]] = []
        for a in alerts:
            sym = str(a.get("symbol") or "").strip().upper()
            q = quotes_map.get(sym) if sym else None

            def q_get(obj: Any, k: str, default=None):
                if obj is None:
                    return default
                if isinstance(obj, dict):
                    return obj.get(k, default)
                return getattr(obj, k, default)

            price = q_get(q, "price", None)
            ccy = q_get(q, "currency", None)

            a = dict(a) 
            a["current_price"] = price
            a["current_currency"] = ccy

            below = dec(a.get("below_price"))
            above = dec(a.get("above_price"))
            cur = dec(price)

            if a.get("status") is None:
                fired_now = False
                if cur is not None:
                    if below is not None and cur <= below:
                        fired_now = True
                    if above is not None and cur >= above:
                        fired_now = True
                a["status"] = "fired" if fired_now else "active"

            enriched.append(a)

        alerts_cache = enriched

    def _badge_count() -> int:
        """Number displayed on the bell badge."""
        return len(_active_alerts()) if monitoring_enabled else 0

    def _fmt_condition(a: Dict[str, Any]) -> str:
        """Format alert condition (below/above) for UI."""
        parts = []
        if a.get("below_price") is not None:
            parts.append(f"< {a.get('below_price')}")
        if a.get("above_price") is not None:
            parts.append(f"> {a.get('above_price')}")
        if not parts:
            parts.append("—")
        return " | ".join(parts)

    def _fmt_price(a: Dict[str, Any]) -> str:
        """Format current price and currency for UI."""
        p = a.get("current_price")
        c = a.get("current_currency")
        if p is None:
            return "—"
        return f"{p} {c or ''}".strip()

    async def _delete_alert(a: Dict[str, Any]) -> None:
        """Delete a single alert and refresh UI/cache."""
        try:
            user_id = self.get_user_id()
        except Exception:
            ui.notify("Missing user_id", type="negative")
            return

        sym = a.get("symbol")

        ok = False
        try:
            ok = await self.wallet_client.delete_alert(user_id=user_id, symbol=str(sym))
        except Exception:
            logger.exception("alert_nav_right_section: delete_alert failed")
            ok = False

        if ok:
            ui.notify("Alert deleted", type="positive")
        else:
            ui.notify("Failed to delete alert", type="negative")

        if monitoring_enabled:
            await _load_alerts_and_prices()
        _render_bell()

    def _render_bell() -> None:
        """Render bell button, badge, and dropdown menu based on cached/enriched alerts."""
        bell_area.clear()
        with bell_area:
            with ui.button(icon="notifications").props("flat color=white"):

                cnt = _badge_count()
                if cnt:
                    ui.badge(cnt, color="red").props("floating")

                with ui.menu().classes("settings-menu") as m:
                    m.props("offset=[0,22]")
                    with ui.row().classes("items-center justify-between q-px-md q-pt-sm").style("min-width:360px"):
                        title = "Alerts (Monitoring ON)" if monitoring_enabled else "Alerts (Monitoring OFF)"
                        ui.label(title).classes("text-weight-medium")
                        ui.button("Open", icon="open_in_new", on_click=lambda: ui.navigate.to("/wallet/favorites")) \
                            .props("dense flat color=primary no-caps")

                    ui.separator().classes("q-my-sm")

                    if not monitoring_enabled:
                        ui.label("Monitoring is OFF — no checks are performed.").classes("q-px-md q-pb-sm text-grey-7")
                        return

                    active = _active_alerts()
                    logger.info(f"active: {active}")
                    if not active:
                        ui.label("No active alerts.").classes("q-px-md q-pb-sm text-grey-7")
                        return

                    for a in active[:5]:
                        sym = str(a.get("symbol") or "—")
                        cond = _fmt_condition(a)
                        price = _fmt_price(a)
                        status = a.get("status") or "active"
                        
                        async def _on_delete(_: Any = None, a_: Dict[str, Any] = a) -> None:
                            await _delete_alert(a_)

                        with ui.row().classes("items-center q-px-md q-py-xs").style("min-width:360px"):
                            dot = "#ef4444" if status == "fired" else "#22c55e"
                            ui.element("span").classes("badge-dot").style(f"background:{dot}")

                            ui.label(f"{sym} · {cond} · now: {price}").classes("q-ml-sm")
                            ui.space()

                            ui.button(icon="delete").props("dense flat size=sm color=negative") \
                                .on("click", _on_delete)

    async def _poll() -> None:
        """Periodic poll task: refresh cache and rerender bell."""
        nonlocal poll_in_flight
        if not monitoring_enabled:
            return
        if poll_in_flight:
            return
        poll_in_flight = True
        try:
            await _load_alerts_and_prices()
            _render_bell()
        finally:
            poll_in_flight = False

    def _start_polling() -> None:
        """Start the polling timer if not running."""
        nonlocal poll_timer
        if poll_timer is not None:
            return
        poll_timer = ui.timer(POLL_SECONDS, _poll)

    def _stop_polling() -> None:
        """Stop the polling timer if running."""
        nonlocal poll_timer
        if poll_timer is None:
            return
        try:
            poll_timer.cancel()
        except Exception:
            pass
        poll_timer = None

    with ui.row().classes("items-center q-ml-sm"):
        ui.label("Alerts").classes("text-white q-mr-xs")
        toggle = ui.toggle(["OFF", "ON"], value=("ON" if monitoring_enabled else "OFF")).props("dense")

        def _set_monitoring(on: bool) -> None:
            nonlocal monitoring_enabled
            monitoring_enabled = on
            app.storage.user[store_key] = on

            if on:
                _start_polling()
            else:
                _stop_polling()
            _render_bell()

        toggle.on("update:model-value", lambda e: _set_monitoring(e.sender.value == "ON"))

    _render_bell()
    if monitoring_enabled:
        _start_polling()
    else:
        _stop_polling()
