from nicegui import ui, app
from datetime import datetime
import inspect
import asyncio
import logging

logger = logging.getLogger(__name__)


class ManualRefreshQuotes:
    """
    UI helper for manually refreshing quotes.

    Flow:
      1) On refresh click, check Celery status.
      2) If Celery worker is online, just reload quotes immediately.
      3) Otherwise, start a manual ingest job and poll its status in Redis storage.
      4) Update UI label + re-enable the refresh button when done.

    """
    def __init__(self):
        self.ingest_key = "ingest:quotes:status"
        self._ingest_timer = None

    async def _on_refresh_quotes_click(self) -> None:
        """
        Handle the "Refresh quotes" button click.

        - Disables the refresh button to prevent double-start.
        - If Celery workers respond to ping, performs a UI reload immediately.
        - Otherwise starts a manual ingest and begins polling its status.
        """
        logger.info("ManualRefreshQuotes: refresh click")
        try:
            self.refresh_btn.disable()
        except Exception:
            pass
        
        status = await self.stock_client.get_celery_status()

        if status and status.get("online") is True:
            workers = status.get("workers") or []
            ui.notify(f"Celery worker online ({', '.join(workers)}). Reloading quotes…", type="info")
            await self._reload()
            return

        ui.notify("Refreshing quotes… it can take up to 20 minutes.", type="info")
        
        if self._ingest_timer is not None:
            ui.notify("Refresh already running.", type="warning")
            return

        res = await self.stock_client.run_manual_ingest()
        if not res or not res.get("ok"):
            ui.notify("Failed to start refresh.", type="negative")
            return

        self._start_ingest_poll()
        
    def _start_ingest_poll(self) -> None:
        """
        Start polling ingest status from storage.

        Updates `_ingest_label` while running and stops polling when:
          - state == "done"
          - state == "error"
          - unexpected/missing state
        """

        self._ingest_label.set_text("Refreshing… (can take up to 20 minutes)")
        self._ingest_label.visible = True
        self._time_running = 0

        async def _tick():
            """
            Poll one cycle: read ingest state from storage and update UI.

            Uses an in-flight guard to avoid overlapping polls if storage is slow.
            """
            data = await app.storage.stock.hgetall(self.ingest_key)
            state = (data or {}).get("state")

            if state == "done":
                self._ingest_label.set_text("Done ✅")
                reload_fn = getattr(self, "_reload", None) or getattr(self, "render_all", None)
                if callable(reload_fn):
                    result = reload_fn()
                    if inspect.isawaitable(result):
                        await result
                self._stop_ingest_polling()

            elif state == "error":
                self._ingest_label.set_text("Failed ❌")
                ui.notify(f"Update quotes failed: {data.get('detail', '')}")
                self._stop_ingest_polling()
            elif state == "running":
                self._time_running += 2
                self._ingest_label.set_text(f"Running... {self._time_running}s")
            else:
                ui.notify("something goes wrong")
                self._stop_ingest_polling()

        self._ingest_timer = ui.timer(2.0, lambda: asyncio.create_task(_tick())) 
        
    def _stop_ingest_polling(self) -> None:
        """
        Stop polling ingest status and re-enable refresh button.

        Safe to call multiple times.
        """
        t = getattr(self, "_ingest_timer", None)
        if t:
            try:
                t.cancel()
            except Exception:
                logger.debug("ManualRefreshQuotes: timer cancel failed", exc_info=True)
                pass
            self._ingest_timer = None
            
        try:
            self.refresh_btn.enable()
        except Exception:
            pass
        
        logger.info("ManualRefreshQuotes: polling stopped")
        
    async def _restore_ingest_status(self) -> None:
        """
        Restore UI state after page reload.

        Reads ingest status from storage and:
          - resumes polling if state == "running"
          - shows done/failed message otherwise
        """
        logger.debug(f"ManualRefreshQuotes: restore ingest status key={self.ingest_key!r}")
        data = await app.storage.stock.hgetall(self.ingest_key)
        state = (data or {}).get("state")
        
        if state == "running":
            self._ingest_label.set_text("Running...")
            try:
                self.refresh_btn.disable()
            except Exception:
                pass
            self._start_ingest_poll()
        elif state == "done":
            self._ingest_label.set_text("Quotes refresh: Done ✅")
            last_ref = getattr(self, "last_ref_label", None)
            if last_ref:
                now = datetime.now().strftime('%H:%M:%S')
                last_ref.text = f'Last update: {now}'
        elif state == "error":
            detail = (data or {}).get("detail", "")
            self._ingest_label.set_text(f"Quotes refresh: Failed ❌ {detail}")
        else:
            self._ingest_label.set_text("")

