#!/usr/bin/env python3
"""Find static runtime hook candidates in Cooking GO iOS IPA.

This is a read-only helper for the 1.26.02 encrypted-JSC path. It inspects the
main Mach-O binary inside an IPA and reports symbol/string evidence around:
- Cocos ScriptEngine / evalString / runScript entry points;
- XXTEA/gzip/scriptBundle loading clues;
- FileUtils/resource loading clues;
- V8 and JSB bridge symbols.

It does not patch the IPA and does not require Apple tooling.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import plistlib
import re
import struct
import sys
import zipfile
from dataclasses import dataclass
from typing import Any

LC_SYMTAB = 0x02
LC_DYSYMTAB = 0x0B
CPU_NAMES = {0x0100000C: "arm64", 0x0200000C: "arm64_32", 12: "arm"}

KEY_PATTERNS = [
    r"ScriptEngine",
    r"evalString",
    r"runScript",
    r"executeScript",
    r"jsb_run_script",
    r"jsb_register",
    r"se::",
    r"_ZN2se",
    r"FileUtils",
    r"getStringFromFile",
    r"getDataFromFile",
    r"fullPathForFilename",
    r"scriptBundle",
    r"index\.jsc",
    r"project\.jsc",
    r"config\.json",
    r"xxtea",
    r"XXTEA",
    r"encryptjs",
    r"decrypt",
    r"inflate",
    r"gzip",
    r"zlib",
    r"v8::",
    r"_ZN2v8",
    r"YiFaniOSIAPBridge",
    r"buyProduct",
]

PRIORITY_PATTERNS = [
    r"_ZN2se12ScriptEngine10evalString",
    r"ScriptEngine.*evalString",
    r"jsb_run_script",
    r"xxtea.*decrypt|decrypt.*xxtea|XXTEA",
    r"getStringFromFile|getDataFromFile",
    r"scriptBundle|index\.jsc|config\.json",
]

PRINTABLE = set(range(0x20, 0x7f))


@dataclass
class Slice:
    offset: int
    size: int
    cputype: int | None
    cpusubtype: int | None


def cstr(buf: bytes, off: int, end: int) -> str:
    if off < 0 or off >= len(buf):
        return ""
    z = buf.find(b"\0", off, min(end, len(buf)))
    if z < 0:
        z = min(end, len(buf))
    return buf[off:z].decode("utf-8", "replace")


def fat_slices(buf: bytes) -> list[Slice]:
    if len(buf) < 4:
        return []
    magic = struct.unpack(">I", buf[:4])[0]
    if magic not in (0xCAFEBABE, 0xCAFEBABF):
        return [Slice(0, len(buf), None, None)]
    nfat = struct.unpack(">I", buf[4:8])[0]
    pos = 8
    out: list[Slice] = []
    for _ in range(nfat):
        if magic == 0xCAFEBABF:
            if pos + 32 > len(buf):
                break
            cputype, cpusubtype, off, size, _align, _reserved = struct.unpack(">IIQQII", buf[pos:pos + 32])
            pos += 32
        else:
            if pos + 20 > len(buf):
                break
            cputype, cpusubtype, off, size, _align = struct.unpack(">IIIII", buf[pos:pos + 20])
            pos += 20
        out.append(Slice(int(off), int(size), cputype, cpusubtype))
    return out


def parse_load_commands(slice_bytes: bytes) -> tuple[str, str, list[dict[str, int]]]:
    if len(slice_bytes) < 28:
        return "", "", []
    magic_le = struct.unpack("<I", slice_bytes[:4])[0]
    magic_be = struct.unpack(">I", slice_bytes[:4])[0]
    endian = "<"
    is64 = False
    if magic_le == 0xFEEDFACF:
        endian, is64 = "<", True
    elif magic_be == 0xFEEDFACF:
        endian, is64 = ">", True
    elif magic_le == 0xFEEDFACE:
        endian, is64 = "<", False
    elif magic_be == 0xFEEDFACE:
        endian, is64 = ">", False
    else:
        return "", "", []
    if is64:
        _magic, cputype, cpusubtype, _filetype, ncmds, _sizeofcmds, _flags, _reserved = struct.unpack(endian + "IiiIIIII", slice_bytes[:32])
        pos = 32
        arch = CPU_NAMES.get(cputype, f"cpu:{cputype}/sub:{cpusubtype}")
    else:
        _magic, cputype, cpusubtype, _filetype, ncmds, _sizeofcmds, _flags = struct.unpack(endian + "IiiIIII", slice_bytes[:28])
        pos = 28
        arch = CPU_NAMES.get(cputype, f"cpu:{cputype}/sub:{cpusubtype}")
    cmds: list[dict[str, int]] = []
    for _ in range(ncmds):
        if pos + 8 > len(slice_bytes):
            break
        cmd, cmdsize = struct.unpack(endian + "II", slice_bytes[pos:pos + 8])
        if cmdsize < 8 or pos + cmdsize > len(slice_bytes):
            break
        entry: dict[str, int] = {"cmd": cmd, "cmdsize": cmdsize, "offset": pos}
        if cmd == LC_SYMTAB and cmdsize >= 24:
            symoff, nsyms, stroff, strsize = struct.unpack(endian + "IIII", slice_bytes[pos + 8:pos + 24])
            entry.update({"symoff": symoff, "nsyms": nsyms, "stroff": stroff, "strsize": strsize, "is64": int(is64)})
        cmds.append(entry)
        pos += cmdsize
    return endian, arch, cmds


def parse_symbols(slice_bytes: bytes) -> tuple[str, list[str]]:
    endian, arch, cmds = parse_load_commands(slice_bytes)
    if not endian:
        return "", []
    symcmd = next((c for c in cmds if c.get("cmd") == LC_SYMTAB), None)
    if not symcmd:
        return arch, []
    symoff = symcmd["symoff"]
    nsyms = symcmd["nsyms"]
    stroff = symcmd["stroff"]
    strsize = symcmd["strsize"]
    is64 = bool(symcmd.get("is64"))
    entsize = 16 if is64 else 12
    strtab = slice_bytes[stroff:stroff + strsize]
    out: list[str] = []
    for i in range(nsyms):
        off = symoff + i * entsize
        if off + entsize > len(slice_bytes):
            break
        n_strx = struct.unpack(endian + "I", slice_bytes[off:off + 4])[0]
        if n_strx == 0 or n_strx >= len(strtab):
            continue
        name = cstr(strtab, n_strx, len(strtab))
        if name:
            out.append(name)
    return arch, out


def extract_ascii_strings(buf: bytes, min_len: int = 5) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    start = None
    cur = bytearray()
    for i, b in enumerate(buf):
        if b in PRINTABLE:
            if start is None:
                start = i
            cur.append(b)
        else:
            if start is not None and len(cur) >= min_len:
                out.append((start, cur.decode("ascii", "replace")))
            start = None
            cur.clear()
    if start is not None and len(cur) >= min_len:
        out.append((start, cur.decode("ascii", "replace")))
    return out


def locate_app(names: list[str]) -> tuple[str, str]:
    info = next((n for n in names if n.startswith("Payload/") and n.endswith(".app/Info.plist")), None)
    if not info:
        raise SystemExit("No Payload/*.app/Info.plist found")
    return info[:-len("Info.plist")], info


def grep_items(items: list[str], patterns: list[str], limit_per_pattern: int) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for pat in patterns:
        rx = re.compile(pat, re.I)
        hits: list[str] = []
        for item in items:
            if rx.search(item):
                hits.append(item)
                if len(hits) >= limit_per_pattern:
                    break
        result[pat] = hits
    return result


def grep_string_items(items: list[tuple[int, str]], patterns: list[str], limit_per_pattern: int) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for pat in patterns:
        rx = re.compile(pat, re.I)
        hits: list[dict[str, Any]] = []
        for off, s in items:
            if rx.search(s):
                hits.append({"offset": off, "string": s})
                if len(hits) >= limit_per_pattern:
                    break
        result[pat] = hits
    return result


def flatten_hit_count(d: dict[str, list[Any]]) -> int:
    return sum(len(v) for v in d.values())


def analyze(ipa: str, limit: int) -> dict[str, Any]:
    with zipfile.ZipFile(ipa) as z:
        names = z.namelist()
        app_prefix, info_path = locate_app(names)
        info = plistlib.loads(z.read(info_path))
        exe_path = app_prefix + info["CFBundleExecutable"]
        data = z.read(exe_path)

    slices = fat_slices(data)
    if not slices:
        raise SystemExit("No Mach-O slice found")
    # Cooking GO 1.26.02 is arm64 thin; for universal binaries prefer arm64.
    selected = next((s for s in slices if s.cputype == 0x0100000C), slices[0])
    sdata = data[selected.offset:selected.offset + selected.size]
    arch, symbols = parse_symbols(sdata)
    ascii_items = extract_ascii_strings(sdata, min_len=5)

    symbol_hits = grep_items(symbols, KEY_PATTERNS, limit)
    string_hits = grep_string_items(ascii_items, KEY_PATTERNS, limit)
    priority_symbols = grep_items(symbols, PRIORITY_PATTERNS, limit)
    priority_strings = grep_string_items(ascii_items, PRIORITY_PATTERNS, limit)

    candidates: list[dict[str, Any]] = []
    for pat, hits in priority_symbols.items():
        for h in hits[:limit]:
            candidates.append({"source": "symbol", "pattern": pat, "value": h})
    for pat, hits in priority_strings.items():
        for h in hits[:limit]:
            candidates.append({"source": "string", "pattern": pat, "offset": h["offset"], "value": h["string"]})

    return {
        "ipa": os.path.abspath(ipa),
        "ipa_sha256": hashlib.sha256(open(ipa, "rb").read()).hexdigest(),
        "bundle_id": info.get("CFBundleIdentifier"),
        "short_version": info.get("CFBundleShortVersionString"),
        "executable": exe_path,
        "arch": arch,
        "binary_sha256": hashlib.sha256(data).hexdigest(),
        "symbol_count": len(symbols),
        "ascii_string_count": len(ascii_items),
        "symbol_hit_count": flatten_hit_count(symbol_hits),
        "string_hit_count": flatten_hit_count(string_hits),
        "priority_candidates": candidates[:200],
        "symbol_hits": symbol_hits,
        "string_hits": string_hits,
    }


def print_text(r: dict[str, Any]) -> None:
    print(f"IPA: {r['ipa']}")
    print(f"IPA sha256: {r['ipa_sha256']}")
    print(f"Executable: {r['executable']} arch={r['arch']} binary_sha256={r['binary_sha256']}")
    print(f"symbols={r['symbol_count']} ascii_strings={r['ascii_string_count']} symbol_hits={r['symbol_hit_count']} string_hits={r['string_hit_count']}")
    print("\nPriority hook candidates:")
    for c in r["priority_candidates"][:80]:
        if c["source"] == "symbol":
            print(f"  [symbol] {c['pattern']} :: {c['value']}")
        else:
            print(f"  [string @0x{c['offset']:x}] {c['pattern']} :: {c['value']}")
    print("\nGrouped symbol hits:")
    for pat, hits in r["symbol_hits"].items():
        if hits:
            print(f"  {pat}: {len(hits)}")
            for h in hits[:20]:
                print(f"    {h}")
    print("\nGrouped string hits:")
    for pat, hits in r["string_hits"].items():
        if hits:
            print(f"  {pat}: {len(hits)}")
            for h in hits[:20]:
                print(f"    @0x{h['offset']:x} {h['string']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ipa", required=True)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--limit", type=int, default=30)
    ns = ap.parse_args()
    r = analyze(ns.ipa, ns.limit)
    if ns.json:
        import json
        json.dump(r, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print_text(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
