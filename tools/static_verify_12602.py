#!/usr/bin/env python3
"""Static closure check for Cooking GO 1.26.02 and the packaged tweak.
No device writes, app launch, or purchase operations are performed.
"""
from __future__ import annotations
import argparse, gzip, hashlib, io, plistlib, re, struct, tarfile, zipfile, zlib
from pathlib import Path

DELTA = 0x9E3779B9
KEY = b"75fa5f0d-2c43-45"
ORIG_JSC_SHA = "cb1825d4c535f77de8cafbec1d4b73e65d10f43835d04cb091c856b4967269d0"


def words(data: bytes):
    if len(data) % 4:
        data += b"\0" * (4 - len(data) % 4)
    return list(struct.unpack("<%dI" % (len(data) // 4), data))


def xxtea_decrypt(data: bytes, key: bytes) -> bytes:
    n = len(data) // 4
    v = list(struct.unpack("<%dI" % n, data[: n * 4]))
    k = list(struct.unpack("<4I", key[:16].ljust(16, b"\0")))
    q = 6 + 52 // n
    total = (q * DELTA) & 0xFFFFFFFF
    y = v[0]
    while total:
        e = (total >> 2) & 3
        for p in range(n - 1, 0, -1):
            z = v[p - 1]
            mx = (((z >> 5) ^ ((y << 2) & 0xFFFFFFFF)) + ((y >> 3) ^ ((z << 4) & 0xFFFFFFFF))) ^ ((total ^ y) + (k[(p & 3) ^ e] ^ z))
            v[p] = (v[p] - mx) & 0xFFFFFFFF
            y = v[p]
        z = v[n - 1]
        mx = (((z >> 5) ^ ((y << 2) & 0xFFFFFFFF)) + ((y >> 3) ^ ((z << 4) & 0xFFFFFFFF))) ^ ((total ^ y) + (k[e] ^ z))
        v[0] = (v[0] - mx) & 0xFFFFFFFF
        y = v[0]
        total = (total - DELTA) & 0xFFFFFFFF
    return struct.pack("<%dI" % n, *v)


def gunzip(data: bytes) -> bytes:
    obj = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = obj.decompress(data)
    assert obj.eof, "decrypted JSC is not a complete gzip stream"
    return out


def parse_deb(raw: bytes) -> dict[str, bytes]:
    assert raw[:8] == b"!<arch>\n"
    off = 8
    members: dict[str, bytes] = {}
    while off + 60 <= len(raw):
        hdr = raw[off:off + 60]
        name = hdr[:16].decode("ascii", "replace").strip().rstrip("/")
        size = int(hdr[48:58].decode("ascii", "replace").strip())
        body = raw[off + 60:off + 60 + size]
        members[name] = body
        off += 60 + size + (size & 1)
    assert "data.tar.gz" in members and "control.tar.gz" in members
    return members


def tar_members(tar_gz: bytes) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(tar_gz), mode="r:gz") as t:
        for m in t.getmembers():
            key = m.name.lstrip("./")
            if m.isfile():
                f = t.extractfile(m)
                out[key] = f.read() if f else b""
            else:
                out[key] = b""
    return out


def control_field(control: bytes, name: str) -> str:
    rx = re.compile(rb"^" + re.escape(name.encode()) + rb":\s*(.*?)\s*$", re.M)
    m = rx.search(control)
    return m.group(1).decode("utf-8", "replace") if m else ""


def version_tuple(v: str) -> tuple[int, ...]:
    nums = []
    for part in re.split(r"[^0-9]+", v):
        if part:
            nums.append(int(part))
    return tuple(nums)


def read_jsc(ipa: Path) -> bytes:
    with zipfile.ZipFile(ipa) as z:
        return z.read("Payload/AirplaneCooking-mobile.app/assets/scriptBundle/index.jsc")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ipa", type=Path, required=True)
    ap.add_argument("--deb", type=Path, required=True)
    ap.add_argument("--repo", type=Path, required=True)
    ns = ap.parse_args()
    repo = ns.repo
    jsc = read_jsc(ns.ipa)
    assert hashlib.sha256(jsc).hexdigest() == ORIG_JSC_SHA
    with zipfile.ZipFile(ns.ipa) as z:
        info = plistlib.loads(z.read("Payload/AirplaneCooking-mobile.app/Info.plist"))
        cfg = z.read("Payload/AirplaneCooking-mobile.app/assets/scriptBundle/config.json")
    assert info["CFBundleIdentifier"] == "com.airplanecooking.chef.kitchen.restaurant.diner"
    assert info["CFBundleShortVersionString"] == "1.26.02"
    assert b'"encrypted":true' in cfg
    plain = gunzip(xxtea_decrypt(jsc, KEY))
    assert plain.startswith(b"window.__require")
    patched = repo / "packaging" / "CookingGoMod.index12602.jsc"
    patched_jsc = patched.read_bytes()
    patched_plain = gunzip(xxtea_decrypt(patched_jsc, KEY))
    marker = b"/* ==== CookingGoMod bootstrap ==== */"
    assert marker in patched_plain
    bootstrap = (repo / "src" / "CGMBootstrap.js").read_bytes()
    assert bootstrap in patched_plain
    bootstrap_text = bootstrap.decode("utf-8", "replace")
    assert "var gIap = { enabled: false" in bootstrap_text, "IAP state must default to disabled in JS bootstrap"
    assert "loadIapState();" in bootstrap_text, "JS bootstrap must load persisted IAP state explicitly"
    assert "function retryBoot(reason)" in bootstrap_text, "JS bootstrap must retry if injected before JSB/mailbox readiness"
    generated_h = (repo / "src" / "CGMBootstrap.generated.h").read_text(encoding="utf-8")
    assert "bootstrap deferred limit reached" in generated_h, "generated bootstrap header must include retry payload"
    harness = repo / "tools" / "mock_cgm_bootstrap.js"
    harness_text = harness.read_text(encoding="utf-8")
    assert "default-off Pay wrapper passes purchase calls to original implementation" in harness_text
    assert "purchase-success synthesis path" in harness_text
    static_doc = repo / "docs" / "IAP-RICHES-STATIC-12602.md"
    static_doc_text = static_doc.read_text(encoding="utf-8")
    assert "Pay success dispatch model" in static_doc_text
    assert "Riches / 财富日历 chain" in static_doc_text
    # Ensure the static payload is not the untouched original and is self-consistent.
    assert patched_jsc != jsc
    # Read the Debian ar container without depending on dpkg-deb/ar being on PATH.
    raw = ns.deb.read_bytes()
    members = parse_deb(raw)
    data_files = tar_members(members["data.tar.gz"])
    ctrl_files = tar_members(members["control.tar.gz"])
    data_names = set(data_files)
    ctrl_names = set(ctrl_files)
    assert "var/jb/usr/lib/TweakInject/CookingGoMod.index12602.jsc" in data_names
    assert "control" in ctrl_names and "postinst" in ctrl_names and "postrm" in ctrl_names
    deb_version = control_field(ctrl_files["control"], "Version")
    cfg_path = "var/jb/usr/lib/TweakInject/CookingGoMod.cfg"
    dylib_path = "var/jb/usr/lib/TweakInject/CookingGoMod.dylib"
    bootstrap_pkg_path = "var/jb/usr/lib/TweakInject/CookingGoMod.bootstrap.js"
    jsc_pkg_path = "var/jb/usr/lib/TweakInject/CookingGoMod.index12602.jsc"
    assert cfg_path in data_files and dylib_path in data_files
    assert bootstrap_pkg_path in data_files and jsc_pkg_path in data_files
    assert data_files[bootstrap_pkg_path] == bootstrap, "DEB bootstrap payload differs from src/CGMBootstrap.js"
    assert data_files[jsc_pkg_path] == patched_jsc, "DEB packaged index12602 JSC differs from packaging/CookingGoMod.index12602.jsc"
    cfg_text = data_files[cfg_path].decode("utf-8", "replace")
    if version_tuple(deb_version) >= (1, 3, 2):
        src_m = (repo / "src" / "CookingGoMod.m").read_text(encoding="utf-8")
        runtime_doc = (repo / "docs" / "RUNTIME-HOOK-12602.md").read_text(encoding="utf-8")
        assert "rt=0" in cfg_text, "packaged cfg must keep runtime hook default-off"
        assert "kCGMEvalStringOffset12602 = 0x1c28a30" in src_m
        assert "kCGMScriptEngineGetInstanceOffset12602 = 0x1c263cc" in src_m
        assert "CGMInstallRuntimeEvalHook" in src_m
        assert "runtime evalString hook disabled by config" in src_m
        assert b"runtime evalString hook installed" in data_files[dylib_path]
        assert b"bootstrap deferred limit reached" in data_files[dylib_path], "packaged dylib must be rebuilt after JS retry changes"
        assert "candidate_evalString_function_va = 0x101c28a30" in runtime_doc
        assert "target = main_mach_header + 0x1c28a30" in runtime_doc
        assert "getInstance = main_mach_header + 0x1c263cc" in runtime_doc
    print("IPA sha256:", hashlib.sha256(ns.ipa.read_bytes()).hexdigest())
    print("original index.jsc sha256:", hashlib.sha256(jsc).hexdigest())
    print("original plain JS bytes:", len(plain))
    print("patched index.jsc sha256:", hashlib.sha256(patched_jsc).hexdigest())
    print("patched plain JS bytes:", len(patched_plain))
    print("deb sha256:", hashlib.sha256(raw).hexdigest())
    print("deb version:", deb_version)
    print("packaged cfg rt:", "rt=0" if "rt=0" in cfg_text else "<missing>")
    print("mock harness:", str(repo / "tools" / "mock_cgm_bootstrap.js"))
    print("static report:", str(repo / "docs" / "IAP-RICHES-STATIC-12602.md"))
    print("static closure: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
