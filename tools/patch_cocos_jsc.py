#!/usr/bin/env python3
"""Patch Cocos Creator encrypted .jsc by decrypting XXTEA, gunzipping, appending bootstrap JS, gzipping, and re-encrypting.

Targeted at Cooking GO 1.26.02 scriptBundle/index.jsc. The key is recovered from the
Cocos executable string and passed explicitly so the generated payload is deterministic.
"""
import argparse
import gzip
import hashlib
import io
import struct
import sys
import zipfile
import zlib
from pathlib import Path

DELTA = 0x9E3779B9


def _key_words(key: bytes):
    key = key[:16].ljust(16, b"\0")
    return list(struct.unpack("<4I", key))


def _words_from_bytes(data: bytes):
    if len(data) % 4:
        data += b"\0" * (4 - (len(data) % 4))
    return list(struct.unpack("<%dI" % (len(data) // 4), data))


def _bytes_from_words(words):
    return struct.pack("<%dI" % len(words), *[(x & 0xFFFFFFFF) for x in words])


def xxtea_decrypt(data: bytes, key: bytes) -> bytes:
    n = len(data) // 4
    if n < 2:
        return data
    v = list(struct.unpack("<%dI" % n, data[: n * 4]))
    k = _key_words(key)
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
        p = 0
        mx = (((z >> 5) ^ ((y << 2) & 0xFFFFFFFF)) + ((y >> 3) ^ ((z << 4) & 0xFFFFFFFF))) ^ ((total ^ y) + (k[(p & 3) ^ e] ^ z))
        v[0] = (v[0] - mx) & 0xFFFFFFFF
        y = v[0]
        total = (total - DELTA) & 0xFFFFFFFF
    return _bytes_from_words(v)


def xxtea_encrypt(data: bytes, key: bytes) -> bytes:
    v = _words_from_bytes(data)
    n = len(v)
    if n < 2:
        return data
    k = _key_words(key)
    q = 6 + 52 // n
    total = 0
    z = v[n - 1]
    for _ in range(q):
        total = (total + DELTA) & 0xFFFFFFFF
        e = (total >> 2) & 3
        for p in range(0, n - 1):
            y = v[p + 1]
            mx = (((z >> 5) ^ ((y << 2) & 0xFFFFFFFF)) + ((y >> 3) ^ ((z << 4) & 0xFFFFFFFF))) ^ ((total ^ y) + (k[(p & 3) ^ e] ^ z))
            v[p] = (v[p] + mx) & 0xFFFFFFFF
            z = v[p]
        y = v[0]
        p = n - 1
        mx = (((z >> 5) ^ ((y << 2) & 0xFFFFFFFF)) + ((y >> 3) ^ ((z << 4) & 0xFFFFFFFF))) ^ ((total ^ y) + (k[(p & 3) ^ e] ^ z))
        v[p] = (v[p] + mx) & 0xFFFFFFFF
        z = v[p]
    return _bytes_from_words(v)


def gunzip_lenient(data: bytes) -> bytes:
    obj = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = obj.decompress(data)
    if not obj.eof:
        raise ValueError("decrypted payload is not a complete gzip stream")
    return out


def gzip_deterministic(data: bytes) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0, compresslevel=9) as gz:
        gz.write(data)
    return buf.getvalue()


def read_input(path: Path, member: str | None) -> bytes:
    if member:
        with zipfile.ZipFile(path) as zf:
            return zf.read(member)
    return path.read_bytes()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="IPA or raw index.jsc")
    ap.add_argument("--member", default="Payload/AirplaneCooking-mobile.app/assets/scriptBundle/index.jsc")
    ap.add_argument("--key", required=True)
    ap.add_argument("--bootstrap", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--dump-js", default=None)
    ns = ap.parse_args(argv)

    enc = read_input(Path(ns.input), ns.member or None)
    dec = xxtea_decrypt(enc, ns.key.encode("utf-8"))
    js = gunzip_lenient(dec)
    boot = Path(ns.bootstrap).read_bytes()
    marker = b"\n/* ==== CookingGoMod bootstrap ==== */\n"
    if marker in js:
        base = js.split(marker, 1)[0]
    else:
        base = js
    patched_js = base.rstrip(b"\n") + marker + boot + b"\n"
    gz = gzip_deterministic(patched_js)
    out = xxtea_encrypt(gz, ns.key.encode("utf-8"))
    Path(ns.output).parent.mkdir(parents=True, exist_ok=True)
    Path(ns.output).write_bytes(out)
    if ns.dump_js:
        Path(ns.dump_js).parent.mkdir(parents=True, exist_ok=True)
        Path(ns.dump_js).write_bytes(patched_js)
    print("input_sha256", hashlib.sha256(enc).hexdigest())
    print("plain_js_bytes", len(js))
    print("patched_js_bytes", len(patched_js))
    print("output_bytes", len(out))
    print("output_sha256", hashlib.sha256(out).hexdigest())
    # self-check
    chk = gunzip_lenient(xxtea_decrypt(out, ns.key.encode("utf-8")))
    assert chk == patched_js
    print("verify", "OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
