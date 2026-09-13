#!/usr/bin/env python3
"""Read-only on-device launch triage for Cooking GO.

Requires the local MCP helper used by this workspace. The script launches the app once,
captures unified log entries, and flags dyld/library-validation failures that happen
before JS/bootstrap code can execute. It writes only to the host machine.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import threading
import time
from pathlib import Path
from typing import Any

DEFAULT_BUNDLE_ID = "com.airplanecooking.chef.kitchen.restaurant.diner"
PATTERN = re.compile(
    r"airplane|cooking|dyld|Library Validation failed|Library not loaded|image not found|"
    r"no suitable image|libswift|amfid|MIS|code signature|signature|posix_spawn|"
    r"RBSProcessExitStatus|processDidExit|launch failed|ProcessExited|Corpse failure|termination reported",
    re.I,
)


def load_mcp(path: str):
    spec = importlib.util.spec_from_file_location("mcp_helper", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load MCP helper: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def unwrap(resp: Any) -> Any:
    if not isinstance(resp, dict):
        return resp
    result = resp.get("result", {})
    if isinstance(result, dict) and result.get("structuredContent") is not None:
        return result["structuredContent"]
    if isinstance(result, dict):
        text = "\n".join(
            item.get("text", "") for item in result.get("content", [])
            if isinstance(item, dict)
        )
        if text:
            try:
                return json.loads(text)
            except Exception:
                return text
    return resp


def call(mcp: Any, name: str, args: dict[str, Any]) -> Any:
    return unwrap(mcp.call(name, args))


def run_cmd(mcp: Any, command: str) -> dict[str, Any]:
    r = call(mcp, "run_command", {"command": command})
    if isinstance(r, dict):
        return r
    return {"exitCode": None, "output": str(r)}


def sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mcp", required=True, help="path to mcp.py")
    ap.add_argument("--bundle-id", default=DEFAULT_BUNDLE_ID)
    ap.add_argument("--seconds", type=int, default=25)
    ap.add_argument("--max-lines", type=int, default=20000)
    ap.add_argument("--out", default="")
    ns = ap.parse_args()

    mcp = load_mcp(ns.mcp)
    report: dict[str, Any] = {"bundle_id": ns.bundle_id}

    info = call(mcp, "get_app_info", {"bundle_id": ns.bundle_id})
    report["app_info"] = info
    bundle = info.get("bundle_path") if isinstance(info, dict) else None
    exe = info.get("executable_path") if isinstance(info, dict) else None

    report["system_version"] = run_cmd(
        mcp,
        "/usr/bin/plutil -p /System/Library/CoreServices/SystemVersion.plist 2>/dev/null "
        "|| cat /System/Library/CoreServices/SystemVersion.plist",
    )

    if bundle and exe:
        jsc = f"{bundle}/assets/scriptBundle/index.jsc"
        report["bundle_static"] = run_cmd(
            mcp,
            "set -e; "
            f"ls -ld {sh_quote(bundle)} {sh_quote(bundle + '/Frameworks')} {sh_quote(jsc)} 2>&1; "
            f"sha256sum {sh_quote(jsc)} 2>/dev/null || shasum -a 256 {sh_quote(jsc)} 2>/dev/null; "
            f"ls -ld {sh_quote(bundle + '/_CodeSignature')} {sh_quote(bundle + '/_CodeSignature/CodeResources')} {sh_quote(bundle + '/embedded.mobileprovision')} 2>&1 || true",
        )
        report["main_ldid_header"] = run_cmd(mcp, f"ldid -h {sh_quote(exe)} 2>&1 | head -80")

    box: dict[str, Any] = {}

    def capture() -> None:
        box["syslog"] = call(mcp, "get_syslog", {"last_seconds": ns.seconds, "max_lines": ns.max_lines})

    t = threading.Thread(target=capture)
    t.start()
    time.sleep(1)
    report["launch_result"] = call(mcp, "launch_app", {"bundle_id": ns.bundle_id})
    t.join()

    syslog = box.get("syslog", {})
    entries = syslog.get("entries", []) if isinstance(syslog, dict) else []
    filtered: list[str] = []
    rejected_paths: list[str] = []
    for e in entries:
        line = f"{e.get('date','')} {e.get('process','')} {e.get('subsystem','')} {e.get('category','')} {e.get('level','')} | {e.get('message','')}"
        if PATTERN.search(line):
            filtered.append(line)
            m = re.search(r"Rejecting '([^']+)'", line)
            if m and m.group(1) not in rejected_paths:
                rejected_paths.append(m.group(1))
    report["syslog_total_entries"] = len(entries)
    report["filtered_log_lines"] = filtered
    report["rejected_library_paths"] = rejected_paths
    if rejected_paths:
        report["first_rejected_ldid_header"] = run_cmd(mcp, f"ldid -h {sh_quote(rejected_paths[0])} 2>&1 | head -80")

    report["verdict"] = {
        "has_library_validation_failure": any("Library Validation failed" in x for x in filtered),
        "has_dyld_exit": any("domain:dyld(6) code:1" in x or "namespace=6 code=1" in x for x in filtered),
        "first_rejected_library": rejected_paths[0] if rejected_paths else None,
    }

    text_lines = [
        f"bundle_id: {ns.bundle_id}",
        f"bundle_path: {bundle}",
        f"executable_path: {exe}",
        f"launch_result: {report['launch_result']}",
        f"syslog entries: {len(entries)} filtered: {len(filtered)}",
        f"verdict: {json.dumps(report['verdict'], ensure_ascii=False)}",
        "",
        "-- system_version --",
        report["system_version"].get("output", ""),
        "-- bundle_static --",
        report.get("bundle_static", {}).get("output", ""),
        "-- main ldid -h --",
        report.get("main_ldid_header", {}).get("output", ""),
    ]
    if rejected_paths:
        text_lines += ["-- first rejected ldid -h --", report.get("first_rejected_ldid_header", {}).get("output", "")]
    text_lines += ["-- filtered launch log --", *filtered]
    text = "\n".join(text_lines)

    if ns.out:
        out = Path(ns.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(out)
    print(text)
    return 0 if report["verdict"]["has_library_validation_failure"] or report["verdict"]["has_dyld_exit"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
