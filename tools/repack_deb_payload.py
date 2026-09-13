#!/usr/bin/env python3
"""Replace selected files inside a gzip-compressed Debian package data.tar.gz.

This is a Windows-friendly fallback when dpkg-deb is unavailable. It preserves
control.tar.gz and existing tar metadata for unchanged files. Intended here for
synchronizing packaged JS/JSC artifacts after local static verification changes.
"""
from __future__ import annotations
import argparse, gzip, io, tarfile
from dataclasses import dataclass
from pathlib import Path

AR_MAGIC = b"!<arch>\n"

@dataclass
class ArMember:
    name: str
    mtime: bytes
    uid: bytes
    gid: bytes
    mode: bytes
    data: bytes


def read_ar(path: Path) -> list[ArMember]:
    raw = path.read_bytes()
    if not raw.startswith(AR_MAGIC):
        raise ValueError(f"not a deb/ar archive: {path}")
    out: list[ArMember] = []
    off = len(AR_MAGIC)
    while off + 60 <= len(raw):
        hdr = raw[off:off + 60]
        if hdr[58:60] != b"`\n":
            raise ValueError(f"bad ar header at offset {off}")
        name = hdr[:16].decode("ascii", "replace").strip().rstrip("/")
        size = int(hdr[48:58].decode("ascii", "replace").strip())
        data = raw[off + 60: off + 60 + size]
        out.append(ArMember(name, hdr[16:28], hdr[28:34], hdr[34:40], hdr[40:48], data))
        off += 60 + size + (size & 1)
    return out


def write_ar(path: Path, members: list[ArMember]) -> None:
    with path.open("wb") as f:
        f.write(AR_MAGIC)
        for m in members:
            name = (m.name + "/").encode("ascii")[:16].ljust(16, b" ")
            hdr = b"".join([
                name,
                m.mtime[:12].ljust(12, b" "),
                m.uid[:6].ljust(6, b" "),
                m.gid[:6].ljust(6, b" "),
                m.mode[:8].ljust(8, b" "),
                str(len(m.data)).encode("ascii").ljust(10, b" "),
                b"`\n",
            ])
            f.write(hdr)
            f.write(m.data)
            if len(m.data) & 1:
                f.write(b"\n")


def read_tar_gz(raw: bytes) -> tuple[list[tarfile.TarInfo], dict[str, bytes]]:
    infos: list[tarfile.TarInfo] = []
    payloads: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
        for info in tf.getmembers():
            infos.append(info)
            if info.isfile():
                fh = tf.extractfile(info)
                payloads[info.name] = fh.read() if fh else b""
    return infos, payloads


def write_tar_gz(infos: list[tarfile.TarInfo], payloads: dict[str, bytes]) -> bytes:
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w") as tf:
        for old in infos:
            info = tarfile.TarInfo(old.name)
            info.mode = old.mode
            info.uid = old.uid
            info.gid = old.gid
            info.uname = old.uname
            info.gname = old.gname
            info.mtime = old.mtime
            info.type = old.type
            info.linkname = old.linkname
            if old.isfile():
                data = payloads[old.name]
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
            else:
                info.size = 0
                tf.addfile(info)
    gz_buf = io.BytesIO()
    with gzip.GzipFile(fileobj=gz_buf, mode="wb", mtime=0) as gz:
        gz.write(tar_buf.getvalue())
    return gz_buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--bootstrap", type=Path, required=True)
    ap.add_argument("--jsc", type=Path, required=True)
    ns = ap.parse_args()

    replacements = {
        "./var/jb/usr/lib/TweakInject/CookingGoMod.bootstrap.js": ns.bootstrap.read_bytes(),
        "var/jb/usr/lib/TweakInject/CookingGoMod.bootstrap.js": ns.bootstrap.read_bytes(),
        "./var/jb/usr/lib/TweakInject/CookingGoMod.index12602.jsc": ns.jsc.read_bytes(),
        "var/jb/usr/lib/TweakInject/CookingGoMod.index12602.jsc": ns.jsc.read_bytes(),
    }
    members = read_ar(ns.input)
    replaced = []
    for m in members:
        if m.name == "data.tar.gz":
            infos, payloads = read_tar_gz(m.data)
            for name in list(payloads):
                if name in replacements:
                    payloads[name] = replacements[name]
                    replaced.append(name)
            m.data = write_tar_gz(infos, payloads)
            break
    need = {"var/jb/usr/lib/TweakInject/CookingGoMod.bootstrap.js", "var/jb/usr/lib/TweakInject/CookingGoMod.index12602.jsc"}
    normalized = {x.lstrip("./") for x in replaced}
    missing = sorted(need - normalized)
    if missing:
      raise SystemExit(f"missing target(s) in data.tar.gz: {missing}")
    ns.output.parent.mkdir(parents=True, exist_ok=True)
    write_ar(ns.output, members)
    print("wrote", ns.output)
    for name in sorted(normalized):
        print("replaced", name)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
