#!/usr/bin/env python3
"""Live-device ad-hoc re-sign helper for Cooking GO 1.26.02.

This is a lab fallback for the observed 1.26.02 dyld/library-validation gate:
the installed main executable is ad-hoc/TeamIdentifier empty while embedded
frameworks retain App Store team signatures. The helper signs framework binaries
first, then the main executable, using the MCP root helper's mcp-ldid allow-list.

It does not modify scripts, resources, or the mod DEB.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import time
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DEFAULT_BUNDLE_ID = "com.airplanecooking.chef.kitchen.restaurant.diner"


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
        text = "\n".join(item.get("text", "") for item in result.get("content", []) if isinstance(item, dict))
        if text:
            try:
                return json.loads(text)
            except Exception:
                return text
    return resp


def call(mcp: Any, name: str, args: dict[str, Any] | None = None) -> Any:
    return unwrap(mcp.call(name, args or {}))


def sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def run_cmd(mcp: Any, command: str, timeout: int = 60) -> dict[str, Any]:
    r = call(mcp, "run_command", {"command": command, "timeout": timeout})
    return r if isinstance(r, dict) else {"exitCode": None, "output": str(r)}


def list_code_paths(mcp: Any, app_path: str, exe_path: str) -> list[str]:
    script = f'''
app={sh_quote(app_path)}
for fw in "$app"/Frameworks/*.framework; do
  [ -d "$fw" ] || continue
  n=${{fw##*/}}
  n=${{n%.framework}}
  f="$fw/$n"
  [ -f "$f" ] || continue
  /var/jb/usr/bin/mcp-ldid -h "$f" 2>/dev/null | grep '^Executable=' >/dev/null && printf '%s\\n' "$f"
done
find "$app" -type f -name '*.dylib' -print 2>/dev/null
printf '%s\\n' {sh_quote(exe_path)}
'''
    out = run_cmd(mcp, script, 90)
    if out.get("exitCode") not in (0, None):
        raise SystemExit(f"failed to list code paths: {out}")
    paths: list[str] = []
    seen: set[str] = set()
    for line in str(out.get("output", "")).splitlines():
        line = line.strip()
        if line.startswith("/") and line not in seen:
            seen.add(line)
            paths.append(line)
    return paths


def summarize_signatures(mcp: Any, paths: list[str]) -> dict[str, Any]:
    rows = []
    for p in paths:
        r = run_cmd(mcp, f"/var/jb/usr/bin/mcp-ldid -h {sh_quote(p)} 2>&1", 30)
        text = str(r.get("output", ""))
        rows.append({
            "path": p,
            "exitCode": r.get("exitCode"),
            "identifier": (re.search(r"(?m)^Identifier=(.*)$", text) or [None, ""])[1],
            "team_id": (re.search(r"(?m)^TeamIdentifier=(.*)$", text) or [None, ""])[1],
            "cdhash": (re.search(r"(?m)^CDHash=(.*)$", text) or [None, ""])[1],
        })
    teams = sorted({x["team_id"] for x in rows if x.get("team_id")})
    return {"count": len(rows), "team_ids": teams, "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mcp", required=True)
    ap.add_argument("--bundle-id", default=DEFAULT_BUNDLE_ID)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default="")
    ns = ap.parse_args()

    mcp = load_mcp(ns.mcp)
    report: dict[str, Any] = {"bundle_id": ns.bundle_id, "dry_run": ns.dry_run, "steps": []}
    call(mcp, "wake_and_home", {"sequence": "auto"})
    app = call(mcp, "get_app_info", {"bundle_id": ns.bundle_id})
    report["app_info"] = app
    app_path = app.get("bundle_path") if isinstance(app, dict) else ""
    exe_path = app.get("executable_path") if isinstance(app, dict) else ""
    if not app_path or not exe_path:
        raise SystemExit(f"app not installed or app_info incomplete: {app}")

    call(mcp, "kill_app", {"bundle_id": ns.bundle_id})
    time.sleep(1)
    paths = list_code_paths(mcp, app_path, exe_path)
    report["code_paths"] = paths
    report["before"] = summarize_signatures(mcp, paths[:2] + paths[-1:])

    if not ns.dry_run:
        for p in paths:
            r = run_cmd(mcp, f"/var/jb/usr/bin/mcp-root /usr/bin/mcp-ldid -S {sh_quote(p)} 2>&1", 60)
            report["steps"].append({"sign": p, "exitCode": r.get("exitCode"), "output": str(r.get("output", ""))[-400:]})
            if r.get("exitCode") != 0:
                report["after_partial"] = summarize_signatures(mcp, paths[:2] + paths[-1:])
                raise SystemExit(json.dumps(report, ensure_ascii=False, indent=2))
        report["after"] = summarize_signatures(mcp, paths[:2] + paths[-1:])

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if ns.out:
        from pathlib import Path
        out = Path(ns.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"report: {out}")
    print(f"code paths: {len(paths)}")
    if report.get("after"):
        print(f"after team ids: {report['after'].get('team_ids')}")
    if not ns.out:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())