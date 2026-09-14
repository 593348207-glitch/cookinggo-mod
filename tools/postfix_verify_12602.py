#!/usr/bin/env python3
"""Post-signing-fix device verifier for Cooking GO 1.26.02 + CookingGoMod.

Workflow:
1. optionally install a repaired/resigned IPA;
2. verify the base game launches without dyld/library-validation failure;
3. optionally install the DEB;
4. verify tweak default config keeps rt=0;
5. optionally switch rt=1 and verify the runtime evalString scaffold.

The script is conservative: it will not install the DEB or enable rt=1 unless the
base game launch gate passes.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DEFAULT_BUNDLE_ID = "com.airplanecooking.chef.kitchen.restaurant.diner"
DEFAULT_PACKAGE_ID = "com.seagull.cookinggomod"
DEFAULT_CFG_PATH = "/var/jb/usr/lib/TweakInject/CookingGoMod.cfg"
LOG_PATTERN = re.compile(
    r"airplane|cooking|dyld|Library Validation failed|Library not loaded|image not found|"
    r"no suitable image|libswift|amfid|MIS|code signature|posix_spawn|"
    r"RBSProcessExitStatus|processDidExit|launch failed|ProcessExited|Corpse failure|termination reported|"
    r"CookingGoMod|evalString|js_hello|bootstrap",
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


def call(mcp: Any, name: str, args: dict[str, Any] | None = None) -> Any:
    return unwrap(mcp.call(name, args or {}))


def server_root(mcp: Any) -> str:
    base = getattr(mcp, "BASE", "")
    if base.endswith("/mcp"):
        return base[:-4]
    return base.rstrip("/")


def upload_local_file(mcp: Any, path: str) -> str:
    if path.startswith("/"):
        return path
    local = Path(path)
    if not local.is_file():
        raise SystemExit(f"local file not found: {path}")
    url = server_root(mcp) + "/upload_file"
    req = urllib.request.Request(
        url,
        data=local.read_bytes(),
        headers={"X-Filename": local.name, "Content-Type": "application/octet-stream"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        body = r.read().decode("utf-8", "replace")
    try:
        obj = json.loads(body)
        for key in ("path", "device_path", "file", "uploaded_path"):
            if obj.get(key):
                return obj[key]
    except Exception:
        pass
    m = re.search(r"(/var/[^\s\"']+)", body)
    if m:
        return m.group(1)
    raise SystemExit(f"upload response did not contain device path: {body[:300]}")


def line_for_entry(e: dict[str, Any]) -> str:
    return f"{e.get('date','')} {e.get('process','')} {e.get('subsystem','')} {e.get('category','')} {e.get('level','')} | {e.get('message','')}"


def capture_launch(mcp: Any, bundle_id: str, seconds: int, max_lines: int) -> dict[str, Any]:
    box: dict[str, Any] = {}

    def cap() -> None:
        box["syslog"] = call(mcp, "get_syslog", {"last_seconds": seconds, "max_lines": max_lines})

    t = threading.Thread(target=cap)
    t.start()
    time.sleep(1)
    launch_result = call(mcp, "launch_app", {"bundle_id": bundle_id})
    t.join()
    syslog = box.get("syslog", {})
    entries = syslog.get("entries", []) if isinstance(syslog, dict) else []
    filtered = [line_for_entry(e) for e in entries if LOG_PATTERN.search(line_for_entry(e))]
    lv_lines = [x for x in filtered if "Library Validation failed" in x]
    dyld_lines = [x for x in filtered if "domain:dyld(6) code:1" in x or "namespace=6 code=1" in x]
    exited_lines = [x for x in filtered if "ProcessExited" in x or "processDidExit" in x or "termination reported" in x]
    return {
        "launch_result": launch_result,
        "syslog_total_entries": len(entries),
        "filtered_log_lines": filtered,
        "library_validation_lines": lv_lines,
        "dyld_exit_lines": dyld_lines,
        "process_exit_lines": exited_lines,
        "has_library_validation_failure": bool(lv_lines),
        "has_dyld_exit": bool(dyld_lines),
    }


def sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def run_cmd(mcp: Any, command: str, timeout: int = 10) -> dict[str, Any]:
    r = call(mcp, "run_command", {"command": command, "timeout": timeout})
    return r if isinstance(r, dict) else {"exitCode": None, "output": str(r)}


def result_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def install_result_failed(value: Any) -> bool:
    text = result_text(value).lower()
    return any(token in text for token in ("install failed", "sudo:", "incorrect password", "error"))


def read_device_file(mcp: Any, path: str, max_bytes: int = 262144) -> str:
    r = call(mcp, "read_file", {"path": path, "max_bytes": max_bytes})
    if isinstance(r, dict):
        return r.get("content") or r.get("text") or r.get("output") or json.dumps(r, ensure_ascii=False)
    return str(r)


def write_device_file(mcp: Any, path: str, content: str) -> Any:
    result = call(mcp, "write_file", {"path": path, "content": content, "encoding": "utf8"})
    try:
        if read_device_file(mcp, path, max(len(content) + 64, 4096)) == content:
            return result
    except Exception:
        pass

    # Some MCP write_file implementations use a same-directory temporary file.
    # /var/jb/usr/lib/TweakInject is root-owned, while CookingGoMod.cfg is made
    # world-writable for lab toggles; direct shell redirection can still update
    # the existing file without directory write permission.
    marker = "CGM_CFG_EOF"
    expected = content if content.endswith("\n") else content + "\n"
    while marker in expected:
        marker += "_X"
    cmd = f"cat > {sh_quote(path)} <<'{marker}'\n{expected}{marker}\n"
    fallback = run_cmd(mcp, cmd, 10)
    actual = read_device_file(mcp, path, max(len(expected) + 64, 4096))
    if actual != expected:
        raise SystemExit(
            "failed to update device file "
            f"{path}: fallback={fallback!r} actual_tail={actual[-200:]!r}"
        )
    return fallback


def set_rt_in_cfg(mcp: Any, cfg_path: str, enabled: bool) -> str:
    try:
        cfg = read_device_file(mcp, cfg_path)
    except Exception:
        cfg = ""
    if not cfg or cfg.startswith("{") and "No such" in cfg:
        cfg = "objc=1\nposix=0\noverlay=1\npanel=0\nrot=0\nvlog=0\niap=0\nrt=0\n"
    if re.search(r"(?m)^rt\s*=", cfg):
        cfg = re.sub(r"(?m)^rt\s*=\s*[01].*$", f"rt={1 if enabled else 0}", cfg)
    else:
        cfg = cfg.rstrip() + f"\nrt={1 if enabled else 0}\n"
    write_device_file(mcp, cfg_path, cfg)
    return cfg


def mailbox_path(app_info: dict[str, Any]) -> str:
    data = app_info.get("data_container") or ""
    return data.rstrip("/") + "/Documents/cookingmod"


def discover_mailbox_paths(mcp: Any, app_info: dict[str, Any]) -> list[str]:
    cands: list[str] = []
    primary = mailbox_path(app_info)

    # Re-signed/ad-hoc lab installs may leave MobileContainerManager metadata
    # under the bundle id while NSHomeDirectory() resolves to the executable id
    # container. Prefer all existing cookingmod mailboxes, newest mod.log first.
    cmd = r"""
find /var/mobile/Containers/Data/Application -path '*/Documents/cookingmod' -type d -print 2>/dev/null | while read d; do
  ts=0
  [ -f "$d/mod.log" ] && ts=$(stat -f '%m' "$d/mod.log" 2>/dev/null || stat -c '%Y' "$d/mod.log" 2>/dev/null || echo 0)
  printf '%s	%s
' "$ts" "$d"
done | sort -nr | cut -f2-
""".strip()
    r = run_cmd(mcp, cmd, 20)
    for line in str(r.get("output", "")).splitlines():
        line = line.strip()
        if line.startswith("/") and line not in cands:
            cands.append(line)
    if primary and primary != "/Documents/cookingmod" and primary not in cands:
        cands.append(primary)
    return cands


def active_mailbox_path(mcp: Any, app_info: dict[str, Any]) -> str:
    paths = discover_mailbox_paths(mcp, app_info)
    return paths[0] if paths else mailbox_path(app_info)


def package_installed(mcp: Any, package_id: str) -> bool:
    # `dpkg -s` also exits 0 for a package left in `deinstall ok config-files`
    # state. Require the exact installed status so a removed tweak does not
    # trigger the rt=0 gate merely because dpkg retained its config files.
    r = run_cmd(
        mcp,
        f"dpkg-query -W -f='${{Status}}\n' {sh_quote(package_id)} 2>/dev/null || true",
        10,
    )
    return bool(re.search(r"(?m)^install ok installed\s*$", str(r.get("output", ""))))


def clear_tweak_runtime_files(mcp: Any, app_info: dict[str, Any]) -> dict[str, Any]:
    names = "mod.log js_hello.json probe.json state.json res.json cmd.json ui_cmd.json ui_state.json hits.json"
    cleared = []
    for mb in discover_mailbox_paths(mcp, app_info):
        if not mb or mb == "/Documents/cookingmod":
            continue
        r = run_cmd(mcp, f"cd {sh_quote(mb)} 2>/dev/null && rm -f {names} 2>/dev/null || true", 10)
        cleared.append({"mailbox": mb, "result": r})
    return {"cleared": cleared} if cleared else {"skipped": "no mailbox paths found"}


def file_output(text: Any) -> dict[str, Any]:
    if isinstance(text, dict):
        if text.get("blocked"):
            return {"exitCode": 1, "output": json.dumps(text, ensure_ascii=False)}
        if "content" in text:
            text = text.get("content")
        elif "output" in text:
            text = text.get("output")
    s = "" if text is None else str(text)
    if "No such file or directory" in s or "Operation not permitted" in s:
        return {"exitCode": 0, "output": ""}
    return {"exitCode": 0, "output": s}


def collect_tweak_state(mcp: Any, app_info: dict[str, Any], cfg_path: str) -> dict[str, Any]:
    # Mailbox lives in the app container. Unprivileged `run_command`/`tail`
    # gets Operation not permitted and produces false-negative rt0/rt1 gates.
    # Prefer MCP read_file/list_dir, which fall back to the privileged helper.
    box = {"cfg": file_output(read_device_file(mcp, cfg_path))}
    mb = mailbox_path(app_info)
    paths = [mb] if mb and mb != "/Documents/cookingmod" else []
    try:
        for extra in discover_mailbox_paths(mcp, app_info):
            if extra not in paths:
                paths.append(extra)
    except Exception:
        pass
    if not paths:
        paths = [mb]
    mb = paths[0]
    box["mailbox"] = mb
    box["mailbox_candidates"] = paths
    listing = call(mcp, "list_dir", {"path": mb})
    box["mailbox_ls"] = file_output(json.dumps(listing, ensure_ascii=False))
    for name in ["mod.log", "js_hello.json", "probe.json", "state.json", "iap_hook.json"]:
        box[name] = file_output(read_device_file(mcp, f"{mb}/{name}"))
    return box


def verdict_base(launch: dict[str, Any]) -> tuple[bool, str]:
    if launch["has_library_validation_failure"] or launch["has_dyld_exit"]:
        return False, "base launch failed dyld/library-validation gate"
    if isinstance(launch["launch_result"], str) and "Failed:" in launch["launch_result"]:
        return False, "base launch did not become frontmost; no dyld signature failure seen, inspect logs"
    return True, "base launch gate passed"


def verdict_rt(state: dict[str, Any], enabled: bool) -> tuple[bool, str]:
    modlog = state.get("mod.log", {}).get("output", "") if isinstance(state.get("mod.log"), dict) else ""
    jshello = state.get("js_hello.json", {}).get("output", "") if isinstance(state.get("js_hello.json"), dict) else ""
    loaded = re.search(r"CookingGoMod v[0-9][^\n]* loaded", modlog) is not None
    if not loaded:
        return False, "fresh tweak load marker not observed"
    if not enabled:
        if "rt=0" in state.get("cfg", {}).get("output", ""):
            return True, "tweak default rt=0 verified"
        return False, "rt=0 not visible in packaged/device cfg"
    if "runtime evalString hook installed" not in modlog:
        return False, "rt=1 enabled but runtime evalString hook install marker not found"
    if "runtime evalString bootstrap OK" in modlog or jshello.strip():
        return True, "rt=1 runtime hook marker observed"
    return False, "rt=1 hook installed but JS handshake not observed yet"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mcp", required=True, help="path to workspace mcp.py")
    ap.add_argument("--bundle-id", default=DEFAULT_BUNDLE_ID)
    ap.add_argument("--package-id", default=DEFAULT_PACKAGE_ID)
    ap.add_argument("--cfg-path", default=DEFAULT_CFG_PATH)
    ap.add_argument("--install-ipa", default="", help="optional local/device path to repaired IPA")
    ap.add_argument("--install-deb", default="", help="optional local/device path to v1.3.4 DEB")
    ap.add_argument("--remove-tweak-first", action="store_true")
    ap.add_argument("--enable-rt", action="store_true", help="after rt=0 smoke test, set rt=1 and launch again")
    ap.add_argument("--seconds", type=int, default=25)
    ap.add_argument("--max-lines", type=int, default=5000)
    ap.add_argument("--out", default="")
    ap.add_argument("--print-json", action="store_true", help="print the full JSON report even when --out is used")
    ap.add_argument("--keep-mailbox", action="store_true", help="do not remove stale runtime marker files before tweak gates")
    ns = ap.parse_args()

    mcp = load_mcp(ns.mcp)
    report: dict[str, Any] = {
        "bundle_id": ns.bundle_id,
        "package_id": ns.package_id,
        "install_ipa": ns.install_ipa,
        "install_deb": ns.install_deb,
        "enable_rt": ns.enable_rt,
        "steps": [],
    }

    call(mcp, "wake_and_home", {"sequence": "auto"})

    if ns.remove_tweak_first:
        report["steps"].append({"remove_tweak_first": call(mcp, "uninstall_app", {"package_id": ns.package_id})})
        time.sleep(5)
        call(mcp, "wake_and_home", {"sequence": "auto"})

    if ns.install_ipa:
        device_ipa = upload_local_file(mcp, ns.install_ipa)
        report["steps"].append({"uploaded_ipa": device_ipa})
        report["steps"].append({"install_ipa_result": call(mcp, "install_app", {"path": device_ipa})})
        time.sleep(8)
        call(mcp, "wake_and_home", {"sequence": "auto"})

    app_info = call(mcp, "get_app_info", {"bundle_id": ns.bundle_id})
    report["app_info_before_base_launch"] = app_info
    call(mcp, "kill_app", {"bundle_id": ns.bundle_id})
    time.sleep(1)
    base_launch = capture_launch(mcp, ns.bundle_id, ns.seconds, ns.max_lines)
    report["base_launch"] = base_launch
    base_ok, base_msg = verdict_base(base_launch)
    report["base_gate"] = {"ok": base_ok, "message": base_msg}

    if not base_ok:
        report["final"] = "STOP: base game launch gate failed; DEB install/rt enable skipped"
        code = 2
    else:
        code = 0
        install_deb_failed = False
        if ns.install_deb:
            device_deb = upload_local_file(mcp, ns.install_deb)
            report["steps"].append({"uploaded_deb": device_deb})
            install_result = call(mcp, "install_app", {"path": device_deb})
            install_deb_failed = install_result_failed(install_result)
            report["steps"].append({"install_deb_result": install_result})
            time.sleep(8)
            call(mcp, "wake_and_home", {"sequence": "auto"})

        app_info_after = call(mcp, "get_app_info", {"bundle_id": ns.bundle_id})
        report["app_info_after_deb"] = app_info_after
        installed = package_installed(mcp, ns.package_id)
        report["package_installed"] = installed
        report["package_install_status"] = {
            "requested": bool(ns.install_deb),
            "install_attempt_failed": install_deb_failed,
            "package_present_after_attempt": installed,
            "reused_existing_package": bool(ns.install_deb and install_deb_failed and installed),
        }

        if ns.install_deb and install_deb_failed and not installed:
            report["final"] = "STOP: requested DEB install failed and package is not installed"
            code = 3
        elif not installed and not ns.install_deb:
            report["final"] = "PASS: base launch gate passed; DEB not installed/requested, tweak gates skipped"
        else:
            # rt=0 default smoke. Only write cfg after DEB is known/requested present.
            set_rt_in_cfg(mcp, ns.cfg_path, False)
            report["rt0_cfg_written"] = True
            if not ns.keep_mailbox:
                report["rt0_clear_runtime_files"] = clear_tweak_runtime_files(mcp, app_info_after)
            call(mcp, "kill_app", {"bundle_id": ns.bundle_id})
            time.sleep(1)
            rt0_launch = capture_launch(mcp, ns.bundle_id, ns.seconds, ns.max_lines)
            report["rt0_launch"] = rt0_launch
            rt0_state = collect_tweak_state(mcp, app_info_after, ns.cfg_path)
            report["rt0_state"] = rt0_state
            rt0_ok, rt0_msg = verdict_rt(rt0_state, False)
            report["rt0_gate"] = {"ok": rt0_ok, "message": rt0_msg}
            if not rt0_ok or rt0_launch["has_library_validation_failure"] or rt0_launch["has_dyld_exit"]:
                code = 3
                report["final"] = "STOP: rt=0 tweak smoke gate failed; rt=1 skipped"
            elif ns.enable_rt:
                set_rt_in_cfg(mcp, ns.cfg_path, True)
                report["rt1_cfg_written"] = True
                if not ns.keep_mailbox:
                    report["rt1_clear_runtime_files"] = clear_tweak_runtime_files(mcp, app_info_after)
                call(mcp, "kill_app", {"bundle_id": ns.bundle_id})
                time.sleep(1)
                rt1_launch = capture_launch(mcp, ns.bundle_id, ns.seconds, ns.max_lines)
                report["rt1_launch"] = rt1_launch
                rt1_state = collect_tweak_state(mcp, app_info_after, ns.cfg_path)
                report["rt1_state"] = rt1_state
                rt1_ok, rt1_msg = verdict_rt(rt1_state, True)
                report["rt1_gate"] = {"ok": rt1_ok, "message": rt1_msg}
                if not rt1_ok or rt1_launch["has_library_validation_failure"] or rt1_launch["has_dyld_exit"]:
                    code = 4
                    report["final"] = "rt=1 runtime hook needs attention"
                else:
                    if install_deb_failed:
                        report["final"] = "PASS: runtime gates passed using existing installed package; requested DEB install failed"
                    else:
                        report["final"] = "PASS: base + DEB + rt=1 runtime hook gates passed"
            else:
                report["final"] = "PASS: base + rt=0 gates passed; rt=1 not requested"

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if ns.out:
        out = Path(ns.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"report: {out}")
    print(f"base_gate: {report.get('base_gate')}")
    if 'rt0_gate' in report:
        print(f"rt0_gate: {report.get('rt0_gate')}")
    if 'rt1_gate' in report:
        print(f"rt1_gate: {report.get('rt1_gate')}")
    print(f"final: {report.get('final')}")
    for key in ("base_launch", "rt0_launch", "rt1_launch"):
        launch = report.get(key)
        if isinstance(launch, dict):
            print(f"{key}: lv={len(launch.get('library_validation_lines', []))} dyld={len(launch.get('dyld_exit_lines', []))} exit={len(launch.get('process_exit_lines', []))} filtered={len(launch.get('filtered_log_lines', []))}")
    if ns.print_json or not ns.out:
        print(text)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
