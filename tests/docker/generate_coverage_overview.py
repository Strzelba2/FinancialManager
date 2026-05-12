#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Counts:
    lines_total: int = 0
    lines_covered: int = 0
    branches_total: int = 0
    branches_covered: int = 0
    functions_total: int = 0
    functions_covered: int = 0

    def add(self, other: "Counts") -> None:
        self.lines_total += other.lines_total
        self.lines_covered += other.lines_covered
        self.branches_total += other.branches_total
        self.branches_covered += other.branches_covered
        self.functions_total += other.functions_total
        self.functions_covered += other.functions_covered

    @property
    def line_pct(self) -> float | None:
        return pct(self.lines_covered, self.lines_total)

    @property
    def branch_pct(self) -> float | None:
        return pct(self.branches_covered, self.branches_total)

    @property
    def function_pct(self) -> float | None:
        return pct(self.functions_covered, self.functions_total)

    @property
    def total_pct(self) -> float | None:
        total = self.lines_total + self.branches_total
        covered = self.lines_covered + self.branches_covered
        return pct(covered, total)


@dataclass
class FileCoverage:
    repo_path: str
    counts: Counts
    executable_lines: dict[int, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class Domain:
    name: str
    description: str
    prefixes: tuple[str, ...]


@dataclass(frozen=True)
class ServiceConfig:
    name: str
    label: str
    html_dir: str
    kind: str
    coverage_path: str
    source_prefix: str
    domains: tuple[Domain, ...]


def pct(covered: int, total: int) -> float | None:
    if total <= 0:
        return None
    return covered * 100.0 / total


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}%"


def css_class(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value >= 80:
        return "good"
    if value >= 50:
        return "warn"
    return "bad"


def parse_condition_coverage(value: str | None) -> tuple[int, int]:
    if not value:
        return (0, 0)
    match = re.search(r"\((\d+)/(\d+)\)", value)
    if not match:
        return (0, 0)
    return int(match.group(1)), int(match.group(2))


def python_repo_path(source_prefix: str, filename: str) -> str:
    if source_prefix == "session":
        if filename in {"adminmiddleware.py", "logmiddleware.py", "reqmiddleware.py"}:
            return f"session/middleware/{filename}"
        if filename.startswith(("userauth/", "utils/", "middleware/")):
            return f"session/{filename}"
        if filename == "utils.py":
            return "session/utils/utils.py"
        return f"session/userauth/{filename}"

    if source_prefix.endswith("/app") and filename.startswith("app/"):
        service_prefix = source_prefix[:-4]
        return f"{service_prefix}/{filename}".replace("//", "/")

    return f"{source_prefix}/{filename}".replace("//", "/")


def python_source_repo_base(source_prefix: str, source: str) -> str | None:
    if source_prefix == "session":
        name = Path(source).name
        if name in {"middleware", "userauth", "utils"}:
            return f"session/{name}"
        return None

    marker = "/app"
    if source_prefix.endswith(marker) and marker in source:
        suffix = source.split(marker, 1)[1].strip("/")
        if suffix:
            return f"{source_prefix}/{suffix}".replace("//", "/")
        return source_prefix

    return None


def resolve_python_repo_path(
    root: Path,
    source_prefix: str,
    filename: str,
    source_paths: list[str],
) -> str:
    for source in source_paths:
        repo_base = python_source_repo_base(source_prefix, source)
        if repo_base is None:
            continue
        candidate = f"{repo_base}/{filename}".replace("//", "/")
        if (root / candidate).exists():
            return candidate

    return python_repo_path(source_prefix, filename)


def parse_python_coverage(path: Path, root: Path, source_prefix: str) -> dict[str, FileCoverage]:
    if not path.exists():
        return {}

    xml_root = ET.parse(path).getroot()
    source_paths = [node.text or "" for node in xml_root.findall("./sources/source")]
    files: dict[str, FileCoverage] = {}
    for class_node in xml_root.findall(".//class"):
        filename = class_node.attrib["filename"]
        repo_path = resolve_python_repo_path(root, source_prefix, filename, source_paths)
        counts = Counts()
        executable_lines: dict[int, bool] = {}

        for line_node in class_node.findall("./lines/line"):
            line_number = int(line_node.attrib["number"])
            hits = int(line_node.attrib.get("hits", "0"))
            counts.lines_total += 1
            if hits > 0:
                counts.lines_covered += 1
            executable_lines[line_number] = hits > 0

            if line_node.attrib.get("branch") == "true":
                covered, total = parse_condition_coverage(line_node.attrib.get("condition-coverage"))
                counts.branches_covered += covered
                counts.branches_total += total

        files[repo_path] = FileCoverage(repo_path=repo_path, counts=counts, executable_lines=executable_lines)

    return files


def parse_python_function_index(path: Path, source_prefix: str) -> dict[str, Counts]:
    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8", errors="ignore")
    functions_by_file: dict[str, Counts] = {}
    for row in re.findall(r'<tr class="region">(.*?)</tr>', text, flags=re.DOTALL):
        name_cells = re.findall(r'<td class="name">.*?</td>', row, flags=re.DOTALL)
        if len(name_cells) < 2 or "no-noun" in name_cells[1]:
            continue

        path_text = re.sub(r"<.*?>", "", name_cells[0])
        path_text = html.unescape(path_text).replace("\u2009", "").strip()
        if not path_text:
            continue

        ratios = re.findall(r'data-ratio="(\d+) (\d+)"', row)
        if not ratios:
            continue

        covered_items, total_items = (int(value) for value in ratios[0])
        if total_items <= 0:
            continue

        repo_path = python_repo_path(source_prefix, path_text)
        counts = functions_by_file.setdefault(repo_path, Counts())
        counts.functions_total += 1
        if covered_items > 0:
            counts.functions_covered += 1

    return functions_by_file


def apply_python_function_coverage(files: dict[str, FileCoverage], path: Path, source_prefix: str) -> None:
    function_counts = parse_python_function_index(path, source_prefix)
    for repo_path, counts in function_counts.items():
        if repo_path not in files:
            files[repo_path] = FileCoverage(repo_path=repo_path, counts=Counts())
        files[repo_path].counts.functions_total = counts.functions_total
        files[repo_path].counts.functions_covered = counts.functions_covered


def parse_lcov(path: Path, source_prefix: str) -> dict[str, FileCoverage]:
    if not path.exists():
        return {}

    files: dict[str, FileCoverage] = {}
    current_path: str | None = None
    counts = Counts()
    executable_lines: dict[int, bool] = {}

    def flush() -> None:
        nonlocal current_path, counts, executable_lines
        if current_path is None:
            return
        files[current_path] = FileCoverage(
            repo_path=current_path,
            counts=counts,
            executable_lines=executable_lines,
        )
        current_path = None
        counts = Counts()
        executable_lines = {}

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("SF:"):
            flush()
            filename = line[3:]
            current_path = f"{source_prefix}/{filename}".replace("//", "/")
        elif line.startswith("DA:") and current_path:
            number_raw, hits_raw = line[3:].split(",", 1)
            line_number = int(number_raw)
            hits = int(hits_raw)
            counts.lines_total += 1
            if hits > 0:
                counts.lines_covered += 1
            executable_lines[line_number] = hits > 0
        elif line.startswith("BRDA:") and current_path:
            counts.branches_total += 1
            taken = line.rsplit(",", 1)[-1]
            if taken != "-" and int(taken) > 0:
                counts.branches_covered += 1
        elif line.startswith("FNF:") and current_path:
            counts.functions_total = int(line[4:])
        elif line.startswith("FNH:") and current_path:
            counts.functions_covered = int(line[4:])
        elif line == "end_of_record":
            flush()

    flush()
    return files


def aggregate(files: dict[str, FileCoverage], prefixes: tuple[str, ...] | None = None) -> Counts:
    counts = Counts()
    for path, file_coverage in files.items():
        if prefixes is None or any(path.startswith(prefix) for prefix in prefixes):
            counts.add(file_coverage.counts)
    return counts


def load_changed_lines(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "base": "unknown",
            "generated_at": None,
            "files": {},
            "error": "Changed-code coverage input was not generated.",
        }
    return json.loads(path.read_text(encoding="utf-8"))


def service_for_path(path: str) -> str | None:
    if path.startswith("stock/app/"):
        return "stock"
    if path.startswith("wallet/app/"):
        return "wallet"
    if path.startswith(("session/userauth/", "session/utils/", "session/middleware/")):
        return "session"
    if path.startswith("next-ui/src/"):
        return "next-ui"
    return None


def changed_code_rows(
    changed_payload: dict[str, object],
    coverage_by_service: dict[str, dict[str, FileCoverage]],
) -> tuple[list[dict[str, object]], Counts, int]:
    rows: list[dict[str, object]] = []
    total_counts = Counts()
    ignored_non_executable = 0

    files = changed_payload.get("files", {})
    if not isinstance(files, dict):
        return rows, total_counts, ignored_non_executable

    for path, changed_lines_raw in sorted(files.items()):
        if not isinstance(path, str) or not isinstance(changed_lines_raw, list):
            continue
        service = service_for_path(path)
        if service is None:
            continue

        file_coverage = coverage_by_service.get(service, {}).get(path)
        changed_lines = {int(line) for line in changed_lines_raw}
        if file_coverage is None:
            rows.append(
                {
                    "service": service,
                    "path": path,
                    "changed": len(changed_lines),
                    "executable": 0,
                    "covered": 0,
                    "pct": None,
                    "note": "No coverage data for this file.",
                }
            )
            continue

        executable = changed_lines.intersection(file_coverage.executable_lines.keys())
        covered = {line for line in executable if file_coverage.executable_lines[line]}
        ignored_non_executable += len(changed_lines) - len(executable)
        total_counts.lines_total += len(executable)
        total_counts.lines_covered += len(covered)

        rows.append(
            {
                "service": service,
                "path": path,
                "changed": len(changed_lines),
                "executable": len(executable),
                "covered": len(covered),
                "pct": pct(len(covered), len(executable)),
                "note": "",
            }
        )

    return rows, total_counts, ignored_non_executable


def html_escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_metric_card(title: str, value: str, detail: str, klass: str = "") -> str:
    return f"""
        <article class="metric {klass}">
          <span>{html_escape(title)}</span>
          <strong>{html_escape(value)}</strong>
          <p>{html_escape(detail)}</p>
        </article>
    """


def render_html(
    coverage_dir: Path,
    service_configs: tuple[ServiceConfig, ...],
    coverage_by_service: dict[str, dict[str, FileCoverage]],
    changed_payload: dict[str, object],
) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M %z")
    service_totals = {
        config.name: aggregate(coverage_by_service.get(config.name, {}))
        for config in service_configs
    }
    changed_rows, changed_total, ignored_non_executable = changed_code_rows(
        changed_payload,
        coverage_by_service,
    )

    service_rows = []
    for config in service_configs:
        counts = service_totals[config.name]
        service_rows.append(
            f"""
            <tr>
              <td><a href="./{html_escape(config.html_dir)}/">{html_escape(config.label)}</a></td>
              <td><span class="pill {css_class(counts.total_pct)}">{fmt_pct(counts.total_pct)}</span></td>
              <td>{fmt_pct(counts.line_pct)} <span class="muted">({counts.lines_covered}/{counts.lines_total})</span></td>
              <td>{fmt_pct(counts.branch_pct)} <span class="muted">({counts.branches_covered}/{counts.branches_total})</span></td>
              <td>{fmt_pct(counts.function_pct)} <span class="muted">({counts.functions_covered}/{counts.functions_total})</span></td>
            </tr>
            """
        )

    domain_rows = []
    for config in service_configs:
        service_files = coverage_by_service.get(config.name, {})
        for domain in config.domains:
            counts = aggregate(service_files, domain.prefixes)
            if counts.lines_total == 0 and counts.branches_total == 0:
                continue
            domain_rows.append(
                f"""
                <tr>
                  <td>{html_escape(config.label)}</td>
                  <td>{html_escape(domain.name)}<div class="muted">{html_escape(domain.description)}</div></td>
                  <td><code>{html_escape(', '.join(domain.prefixes))}</code></td>
                  <td><span class="pill {css_class(counts.total_pct)}">{fmt_pct(counts.total_pct)}</span></td>
                  <td>{fmt_pct(counts.line_pct)} <span class="muted">({counts.lines_covered}/{counts.lines_total})</span></td>
                  <td>{fmt_pct(counts.branch_pct)} <span class="muted">({counts.branches_covered}/{counts.branches_total})</span></td>
                  <td>{fmt_pct(counts.function_pct)} <span class="muted">({counts.functions_covered}/{counts.functions_total})</span></td>
                </tr>
                """
            )

    changed_body: str
    changed_error = changed_payload.get("error")
    if changed_error:
        changed_body = f'<p class="notice bad-box">{html_escape(changed_error)}</p>'
    elif not changed_rows:
        changed_body = '<p class="notice">No changed production executable lines were detected for the configured diff.</p>'
    else:
        row_html = []
        for row in changed_rows:
            row_html.append(
                f"""
                <tr>
                  <td>{html_escape(row["service"])}</td>
                  <td><code>{html_escape(row["path"])}</code></td>
                  <td>{html_escape(row["changed"])}</td>
                  <td>{html_escape(row["executable"])}</td>
                  <td>{html_escape(row["covered"])}</td>
                  <td><span class="pill {css_class(row["pct"])}">{fmt_pct(row["pct"])}</span></td>
                  <td>{html_escape(row["note"])}</td>
                </tr>
                """
            )
        changed_body = f"""
          <table>
            <thead>
              <tr>
                <th>Service</th>
                <th>File</th>
                <th>Changed lines</th>
                <th>Executable changed lines</th>
                <th>Covered</th>
                <th>Coverage</th>
                <th>Note</th>
              </tr>
            </thead>
            <tbody>{''.join(row_html)}</tbody>
          </table>
        """

    changed_base = changed_payload.get("base") or "unknown"
    changed_generated_at = changed_payload.get("generated_at") or "not generated"
    changed_target = 80.0
    changed_pct = changed_total.line_pct

    raw_links = []
    for config in service_configs:
        if (coverage_dir / config.html_dir).exists():
            raw_links.append(f'<li><a href="./{html_escape(config.html_dir)}/">{html_escape(config.label)} raw HTML coverage</a></li>')
        else:
            raw_links.append(f'<li><span class="missing">{html_escape(config.label)} raw HTML coverage was not generated</span></li>')

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Coverage Overview</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #f6f7f9;
        --panel: #ffffff;
        --text: #172033;
        --muted: #667085;
        --line: #d9dee8;
        --blue: #0f4c81;
        --good: #047857;
        --warn: #a16207;
        --bad: #b42318;
      }}
      body {{ margin: 0; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); }}
      main {{ max-width: 1220px; margin: 36px auto 64px; padding: 0 24px; }}
      header {{ margin-bottom: 24px; }}
      h1 {{ margin: 0 0 8px; font-size: 34px; letter-spacing: 0; }}
      h2 {{ margin: 0 0 10px; font-size: 22px; letter-spacing: 0; }}
      p {{ color: var(--muted); line-height: 1.55; }}
      a {{ color: var(--blue); font-weight: 650; text-decoration: none; }}
      a:hover {{ text-decoration: underline; }}
      code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.92em; }}
      section {{ margin-top: 18px; padding: 22px; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; }}
      table {{ width: 100%; border-collapse: collapse; margin-top: 14px; font-size: 14px; }}
      th, td {{ padding: 10px 12px; border-bottom: 1px solid #edf0f5; text-align: left; vertical-align: top; }}
      th {{ color: #344054; background: #f9fafb; font-weight: 700; }}
      .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-top: 16px; }}
      .metric {{ padding: 16px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }}
      .metric span {{ display: block; color: var(--muted); font-size: 13px; font-weight: 650; }}
      .metric strong {{ display: block; margin-top: 6px; font-size: 30px; }}
      .metric p {{ margin: 6px 0 0; font-size: 13px; }}
      .pill {{ display: inline-block; min-width: 64px; padding: 3px 8px; border-radius: 999px; text-align: center; font-weight: 700; }}
      .good {{ color: var(--good); background: #ecfdf3; }}
      .warn {{ color: var(--warn); background: #fffaeb; }}
      .bad {{ color: var(--bad); background: #fef3f2; }}
      .unknown {{ color: #475467; background: #f2f4f7; }}
      .muted {{ color: var(--muted); font-size: 12px; }}
      .notice {{ padding: 12px 14px; border: 1px solid var(--line); border-radius: 8px; background: #f9fafb; }}
      .bad-box {{ border-color: #fecdca; background: #fef3f2; color: var(--bad); }}
      .links {{ display: grid; gap: 10px; padding: 0; list-style: none; }}
      .links a, .links span {{ display: block; padding: 14px 16px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }}
      .missing {{ color: var(--bad); }}
    </style>
  </head>
  <body>
    <main>
      <header>
        <h1>Coverage Overview</h1>
        <p>Generated at {html_escape(generated_at)}. This page is part of the Allure artifact and separates service-wide coverage, domain/module coverage, and changed-code coverage.</p>
      </header>

      <section>
        <h2>How To Read This</h2>
        <p><strong>Global service coverage</strong> is all measured production code included by the service coverage configuration. It is useful as a regression signal, but it does not prove that every domain is tested.</p>
        <p><strong>Domain/module coverage</strong> slices the same data by path prefix. This exposes cases where one heavily tested module, such as equity reports, makes the whole service number look healthier than the rest of the service.</p>
        <p><strong>Changed-code coverage</strong> checks executable lines added or modified in the current Git diff. The reporting target is {changed_target:.0f}% for PR-style review, but this page reports it only; it does not enforce a gate by itself.</p>
      </section>

      <section id="global-service-coverage">
        <h2>Global Service Coverage</h2>
        <div class="metrics">
          {render_metric_card("Stock service", fmt_pct(service_totals.get("stock", Counts()).total_pct), "All measured stock code.", css_class(service_totals.get("stock", Counts()).total_pct))}
          {render_metric_card("Wallet service", fmt_pct(service_totals.get("wallet", Counts()).total_pct), "All measured wallet code.", css_class(service_totals.get("wallet", Counts()).total_pct))}
          {render_metric_card("Session service", fmt_pct(service_totals.get("session", Counts()).total_pct), "All measured session code.", css_class(service_totals.get("session", Counts()).total_pct))}
          {render_metric_card("Next UI", fmt_pct(service_totals.get("next-ui", Counts()).total_pct), "Line plus branch signal from Vitest.", css_class(service_totals.get("next-ui", Counts()).total_pct))}
        </div>
        <table>
          <thead>
            <tr>
              <th>Service</th>
              <th>Total</th>
              <th>Line</th>
              <th>Branch</th>
              <th>Function</th>
            </tr>
          </thead>
          <tbody>{''.join(service_rows)}</tbody>
        </table>
      </section>

      <section id="domain-coverage">
        <h2>Domain / Module Coverage</h2>
        <table>
          <thead>
            <tr>
              <th>Service</th>
              <th>Domain</th>
              <th>Path scope</th>
              <th>Total</th>
              <th>Line</th>
              <th>Branch</th>
              <th>Function</th>
            </tr>
          </thead>
          <tbody>{''.join(domain_rows)}</tbody>
        </table>
      </section>

      <section id="changed-code-coverage">
        <h2>Changed-Code Coverage</h2>
        <div class="metrics">
          {render_metric_card("Changed-code target", f"{changed_target:.0f}%", "Desired PR review threshold.", "unknown")}
          {render_metric_card("Current changed-code coverage", fmt_pct(changed_pct), f"Diff base: {changed_base}", css_class(changed_pct))}
          {render_metric_card("Executable changed lines", f"{changed_total.lines_covered}/{changed_total.lines_total}", f"Ignored non-executable changed lines: {ignored_non_executable}", css_class(changed_pct))}
        </div>
        <p class="muted">Changed-code input generated at {html_escape(changed_generated_at)}.</p>
        {changed_body}
      </section>

      <section>
        <h2>Raw Coverage Reports</h2>
        <ul class="links">
          {''.join(raw_links)}
        </ul>
      </section>
    </main>
  </body>
</html>
"""


def service_configs(root: Path) -> tuple[ServiceConfig, ...]:
    return (
        ServiceConfig(
            name="stock",
            label="Stock",
            html_dir="stock",
            kind="python",
            coverage_path="stock/tests/artifacts/coverage.xml",
            source_prefix="stock/app",
            domains=(
                Domain("Equity reports", "Report builder, report metrics, LLM client, sanitizing, and web source parsing.", ("stock/app/reports/equity/",)),
                Domain("Market data importers", "Markerdata consent, parser, and historical browser code.", ("stock/app/markerdata/",)),
                Domain("API and quotes", "API-level stock service code and quote services.", ("stock/app/api/",)),
                Domain("External clients", "HTTP clients for market listings and upstream data.", ("stock/app/core/clients/",)),
                Domain("Core app and tasks", "Application wiring, context, Celery setup, and background quote tasks.", ("stock/app/core/app.py", "stock/app/core/context.py", "stock/app/core/celery_app.py", "stock/app/core/tasks/")),
                Domain("Persistence / CRUD", "Stock database CRUD helpers.", ("stock/app/crud/",)),
                Domain("Cache infrastructure", "Redis and cache storage helpers.", ("stock/app/core/cache/",)),
                Domain("Utilities and validators", "Reusable stock helper and validation code.", ("stock/app/utils/", "stock/app/validators/")),
            ),
        ),
        ServiceConfig(
            name="wallet",
            label="Wallet",
            html_dir="wallet",
            kind="python",
            coverage_path="wallet/tests/artifacts/coverage.xml",
            source_prefix="wallet/app",
            domains=(
                Domain("API routes", "Public wallet route handlers.", ("wallet/app/api/routes/",)),
                Domain("Domain services", "Wallet service layer and financial orchestration.", ("wallet/app/api/services/",)),
                Domain("Persistence / CRUD", "Wallet database CRUD helpers.", ("wallet/app/crud/",)),
                Domain("External clients", "Auth and stock service clients.", ("wallet/app/clients/",)),
                Domain("Core infrastructure", "Wallet core app wiring, cache, tasks, and shared exceptions.", ("wallet/app/core/",)),
                Domain("Utilities and validators", "Money, date, and validation helpers.", ("wallet/app/utils/", "wallet/app/validators/")),
            ),
        ),
        ServiceConfig(
            name="session",
            label="Session",
            html_dir="session",
            kind="python",
            coverage_path="session/tests/artifacts/coverage.xml",
            source_prefix="session",
            domains=(
                Domain("Auth and session core", "Authentication, HMAC, token, manager, throttle, and 2FA code.", ("session/userauth/authentication.py", "session/userauth/backends.py", "session/userauth/hmac_token.py", "session/userauth/managers.py", "session/userauth/throttles.py", "session/userauth/tokens.py", "session/userauth/two_factor.py")),
                Domain("Forms and validators", "Input validation, serializers, and forms.", ("session/userauth/forms.py", "session/userauth/serializers.py", "session/userauth/validators.py")),
                Domain("Views", "Session HTTP view behavior and health probes.", ("session/userauth/views.py", "session/userauth/views_health.py")),
                Domain("Middleware", "Session request, admin, and logging middleware.", ("session/middleware/",)),
                Domain("Utilities", "Shared session utility functions.", ("session/utils/",)),
            ),
        ),
        ServiceConfig(
            name="next-ui",
            label="Next UI",
            html_dir="next-ui",
            kind="lcov",
            coverage_path="next-ui/tests/artifacts/coverage-html/lcov.info",
            source_prefix="next-ui",
            domains=(
                Domain("Auth UI and actions", "Login/register pages and auth server actions.", ("next-ui/src/app/(auth)/", "next-ui/src/features/auth/")),
                Domain("Dashboard pages", "Protected application pages.", ("next-ui/src/app/(dashboard)/",)),
                Domain("API route proxies", "Next.js API routes that proxy backend services.", ("next-ui/src/app/api/",)),
                Domain("Wallet UI", "Wallet feature components and actions.", ("next-ui/src/features/wallet/",)),
                Domain("Reports UI", "Report page components, data, and types.", ("next-ui/src/features/reports/",)),
                Domain("Shared components", "Reusable UI and layout components.", ("next-ui/src/components/",)),
                Domain("Libraries and API clients", "Frontend helpers and typed API clients.", ("next-ui/src/lib/",)),
            ),
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="/workspace")
    parser.add_argument("--coverage-dir", default="/workspace/tests/artifacts/allure-report/coverage")
    parser.add_argument("--changed-lines", default="/workspace/tests/artifacts/coverage-changed-lines.json")
    args = parser.parse_args()

    root = Path(args.root)
    coverage_dir = Path(args.coverage_dir)
    coverage_dir.mkdir(parents=True, exist_ok=True)

    configs = service_configs(root)
    coverage_by_service: dict[str, dict[str, FileCoverage]] = {}
    for config in configs:
        coverage_path = root / config.coverage_path
        if config.kind == "python":
            files = parse_python_coverage(coverage_path, root, config.source_prefix)
            apply_python_function_coverage(
                files,
                coverage_path.parent / "coverage-html" / "function_index.html",
                config.source_prefix,
            )
            coverage_by_service[config.name] = files
        elif config.kind == "lcov":
            coverage_by_service[config.name] = parse_lcov(coverage_path, config.source_prefix)

    changed_payload = load_changed_lines(Path(args.changed_lines))
    html_text = render_html(coverage_dir, configs, coverage_by_service, changed_payload)
    (coverage_dir / "index.html").write_text(html_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
