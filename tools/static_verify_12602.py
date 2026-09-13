#!/usr/bin/env python3
"""Static closure check for Cooking GO 1.26.02 and the packaged tweak.
No device writes, app launch, or purchase operations are performed.
"""
from __future__ import annotations
import argparse, gzip, hashlib, io, plistlib, struct, tarfile, zipfile, zlib
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
    # Ensure the static payload is not the untouched original and is self-consistent.
    assert patched_jsc != jsc
    # Read the Debian ar container without depending on dpkg-deb/ar being on PATH.
    raw = ns.deb.read_bytes()
    assert raw[:8] == b"!<arch>\n"
    off = 8
    members = {}
    while off + 60 <= len(raw):
        hdr = raw[off:off + 60]
        name = hdr[:16].decode("ascii", "replace").strip().rstrip("/")
        size = int(hdr[48:58].decode("ascii", "replace").strip())
        body = raw[off + 60:off + 60 + size]
        members[name] = body
        off += 60 + size + (size & 1)
    assert "data.tar.gz" in members and "control.tar.gz" in members
    with tarfile.open(fileobj=io.BytesIO(members["data.tar.gz"]), mode="r:gz") as t:
        data_names = {m.name.lstrip("./") for m in t.getmembers()}
    with tarfile.open(fileobj=io.BytesIO(members["control.tar.gz"]), mode="r:gz") as t:
        ctrl_names = {m.name.lstrip("./") for m in t.getmembers()}
    assert "var/jb/usr/lib/TweakInject/CookingGoMod.index12602.jsc" in data_names
    assert "control" in ctrl_names and "postinst" in ctrl_names and "postrm" in ctrl_names
    print("IPA sha256:", hashlib.sha256(ns.ipa.read_bytes()).hexdigest())
    print("original index.jsc sha256:", hashlib.sha256(jsc).hexdigest())
    print("original plain JS bytes:", len(plain))
    print("patched index.jsc sha256:", hashlib.sha256(patched_jsc).hexdigest())
    print("patched plain JS bytes:", len(patched_plain))
    print("static closure: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
