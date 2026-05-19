from __future__ import annotations

import json
import os
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from html import escape
from pathlib import Path
from statistics import quantiles
from threading import Barrier
from uuid import uuid4

import allure
import httpx
import psycopg
import pytest


PASSWORD = "StressPass123!"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
ARTIFACT_DIR = Path("/workspace/tests/artifacts/load-capacity")


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    value = int(raw_value)
    return max(minimum, min(value, maximum))


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _capacity_steps() -> list[int]:
    raw_value = os.getenv("LOGIN_CAPACITY_STEPS", "100,250,500,1000")
    steps = sorted({int(part.strip()) for part in raw_value.split(",") if part.strip()})
    if not steps:
        raise ValueError("LOGIN_CAPACITY_STEPS must contain at least one integer")
    max_users = _env_int("LOGIN_CAPACITY_MAX_USERS", steps[-1], minimum=1, maximum=10_000)
    return [step for step in steps if step <= max_users]


def _paths() -> list[str]:
    raw_value = os.getenv("LOGIN_CAPACITY_PATHS", "/wallet,/transactions")
    paths = [part.strip() for part in raw_value.split(",") if part.strip()]
    if not paths:
        raise ValueError("LOGIN_CAPACITY_PATHS must contain at least one path")
    return paths


def _virtual_client_ip(index: int) -> str:
    """
    Use the 198.18.0.0/15 benchmarking range for virtual clients.
    The same address is reused across login and routed page requests so the
    HMAC fingerprint sees a stable client identity per virtual user.
    """
    second_octet = 18 + ((index // (250 * 256)) % 2)
    third_octet = (index // 250) % 256
    fourth_octet = (index % 250) + 1
    return f"198.{second_octet}.{third_octet}.{fourth_octet}"


def _p95(durations: list[float]) -> float:
    if not durations:
        return 0.0
    if len(durations) < 2:
        return durations[0]
    return quantiles(durations, n=20, method="inclusive")[18]


def _headers(
    case_id: str,
    client_ip: str,
    referer_path: str = "/login",
    user_agent: str = BROWSER_USER_AGENT,
) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": f"http://next.localhost:8081{referer_path}?capacity={case_id}",
        "User-Agent": user_agent,
        "Sec-CH-UA-Platform": '"Linux"',
        "X-Original-Client-IP": client_ip,
    }


def _traefik_headers(
    sessionid: str,
    hmac_token: str,
    client_ip: str,
    path: str,
) -> dict[str, str]:
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Cookie": f"sessionid={sessionid}; hmac={hmac_token}",
        "Host": "next.localhost",
        "Referer": f"http://next.localhost:8081{path}",
        "User-Agent": BROWSER_USER_AGENT,
        "Sec-CH-UA-Platform": '"Linux"',
        "X-Original-Client-IP": client_ip,
    }


def _verify_headers(
    sessionid: str,
    hmac_token: str,
    client_ip: str,
    case_id: str,
) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Cookie": f"sessionid={sessionid}; hmac={hmac_token}",
        "X-Forwarded-Host": "next.localhost",
        "User-Agent": BROWSER_USER_AGENT,
        "Sec-CH-UA-Platform": '"Linux"',
        "X-Original-Client-IP": client_ip,
        "X-Login-Capacity-Case": case_id,
    }


def _status_counts(responses: list[httpx.Response]) -> dict[str, int]:
    return {str(status): count for status, count in Counter(response.status_code for response in responses).items()}


def _response_sample(response: httpx.Response) -> str:
    return response.text[:300].replace("\n", " ").strip()


def _html_value(value: object) -> str:
    return escape(str(value))


def _format_errors(summary: dict[str, object]) -> str:
    errors = summary.get("errors")
    if not isinstance(errors, dict) or not errors:
        return "-"
    return ", ".join(f"{_html_value(name)}: {_html_value(count)}" for name, count in errors.items())


def _phase_cell(summary: dict[str, object]) -> str:
    ok = summary.get("ok", 0)
    total = summary.get("total", 0)
    p95 = summary.get("p95_seconds", 0)
    max_seconds = summary.get("max_seconds", 0)
    errors = _format_errors(summary)
    return (
        f"<strong>{_html_value(ok)}/{_html_value(total)}</strong>"
        f"<span>p95 {_html_value(p95)}s</span>"
        f"<span>max {_html_value(max_seconds)}s</span>"
        f"<span>errors: {errors}</span>"
    )


def _render_sample_rows(samples: object) -> str:
    if not isinstance(samples, list) or not samples:
        return '<tr><td colspan="6" class="muted">No samples</td></tr>'
    rows = []
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        rows.append(
            "<tr>"
            f"<td>{_html_value(sample.get('index', '-'))}</td>"
            f"<td>{_html_value(sample.get('path', '-'))}</td>"
            f"<td>{_html_value(sample.get('client_ip', '-'))}</td>"
            f"<td>{_html_value(sample.get('status', sample.get('error', '-')))}</td>"
            f"<td>{_html_value(sample.get('duration', '-'))}</td>"
            f"<td><code>{_html_value(sample.get('body', ''))}</code></td>"
            "</tr>"
        )
    return "".join(rows) or '<tr><td colspan="6" class="muted">No samples</td></tr>'


def _render_samples_section(title: str, summary: dict[str, object]) -> str:
    samples = []
    for sample_key in ("error_samples", "non_200_samples", "login_text_samples"):
        sample_list = summary.get(sample_key)
        if isinstance(sample_list, list):
            for item in sample_list:
                if isinstance(item, dict):
                    samples.append({"sample_type": sample_key, **item})
    return (
        f"<h3>{_html_value(title)}</h3>"
        '<table class="samples">'
        "<thead><tr><th>Index</th><th>Path</th><th>Client IP</th>"
        "<th>Status/Error</th><th>Duration</th><th>Body sample</th></tr></thead>"
        f"<tbody>{_render_sample_rows(samples)}</tbody>"
        "</table>"
    )


def _render_html_report(report: dict[str, object]) -> str:
    config = report.get("config", {})
    if not isinstance(config, dict):
        config = {}
    runtime = config.get("session_auth_runtime", {})
    if not isinstance(runtime, dict):
        runtime = {}
    paths = config.get("paths", [])
    if not isinstance(paths, list):
        paths = []

    step_rows = []
    detail_sections = []
    for step in report.get("steps", []):
        if not isinstance(step, dict):
            continue
        passed = bool(step.get("passed"))
        status_class = "pass" if passed else "fail"
        route_cells = []
        routes = step.get("routes", {})
        if not isinstance(routes, dict):
            routes = {}
        for path in paths:
            route_summary = routes.get(path, {})
            if not isinstance(route_summary, dict):
                route_summary = {}
            route_cells.append(f"<td>{_phase_cell(route_summary)}</td>")

        step_rows.append(
            "<tr>"
            f"<td>{_html_value(step.get('users', '-'))}</td>"
            f'<td><span class="badge {status_class}">{_html_value("PASS" if passed else "FAIL")}</span></td>'
            f"<td>{_html_value(step.get('failed_phase') or '-')}</td>"
            f"<td>{_html_value(step.get('elapsed_seconds', '-'))}s</td>"
            f"<td>{_phase_cell(step.get('login', {}) if isinstance(step.get('login'), dict) else {})}</td>"
            f"<td>{_phase_cell(step.get('verify_session', {}) if isinstance(step.get('verify_session'), dict) else {})}</td>"
            f"{''.join(route_cells)}"
            f"<td>{_phase_cell(step.get('logout', {}) if isinstance(step.get('logout'), dict) else {})}</td>"
            "</tr>"
        )

        failed_phase = step.get("failed_phase") or "none"
        detail_sections.append(
            f"<section><h2>Step {_html_value(step.get('users', '-'))} users</h2>"
            f"<p><strong>Failed phase:</strong> {_html_value(failed_phase)}</p>"
            f"<p>{_html_value(step.get('failure_hint') or 'No failure detected.')}</p>"
            f"{_render_samples_section('Login samples', step.get('login', {}) if isinstance(step.get('login'), dict) else {})}"
            f"{_render_samples_section('Direct verifySession samples', step.get('verify_session', {}) if isinstance(step.get('verify_session'), dict) else {})}"
            + "".join(
                _render_samples_section(
                    f"Route {path} samples",
                    routes.get(path, {}) if isinstance(routes.get(path), dict) else {},
                )
                for path in paths
            )
            + f"{_render_samples_section('Logout samples', step.get('logout', {}) if isinstance(step.get('logout'), dict) else {})}"
            "</section>"
        )

    route_headers = "".join(f"<th>Route {_html_value(path)}</th>" for path in paths)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Login Capacity Probe</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f9fc;
      --panel: #ffffff;
      --text: #182033;
      --muted: #667085;
      --line: #d9e0ea;
      --pass: #166534;
      --fail: #b42318;
      --warn: #92400e;
    }}
    body {{
      margin: 0;
      padding: 32px;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    h1, h2, h3 {{ margin: 0 0 12px; }}
    h1 {{ font-size: 28px; }}
    h2 {{ font-size: 20px; margin-top: 28px; }}
    h3 {{ font-size: 16px; margin-top: 18px; }}
    p {{ color: var(--muted); }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin: 20px 0;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }}
    .label {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }}
    .value {{ display: block; margin-top: 6px; font-size: 22px; font-weight: 700; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      margin-bottom: 20px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 10px 12px;
      text-align: left;
      vertical-align: top;
      font-size: 13px;
    }}
    th {{ background: #eef2f7; color: #344054; }}
    td span {{ display: block; color: var(--muted); margin-top: 3px; }}
    code {{ white-space: pre-wrap; word-break: break-word; }}
    .badge {{
      display: inline-block;
      padding: 3px 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
    }}
    .badge.pass {{ color: var(--pass); background: #dcfce7; }}
    .badge.fail {{ color: var(--fail); background: #fee4e2; }}
    .muted {{ color: var(--muted); }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      margin-top: 18px;
    }}
    .samples td:last-child {{ max-width: 520px; }}
  </style>
</head>
<body>
  <h1>Login Capacity Probe</h1>
  <p>Prod-like login/session capacity evidence generated from login_capacity_probe.json.</p>
  <div class="cards">
    <div class="card"><span class="label">Last passing users</span><span class="value">{_html_value(report.get('last_passing_users'))}</span></div>
    <div class="card"><span class="label">First failing users</span><span class="value">{_html_value(report.get('first_failing_users'))}</span></div>
    <div class="card"><span class="label">Gunicorn workers</span><span class="value">{_html_value(runtime.get('gunicorn_workers', 'unknown'))}</span></div>
    <div class="card"><span class="label">Timeout</span><span class="value">{_html_value(config.get('request_timeout_seconds', 'unknown'))}s</span></div>
  </div>
  <h2>Ramp Summary</h2>
  <table>
    <thead>
      <tr><th>Users</th><th>Status</th><th>Failed phase</th><th>Elapsed</th><th>Login</th><th>Direct verifySession</th>{route_headers}<th>Logout</th></tr>
    </thead>
    <tbody>{''.join(step_rows)}</tbody>
  </table>
  <h2>Runtime</h2>
  <table>
    <tbody>
      <tr><th>ENV_TYPE</th><td>{_html_value(runtime.get('env_type', 'unknown'))}</td></tr>
      <tr><th>GUNICORN_WORKERS</th><td>{_html_value(runtime.get('gunicorn_workers', 'unknown'))}</td></tr>
      <tr><th>GUNICORN_TIMEOUT</th><td>{_html_value(runtime.get('gunicorn_timeout', 'unknown'))}</td></tr>
      <tr><th>ALLOWED_HOSTS</th><td>{_html_value(runtime.get('allowed_hosts', 'unknown'))}</td></tr>
    </tbody>
  </table>
  {''.join(detail_sections)}
</body>
</html>
"""


def _read_seed_password_hash(session_url: str) -> str:
    suffix = uuid4().hex[:10]
    user = {
        "first_name": "Capacity",
        "last_name": "Seed",
        "username": f"seed{suffix}",
        "email": f"capacity.seed.{suffix}@example.com",
        "password": PASSWORD,
    }
    response = httpx.post(
        f"{session_url}/register/",
        headers=_headers(f"seed-{suffix}", "10.254.1.10", referer_path="/register"),
        json=user,
        timeout=20.0,
    )
    assert response.status_code == 201, response.text

    with psycopg.connect(
        host="session-db",
        port=5432,
        dbname="session_test",
        user="myuser",
        password="mypassword",
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE userauth_user
                   SET is_active = TRUE,
                       is_verified = TRUE
                 WHERE email = %s
             RETURNING password
                """,
                (user["email"],),
            )
            row = cursor.fetchone()
            assert row is not None
            return str(row[0])


def _create_capacity_users(session_url: str, count: int) -> list[dict[str, str]]:
    suffix = uuid4().hex[:10]
    password_hash = _read_seed_password_hash(session_url)
    users = [
        {
            "username": f"cap{suffix[:6]}{index:05d}",
            "email": f"capacity.{suffix}.{index}@example.com",
            "client_ip": _virtual_client_ip(index),
        }
        for index in range(count)
    ]

    with psycopg.connect(
        host="session-db",
        port=5432,
        dbname="session_test",
        user="myuser",
        password="mypassword",
    ) as conn:
        with conn.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO userauth_user (
                    password,
                    last_login,
                    is_superuser,
                    username,
                    first_name,
                    last_name,
                    email,
                    is_staff,
                    is_active,
                    date_joined,
                    is_two_factor,
                    is_blocked,
                    is_verified
                )
                VALUES (%s, NULL, FALSE, %s, 'Capacity', 'User', %s, FALSE, TRUE, NOW(), FALSE, FALSE, TRUE)
                """,
                [(password_hash, user["username"], user["email"]) for user in users],
            )
    return users


def _login_after_barrier(
    barrier: Barrier,
    session_url: str,
    user: dict[str, str],
    index: int,
    timeout: float,
) -> dict[str, object]:
    barrier.wait(timeout=60.0)
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{session_url}/login/",
                headers=_headers(f"capacity-login-{index}", user["client_ip"]),
                json={"email": user["email"], "password": PASSWORD},
            )
        return {
            "index": index,
            "user": user,
            "response": response,
            "duration": time.perf_counter() - started,
            "error": None,
        }
    except Exception as exc:
        return {
            "index": index,
            "user": user,
            "response": None,
            "duration": time.perf_counter() - started,
            "error": type(exc).__name__,
        }


def _verify_after_barrier(
    barrier: Barrier,
    session_url: str,
    session: dict[str, object],
    timeout: float,
) -> dict[str, object]:
    barrier.wait(timeout=60.0)
    started = time.perf_counter()
    hmac_token = str(session["hmac_token"])
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            response = client.get(
                f"{session_url}/verifySession/",
                headers=_verify_headers(
                    sessionid=str(session["sessionid"]),
                    hmac_token=hmac_token,
                    client_ip=str(session["client_ip"]),
                    case_id=f"capacity-verify-{session['index']}",
                ),
            )
        refreshed_hmac = response.cookies.get("hmac")
        if refreshed_hmac:
            hmac_token = refreshed_hmac
        return {
            "index": session["index"],
            "email": session["email"],
            "client_ip": session["client_ip"],
            "session": {**session, "hmac_token": hmac_token},
            "response": response,
            "duration": time.perf_counter() - started,
            "error": None,
        }
    except Exception as exc:
        return {
            "index": session["index"],
            "email": session["email"],
            "client_ip": session["client_ip"],
            "session": session,
            "response": None,
            "duration": time.perf_counter() - started,
            "error": type(exc).__name__,
        }


def _route_path_after_barrier(
    barrier: Barrier,
    traefik_url: str,
    session: dict[str, object],
    path: str,
    timeout: float,
) -> dict[str, object]:
    barrier.wait(timeout=60.0)
    started = time.perf_counter()
    hmac_token = str(session["hmac_token"])
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            response = client.get(
                f"{traefik_url}{path}",
                headers=_traefik_headers(
                    sessionid=str(session["sessionid"]),
                    hmac_token=hmac_token,
                    client_ip=str(session["client_ip"]),
                    path=path,
                ),
            )
        refreshed_hmac = response.cookies.get("hmac")
        if refreshed_hmac:
            hmac_token = refreshed_hmac
        return {
            "index": session["index"],
            "email": session["email"],
            "client_ip": session["client_ip"],
            "session": {**session, "hmac_token": hmac_token},
            "path": path,
            "response": response,
            "has_login_text": "Zaloguj" in response.text or "Please login" in response.text,
            "duration": time.perf_counter() - started,
            "error": None,
        }
    except Exception as exc:
        return {
            "index": session["index"],
            "email": session["email"],
            "client_ip": session["client_ip"],
            "session": session,
            "path": path,
            "response": None,
            "has_login_text": False,
            "duration": time.perf_counter() - started,
            "error": type(exc).__name__,
        }


def _logout_after_barrier(
    barrier: Barrier,
    session_url: str,
    session: dict[str, object],
    timeout: float,
) -> dict[str, object]:
    barrier.wait(timeout=60.0)
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{session_url}/logout/",
                headers={
                    **_headers(
                        f"capacity-logout-{session['index']}",
                        str(session["client_ip"]),
                        referer_path="/logout",
                    ),
                    "Cookie": f"sessionid={session['sessionid']}; hmac={session['hmac_token']}",
                },
            )
        return {
            "status": response.status_code,
            "duration": time.perf_counter() - started,
            "error": None,
        }
    except Exception as exc:
        return {
            "status": None,
            "duration": time.perf_counter() - started,
            "error": type(exc).__name__,
        }


def _run_threaded(items, worker, max_workers: int) -> list[dict[str, object]]:
    if not items:
        return []
    barrier = Barrier(len(items) + 1)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(worker, barrier, item)
            for item in items
        ]
        barrier.wait(timeout=60.0)
        return [future.result(timeout=180.0) for future in futures]


def _summarize_login(results: list[dict[str, object]]) -> dict[str, object]:
    responses = [result["response"] for result in results if isinstance(result.get("response"), httpx.Response)]
    errors = Counter(str(result["error"]) for result in results if result.get("error"))
    durations = [float(result["duration"]) for result in results]
    non_200_samples = []
    for result in results:
        response = result.get("response")
        if not isinstance(response, httpx.Response) or response.status_code == 200:
            continue
        non_200_samples.append(
            {
                "index": result["index"],
                "email": result["user"]["email"],
                "client_ip": result["user"]["client_ip"],
                "status": response.status_code,
                "body": _response_sample(response),
            }
        )
        if len(non_200_samples) >= 5:
            break
    error_samples = []
    for result in results:
        if not result.get("error"):
            continue
        error_samples.append(
            {
                "index": result["index"],
                "email": result["user"]["email"],
                "client_ip": result["user"]["client_ip"],
                "error": result["error"],
                "duration": round(float(result["duration"]), 4),
            }
        )
        if len(error_samples) >= 5:
            break

    return {
        "total": len(results),
        "ok": sum(1 for response in responses if response.status_code == 200),
        "status_counts": _status_counts(responses),
        "errors": dict(errors),
        "error_samples": error_samples,
        "non_200_samples": non_200_samples,
        "p95_seconds": round(_p95(durations), 4),
        "max_seconds": round(max(durations, default=0.0), 4),
    }


def _summarize_http_results(
    results: list[dict[str, object]],
    expected_total: int,
    require_no_login_text: bool = False,
) -> dict[str, object]:
    responses = [result["response"] for result in results if isinstance(result.get("response"), httpx.Response)]
    errors = Counter(str(result["error"]) for result in results if result.get("error"))
    durations = [float(result["duration"]) for result in results]
    login_text_count = sum(1 for result in results if result.get("has_login_text"))

    non_200_samples = []
    login_text_samples = []
    error_samples = []
    for result in results:
        response = result.get("response")
        if isinstance(response, httpx.Response) and response.status_code != 200:
            non_200_samples.append(
                {
                    "index": result["index"],
                    "email": result["email"],
                    "client_ip": result["client_ip"],
                    "path": result.get("path"),
                    "status": response.status_code,
                    "body": _response_sample(response),
                }
            )
            if len(non_200_samples) >= 5:
                break

    for result in results:
        response = result.get("response")
        if not result.get("has_login_text") or not isinstance(response, httpx.Response):
            continue
        login_text_samples.append(
            {
                "index": result["index"],
                "email": result["email"],
                "client_ip": result["client_ip"],
                "path": result.get("path"),
                "status": response.status_code,
                "body": _response_sample(response),
            }
        )
        if len(login_text_samples) >= 5:
            break

    for result in results:
        if not result.get("error"):
            continue
        error_samples.append(
            {
                "index": result["index"],
                "email": result["email"],
                "client_ip": result["client_ip"],
                "path": result.get("path"),
                "error": result["error"],
                "duration": round(float(result["duration"]), 4),
            }
        )
        if len(error_samples) >= 5:
            break

    return {
        "total": len(results),
        "expected_total": expected_total,
        "ok": sum(
            1
            for result in results
            if isinstance(result.get("response"), httpx.Response)
            and result["response"].status_code == 200
            and (not require_no_login_text or not result.get("has_login_text"))
        ),
        "status_counts": _status_counts(responses),
        "errors": dict(errors),
        "error_samples": error_samples,
        "non_200_samples": non_200_samples,
        "login_text_count": login_text_count,
        "login_text_samples": login_text_samples,
        "p95_seconds": round(_p95(durations), 4),
        "max_seconds": round(max(durations, default=0.0), 4),
    }


def _summarize_logout(results: list[dict[str, object]]) -> dict[str, object]:
    statuses = [result["status"] for result in results if result["status"] is not None]
    errors = Counter(str(result["error"]) for result in results if result.get("error"))
    durations = [float(result["duration"]) for result in results]
    error_samples = []
    for result in results:
        if not result.get("error"):
            continue
        error_samples.append(
            {
                "error": result["error"],
                "duration": round(float(result["duration"]), 4),
            }
        )
        if len(error_samples) >= 5:
            break
    return {
        "total": len(results),
        "ok": sum(1 for status_code in statuses if status_code == 200),
        "status_counts": {str(status): count for status, count in Counter(statuses).items()},
        "errors": dict(errors),
        "error_samples": error_samples,
        "p95_seconds": round(_p95(durations), 4),
        "max_seconds": round(max(durations, default=0.0), 4),
    }


def _failure_phase(
    user_count: int,
    paths: list[str],
    login_summary: dict[str, object],
    verify_summary: dict[str, object],
    route_summaries: dict[str, dict[str, object]],
    logout_summary: dict[str, object],
) -> str | None:
    if login_summary["ok"] != user_count:
        return "login"

    if verify_summary["ok"] != user_count:
        return "verify_session"

    for path in paths:
        path_summary = route_summaries.get(path, {})
        if path_summary.get("ok") != user_count or path_summary.get("login_text_count") != 0:
            return f"route:{path}"

    if logout_summary["ok"] != user_count:
        return "logout"

    return None


def _failure_hint(
    phase: str | None,
    login_summary: dict[str, object],
    verify_summary: dict[str, object],
    route_summaries: dict[str, dict[str, object]],
) -> str | None:
    if phase is None:
        return None

    errors = login_summary.get("errors", {})
    if phase == "login" and isinstance(errors, dict) and errors.get("ReadTimeout"):
        return (
            "Client read timeouts occurred during the direct session-auth login phase. "
            "Routed /wallet and /transactions requests were not attempted for this step, "
            "so the observed breakpoint points to login throughput/queue saturation rather "
            "than HMAC replay, ForwardAuth, Next UI, or wallet page handling."
        )

    status_counts = login_summary.get("status_counts", {})
    if phase == "login" and isinstance(status_counts, dict) and status_counts.get("429"):
        return (
            "The direct session-auth login phase returned HTTP 429 before routed pages were "
            "attempted. Inspect login.non_200_samples to determine whether the limiter is "
            "DRF LoginIPThrottle, application login-attempt blocking, or another 429 path."
        )

    if phase == "verify_session":
        verify_errors = verify_summary.get("errors", {})
        if isinstance(verify_errors, dict) and verify_errors.get("ReadTimeout"):
            return (
                "Login completed, but direct session-auth /verifySession/ timed out. "
                "This isolates the breakpoint to session verification throughput before "
                "Traefik/Next routed page rendering is tested for this step."
            )
        return (
            "Login completed, but direct session-auth /verifySession/ failed. Inspect "
            "verify_session.status_counts, non_200_samples, and error_samples for the "
            "exact response."
        )

    if phase and phase.startswith("route:"):
        path = phase.split(":", 1)[1]
        route_summary = route_summaries.get(path, {})
        route_errors = route_summary.get("errors", {})
        if isinstance(route_errors, dict) and route_errors.get("ReadTimeout"):
            return (
                f"Direct /verifySession/ completed for this step, but routed {path} "
                "requests timed out through Traefik/ForwardAuth/Next UI. Inspect "
                f"routes[{path}].error_samples and service logs to determine whether "
                "the timeout is in ForwardAuth, Next rendering, or downstream page data."
            )
        return (
            f"Direct /verifySession/ completed, but routed {path} failed. Inspect "
            f"routes[{path}].status_counts, non_200_samples, login_text_samples, and "
            "error_samples for the exact response."
        )

    if phase == "logout":
        return "Login and routed pages completed, but logout did not complete for all users."

    return "Capacity step failed; inspect per-phase status counts and errors."


def _write_report(report: dict[str, object]) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = ARTIFACT_DIR / "login_capacity_probe.json"
    html_path = ARTIFACT_DIR / "login_capacity_probe.html"
    html_report = _render_html_report(report)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    html_path.write_text(html_report, encoding="utf-8")
    allure.attach(
        json.dumps(report, indent=2, sort_keys=True),
        name="login-capacity-probe.json",
        attachment_type=allure.attachment_type.JSON,
    )
    allure.attach(
        html_report,
        name="login-capacity-summary.html",
        attachment_type=allure.attachment_type.HTML,
    )
    return report_path


@pytest.mark.security
@pytest.mark.performance
@pytest.mark.load
@pytest.mark.stress
@pytest.mark.capacity
@allure.epic("Security")
@allure.feature("Capacity")
@allure.story("Prod-like session-auth capacity for concurrent authenticated Next UI journeys")
@allure.severity(allure.severity_level.BLOCKER)
@allure.tag("auth", "security", "performance", "capacity", "login", "forwardauth")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Ramps concurrent unique users through login, direct session verification, Traefik "
    "ForwardAuth, /wallet, /transactions, and logout against a prod-like session-auth "
    "Gunicorn runtime. The probe records the first failing step as capacity evidence "
    "instead of pretending the repository has a product-level global user admission limit."
)
class TestLoginCapacityProbe:
    def test_capacity_probe_records_first_breakpoint_for_authenticated_next_ui_journeys(
        self,
        session_url: str,
        traefik_url: str,
    ) -> None:
        if os.getenv("LOGIN_CAPACITY_ENABLED") != "1":
            pytest.skip("capacity probe is explicit; run make login-capacity-test")

        try:
            threading.stack_size(256 * 1024)
        except (RuntimeError, ValueError):
            pass

        steps = _capacity_steps()
        paths = _paths()
        max_users = steps[-1]
        total_prepared_users = sum(steps)
        request_timeout = float(os.getenv("LOGIN_CAPACITY_REQUEST_TIMEOUT_SECONDS", "30"))
        min_pass_users = _env_int(
            "LOGIN_CAPACITY_MIN_PASS_USERS",
            steps[0],
            minimum=1,
            maximum=max_users,
        )
        stop_on_failure = _env_bool("LOGIN_CAPACITY_STOP_ON_FAILURE", True)

        all_users = _create_capacity_users(session_url, total_prepared_users)
        report: dict[str, object] = {
            "config": {
                "steps": steps,
                "total_prepared_users": total_prepared_users,
                "paths": paths,
                "request_timeout_seconds": request_timeout,
                "min_pass_users": min_pass_users,
                "stop_on_failure": stop_on_failure,
                "session_auth_runtime": {
                    "env_type": os.getenv("SESSION_AUTH_ENV_TYPE", "unknown"),
                    "gunicorn_workers": os.getenv("SESSION_AUTH_GUNICORN_WORKERS", "unknown"),
                    "gunicorn_timeout": os.getenv("SESSION_AUTH_GUNICORN_TIMEOUT", "unknown"),
                    "gunicorn_log_level": os.getenv("SESSION_AUTH_GUNICORN_LOG_LEVEL", "unknown"),
                    "allowed_hosts": os.getenv("SESSION_AUTH_ALLOWED_HOSTS", "unknown"),
                },
            },
            "diagnostics": {
                "virtual_client_ip_strategy": (
                    "one stable 198.18.0.0/15 benchmarking-range X-Original-Client-IP "
                    "per virtual user, reused for login and routed page requests"
                ),
                "login_phase": "direct POST to session-auth /login/",
                "direct_verify_phase": (
                    "direct GET to session-auth /verifySession/ with the login cookies "
                    "and stable virtual client IP"
                ),
                "routed_page_phases": (
                    "Traefik Host next.localhost routes each requested path through "
                    "ForwardAuth /verifySession/ and then Next UI/page handlers"
                ),
                "prod_host_note": (
                    "prod-like session-auth enables USE_X_FORWARDED_HOST; capacity target "
                    "therefore includes next.localhost in ALLOWED_HOSTS for routed ForwardAuth checks"
                ),
                "known_runtime_bottleneck": (
                    "login throughput is expected to be dominated by session-auth Gunicorn "
                    "worker count, synchronous request handling, and Django password hash "
                    "verification before routed page checks run"
                ),
            },
            "steps": [],
            "last_passing_users": 0,
            "first_failing_users": None,
        }

        user_offset = 0
        for user_count in steps:
            users = all_users[user_offset:user_offset + user_count]
            user_offset += user_count
            started = time.perf_counter()

            login_results = _run_threaded(
                list(enumerate(users)),
                lambda barrier, item: _login_after_barrier(
                    barrier,
                    session_url,
                    item[1],
                    index=item[0],
                    timeout=request_timeout,
                ),
                max_workers=user_count,
            )
            login_summary = _summarize_login(login_results)
            sessions = []
            for result in login_results:
                response = result.get("response")
                if not isinstance(response, httpx.Response) or response.status_code != 200:
                    continue
                user = result["user"]
                assert isinstance(user, dict)
                sessionid = response.cookies.get("sessionid")
                hmac_token = response.cookies.get("hmac_token")
                if not sessionid or not hmac_token:
                    continue
                sessions.append(
                    {
                        "index": result["index"],
                        "email": user["email"],
                        "client_ip": user["client_ip"],
                        "sessionid": sessionid,
                        "hmac_token": hmac_token,
                    }
                )

            verify_results = []
            route_results_by_path: dict[str, list[dict[str, object]]] = {path: [] for path in paths}
            logout_results = []
            if len(sessions) == user_count:
                verify_results = _run_threaded(
                    sessions,
                    lambda barrier, session: _verify_after_barrier(
                        barrier,
                        session_url,
                        session,
                        timeout=request_timeout,
                    ),
                    max_workers=user_count,
                )
                successful_sessions = [
                    result["session"]
                    for result in verify_results
                    if not result.get("error")
                    and isinstance(result.get("response"), httpx.Response)
                    and result["response"].status_code == 200
                ]
                for path in paths:
                    route_results = _run_threaded(
                        successful_sessions,
                        lambda barrier, session, path=path: _route_path_after_barrier(
                            barrier,
                            traefik_url,
                            session,
                            path=path,
                            timeout=request_timeout,
                        ),
                        max_workers=max(1, len(successful_sessions)),
                    )
                    route_results_by_path[path] = route_results
                    successful_sessions = [
                        result["session"]
                        for result in route_results
                        if not result.get("error")
                        and isinstance(result.get("response"), httpx.Response)
                        and result["response"].status_code == 200
                        and not result.get("has_login_text")
                    ]
                logout_results = _run_threaded(
                    successful_sessions,
                    lambda barrier, session: _logout_after_barrier(
                        barrier,
                        session_url,
                        session,
                        timeout=request_timeout,
                    ),
                    max_workers=max(1, len(successful_sessions)),
                )

            verify_summary = _summarize_http_results(
                verify_results,
                expected_total=user_count if len(sessions) == user_count else 0,
            )
            route_summaries = {
                path: _summarize_http_results(
                    route_results_by_path[path],
                    expected_total=user_count,
                    require_no_login_text=True,
                )
                for path in paths
            }
            logout_summary = _summarize_logout(logout_results)
            failed_phase = _failure_phase(
                user_count=user_count,
                paths=paths,
                login_summary=login_summary,
                verify_summary=verify_summary,
                route_summaries=route_summaries,
                logout_summary=logout_summary,
            )
            passed = failed_phase is None

            step_report = {
                "users": user_count,
                "passed": passed,
                "failed_phase": failed_phase,
                "failure_hint": _failure_hint(
                    failed_phase,
                    login_summary=login_summary,
                    verify_summary=verify_summary,
                    route_summaries=route_summaries,
                ),
                "unique_virtual_client_ips": user_count,
                "elapsed_seconds": round(time.perf_counter() - started, 4),
                "login": login_summary,
                "verify_session": verify_summary,
                "routes": route_summaries,
                "logout": logout_summary,
            }
            report["steps"].append(step_report)

            if passed:
                report["last_passing_users"] = user_count
            else:
                report["first_failing_users"] = user_count
                if stop_on_failure:
                    break

        report_path = _write_report(report)

        assert report["last_passing_users"] >= min_pass_users, (
            f"capacity baseline {min_pass_users} users not met; "
            f"see {report_path}"
        )
