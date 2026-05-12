from __future__ import annotations

from robot.api.deco import keyword
from robot.libraries.BuiltIn import BuiltIn

ROBOT_LIBRARY_SCOPE = "SUITE"


def _built_in() -> BuiltIn:
    return BuiltIn()


def _variable(name: str, default: str) -> str:
    value = _built_in().get_variable_value(name, default)
    return str(value)


def _run(keyword_name: str, *args: object) -> object:
    return _built_in().run_keyword(keyword_name, *args)


@keyword("Open Next Ui Browser")
def open_next_ui_browser() -> None:
    headless = _variable("${HEADLESS}", "True")
    base_url = _variable("${BASE_URL}", "http://traefik")
    viewport = {"width": 1440, "height": 900}

    _run("New Browser", "chromium", f"headless={headless}")
    _run("New Context", f"viewport={viewport}", "tracing=True")
    _run("New Page", base_url)


@keyword("Close Browser And Keep Failure Artifacts")
def close_browser_and_keep_failure_artifacts() -> None:
    _run("Close Browser")

    suite_status = _variable("${SUITE STATUS}", "PASS")
    if suite_status == "FAIL":
        output_dir = _variable("${OUTPUT DIR}", "")
        _run(
            "AllureHelper.Attach Latest Playwright Trace",
            f"{output_dir}/browser/traces",
        )


@keyword("Capture Test Screenshot")
def capture_test_screenshot() -> None:
    try:
        _run("Take Screenshot", "filename=EMBED", "fullPage=True")
    except Exception as exc:
        _built_in().log(f"Screenshot not available: {exc}", "WARN")


@keyword("Go To Next Ui Path")
def go_to_next_ui_path(path: str) -> None:
    base_url = _variable("${BASE_URL}", "http://traefik")
    _run("Go To", f"{base_url}{path}")
    _run("Wait For Load State", "domcontentloaded")


@keyword("Page Should Have Heading")
def page_should_have_heading(heading: str) -> None:
    _run("Get Text", f'role=heading[name="{heading}"]', "==", heading)


@keyword("Page Should Have Text")
def page_should_have_text(text: str) -> None:
    _run("Get Text", f"text={text}", "contains", text)
