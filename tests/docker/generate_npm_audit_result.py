"""
Converts npm audit --json output into an Allure result JSON file.

Passes when there are no high or critical vulnerabilities.
Fails  when high or critical vulnerabilities are found.
Broken when the audit file is missing or malformed.
Always attaches the full audit summary as a text attachment.
"""
from __future__ import annotations

import json
import time
import uuid
import argparse
from pathlib import Path


SEVERITY_ORDER = ["critical", "high", "moderate", "low", "info"]


def _status(meta: dict) -> str:
    vulns = meta.get("vulnerabilities", {})
    if vulns.get("critical", 0) > 0 or vulns.get("high", 0) > 0:
        return "failed"
    return "passed"


def _summary_text(meta: dict, vulnerabilities: dict) -> str:
    vulns = meta.get("vulnerabilities", {})
    lines = ["npm audit summary", "=" * 40]
    for sev in SEVERITY_ORDER:
        count = vulns.get(sev, 0)
        if count:
            lines.append(f"  {sev.upper():10s} {count}")
    lines.append(f"  {'TOTAL':10s} {vulns.get('total', 0)}")
    if vulnerabilities:
        lines += ["", "Affected packages:", "-" * 40]
        for name, info in vulnerabilities.items():
            severity = info.get("severity", "unknown")
            via = [
                v.get("title", v) if isinstance(v, dict) else str(v)
                for v in info.get("via", [])
            ]
            lines.append(f"  [{severity.upper()}] {name}: {', '.join(via[:3])}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-json", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    audit_path = Path(args.audit_json)
    now_ms = int(time.time() * 1000)

    if not audit_path.exists():
        status = "broken"
        summary = "npm audit file not found — npm install may have been skipped."
        meta: dict = {}
        vulnerabilities: dict = {}
    else:
        try:
            data = json.loads(audit_path.read_text())
            meta = data.get("metadata", {})
            vulnerabilities = data.get("vulnerabilities", {})
            status = _status(meta)
            summary = _summary_text(meta, vulnerabilities)
        except Exception as exc:
            status = "broken"
            summary = f"Failed to parse npm audit output: {exc}"
            meta = {}
            vulnerabilities = {}

    attachment_uid = str(uuid.uuid4())
    attachment_file = output_dir / f"{attachment_uid}-attachment"
    attachment_file.write_text(summary, encoding="utf-8")

    result_uid = str(uuid.uuid4())
    result = {
        "uuid": result_uid,
        "historyId": "npm-audit-next-ui",
        "name": "npm audit: next-ui has no high or critical vulnerabilities",
        "status": status,
        "stage": "finished",
        "start": now_ms,
        "stop": now_ms + 1,
        "attachments": [
            {
                "name": "npm audit report",
                "source": f"{attachment_uid}-attachment",
                "type": "text/plain",
            }
        ],
        "labels": [
            {"name": "epic", "value": "Security"},
            {"name": "feature", "value": "Dependency Audit"},
            {"name": "story", "value": "next-ui dependencies have no high or critical vulnerabilities"},
            {"name": "severity", "value": "critical"},
            {"name": "suite", "value": "next-ui"},
        ],
    }

    result_file = output_dir / f"{result_uid}-result.json"
    result_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"npm audit result: {status} → {result_file.name}")


if __name__ == "__main__":
    main()
