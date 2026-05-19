from __future__ import annotations

from html import escape
from urllib.parse import quote

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
    base_url = _variable("${BASE_URL}", "http://next.localhost")
    host_resolver_rules = _variable("${HOST_RESOLVER_RULES}", "").strip()
    viewport = {"width": 1440, "height": 900}
    browser_args = []

    if host_resolver_rules:
        browser_args.append(f"--host-resolver-rules={host_resolver_rules}")

    new_browser_args = ["chromium", f"headless={headless}"]
    if browser_args:
        new_browser_args.append(f"args={browser_args}")

    _run("New Browser", *new_browser_args)
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
    base_url = _variable("${BASE_URL}", "http://next.localhost")
    _run("Go To", f"{base_url}{path}", "wait_until=domcontentloaded")
    _run("Wait For Load State", "domcontentloaded")


@keyword("Page Should Have Heading")
def page_should_have_heading(heading: str) -> None:
    _run("Get Text", f'role=heading[name="{heading}"]', "==", heading)


@keyword("Page Should Have Text")
def page_should_have_text(text: str) -> None:
    _run("Get Text", f"text={text}", "contains", text)


@keyword("Page Should Not Have Text")
def page_should_not_have_text(text: str) -> None:
    body = str(_run("Get Text", "body"))
    if text in body:
        raise AssertionError(f"Page unexpectedly contains text: {text}")


@keyword("Cross Site Form Post To Next Ui Path Should Be Blocked")
def cross_site_form_post_to_next_ui_path_should_be_blocked(path: str) -> None:
    base_url = _variable("${BASE_URL}", "http://next.localhost")
    target = f"{base_url}{path}"
    html = f"""
<!doctype html>
<html lang="en">
  <body>
    <form id="csrf" method="post" action="{escape(target)}">
      <input name="csrf_probe" value="1">
    </form>
    <script>document.getElementById('csrf').submit()</script>
  </body>
</html>
"""
    _run("Go To", f"data:text/html;charset=utf-8,{quote(html)}", "wait_until=domcontentloaded")
    try:
        _run("Wait For Load State", "networkidle")
    except Exception as exc:
        _built_in().log(f"Network idle was not reached after cross-site form POST: {exc}", "WARN")

    current_url = str(_run("Get Url"))
    body = str(_run("Get Text", "body"))
    success_markers = ("success", "summary", "created", "updated")
    handler_markers = ("Nieprawidłowe żądanie", "Podaj", "Dodaj co najmniej")
    auth_markers = (
        "401 - Access Denied",
        "User does not have permission",
        "Go to Login",
        "FinancialManager",
        "Not authenticated",
    )

    if any(marker in body for marker in success_markers + handler_markers):
        raise AssertionError(
            "Cross-site form POST reached the protected Next API handler instead "
            f"of being blocked by the auth boundary. URL={current_url!r}, body={body[:500]!r}"
        )

    if not any(marker in body for marker in auth_markers):
        raise AssertionError(
            "Cross-site form POST did not show an expected auth-boundary response. "
            f"URL={current_url!r}, body={body[:500]!r}"
        )
