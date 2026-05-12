from __future__ import annotations

from pathlib import Path

import allure
from robot.api.deco import keyword
from robot.libraries.BuiltIn import BuiltIn

ROBOT_LIBRARY_SCOPE = "SUITE"


@keyword("Attach Latest Playwright Trace")
def attach_latest_playwright_trace(
    traces_dir: str,
    name: str = "playwright-trace.zip",
) -> None:
    """Attach the newest Playwright trace zip from a Robot Browser output folder."""
    try:
        path = Path(traces_dir)
        if not path.exists():
            BuiltIn().log(f"Traces directory not found: {traces_dir}", "WARN")
            return

        trace_files = sorted(
            path.glob("*.zip"),
            key=lambda trace_file: trace_file.stat().st_mtime,
            reverse=True,
        )
        if not trace_files:
            BuiltIn().log(f"No trace zip files in {traces_dir}", "WARN")
            return

        allure.attach.file(
            str(trace_files[0]),
            name=name,
            attachment_type="application/zip",
        )
    except Exception as exc:
        BuiltIn().log(f"Could not attach trace: {exc}", "WARN")
