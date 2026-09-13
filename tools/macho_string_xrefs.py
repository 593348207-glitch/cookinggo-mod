#!/usr/bin/env python3
"""Find ARM64 string xrefs inside the main Mach-O of an IPA.

This is intentionally lightweight: it parses LC_SEGMENT_64 sections, maps file
offsets to VM addresses, locates target ASCII strings, then scans __TEXT,__text
for common ADRP+ADD / ADRP+LDR page references to those string addresses.

It is a static helper for locating stripped Cocos/V8 hook points such as
`ScriptEngine::evalString` from nearby log strings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import struct
import sys
import zipfile
from dataclasses import asdict, dataclass
from typing import Any

LC_SEGMENT_64 = 0x19
CPU_ARM64 = 0x0100000C

DEFAULT_PATTERNS = [
    r"ScriptEngine::evalString catch exception:",
    r"ScriptEngine::evalString script %s, failed!",
    r"ScriptEngine::onGetStringFromFile %s not found",
    r"js_engine_FileUtils_getStringFromFile",
    r"js_engine_FileUtils_getDataFromFile",
    r"getStringFromFile",
    r"getDataFromFile",
    r"%@/%@/%@/%@/config.json",
    r"%@/%@/config.json\?gameId=%@",
]

PRINTABLE = set(range(0x20, 0x7f))


@dataclass
class FatSlice:
    offset: int
    size: int
    cputype: int | None
    cpusubtype: int | None


@dataclass
class Section:
    segname: str
    sectname: str
    addr: int
    size: int
    offset: int
    flags: int


@dataclass
class StringHit:
    file_offset: int
    vmaddr: int
    string: str
    pattern: str
    section: str


@dataclass
class Xref:
    insn_addr: int
    insn_file_offset: int
    inferred_func_addr: int | None
    inferred_func_file_offset: int | None
    target_addr: int
    target_file_offset: int | None
    kind: str
    reg: int
    text: str


def cstr(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("utf-8", "replace")


def fat_slices(buf: bytes) -> list[FatSlice]:
    if len(buf) < 4:
        return []
    magic = struct.unpack(">I", buf[:4])[0]
    if magic not in (0xCAFEBABE, 0xCAFEBABF):
        return [FatSlice(0, len(buf), None, None)]
    nfat = struct.unpack(">I", buf[4:8])[0]
    pos = 8
    out: list[FatSlice] = []
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
        out.append(FatSlice(int(off), int(size), cputype, cpusubtype))
    return out


def parse_sections(macho: bytes) -> tuple[str, list[Section]]:
    if len(macho) < 32:
        return "", []
    magic_le = struct.unpack("<I", macho[:4])[0]
    magic_be = struct.unpack(">I", macho[:4])[0]
    if magic_le == 0xFEEDFACF:
        endian = "<"
    elif magic_be == 0xFEEDFACF:
        endian = ">"
    else:
        return "", []
    _magic, _cputype, _cpusub, _filetype, ncmds, _sizeofcmds, _flags, _reserved = struct.unpack(endian + "IiiIIIII", macho[:32])
    pos = 32
    sections: list[Section] = []
    for _ in range(ncmds):
        if pos + 8 > len(macho):
            break
        cmd, cmdsize = struct.unpack(endian + "II", macho[pos:pos + 8])
        if cmdsize < 8 or pos + cmdsize > len(macho):
            break
        if cmd == LC_SEGMENT_64 and cmdsize >= 72:
            segname = cstr(macho[pos + 8:pos + 24])
            _vmaddr, _vmsize, _fileoff, _filesize, _maxprot, _initprot, nsects, _segflags = struct.unpack(endian + "QQQQiiii", macho[pos + 24:pos + 72])
            secpos = pos + 72
            for _j in range(nsects):
                if secpos + 80 > pos + cmdsize:
                    break
                sectname = cstr(macho[secpos:secpos + 16])
                secseg = cstr(macho[secpos + 16:secpos + 32]) or segname
                addr, size = struct.unpack(endian + "QQ", macho[secpos + 32:secpos + 48])
                offset, _align, _reloff, _nreloc, flags, _r1, _r2, _r3 = struct.unpack(endian + "IIIIIIII", macho[secpos + 48:secpos + 80])
                sections.append(Section(secseg, sectname, addr, int(size), int(offset), flags))
                secpos += 80
        pos += cmdsize
    return endian, sections


def section_for_file_offset(sections: list[Section], off: int) -> Section | None:
    for s in sections:
        if s.offset <= off < s.offset + s.size:
            return s
    return None


def file_to_vm(sections: list[Section], off: int) -> int | None:
    s = section_for_file_offset(sections, off)
    if not s:
        return None
    return s.addr + (off - s.offset)


def vm_to_file(sections: list[Section], addr: int) -> int | None:
    for s in sections:
        if s.addr <= addr < s.addr + s.size:
            return s.offset + (addr - s.addr)
    return None


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


def sign_extend(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return (value & (sign - 1)) - (value & sign)


def is_adrp(insn: int) -> bool:
    return (insn & 0x9F000000) == 0x90000000


def adrp_target(insn: int, pc: int) -> tuple[int, int]:
    rd = insn & 0x1F
    immlo = (insn >> 29) & 0x3
    immhi = (insn >> 5) & 0x7FFFF
    imm = sign_extend((immhi << 2) | immlo, 21) << 12
    return rd, (pc & ~0xFFF) + imm


def is_add_imm_64(insn: int) -> bool:
    return (insn & 0xFF800000) == 0x91000000


def add_imm_value(insn: int) -> tuple[int, int, int]:
    rd = insn & 0x1F
    rn = (insn >> 5) & 0x1F
    imm12 = (insn >> 10) & 0xFFF
    shift = (insn >> 22) & 0x3
    imm = imm12 << (12 if shift else 0)
    return rd, rn, imm


def is_ldr_literal_or_unsigned(insn: int) -> bool:
    # LDR Xt, [Xn, #imm12] unsigned offset, 64-bit variant.
    return (insn & 0xFFC00000) == 0xF9400000


def ldr_unsigned_value(insn: int) -> tuple[int, int, int]:
    rt = insn & 0x1F
    rn = (insn >> 5) & 0x1F
    imm12 = (insn >> 10) & 0xFFF
    return rt, rn, imm12 * 8


def looks_like_frame_prologue(word_bytes: bytes) -> bool:
    # Common ARM64 frame setup: stp x29, x30, [sp, #-imm]!
    # Encodings appear as: fd 7b bf a9, fd 7b be a9, fd 7b bd a9, ...
    return len(word_bytes) == 4 and word_bytes[0] == 0xFD and word_bytes[1] == 0x7B and word_bytes[3] == 0xA9


def infer_function_start(text_bytes: bytes, text_addr: int, off: int, max_back: int = 0x3000) -> int | None:
    start = max(0, off - max_back)
    # Walk backwards on instruction alignment. Prefer nearest standard frame prologue.
    for p in range(off & ~3, start, -4):
        if looks_like_frame_prologue(text_bytes[p:p + 4]):
            return text_addr + p
    return None


def scan_xrefs(macho: bytes, sections: list[Section], target_addrs: set[int], window: int = 8) -> list[Xref]:
    text = next((s for s in sections if s.segname == "__TEXT" and s.sectname == "__text"), None)
    if not text:
        return []
    tb = macho[text.offset:text.offset + text.size]
    xrefs: list[Xref] = []
    target_pages = {a & ~0xFFF for a in target_addrs}
    exact_targets = set(target_addrs)
    for off in range(0, len(tb) - 4, 4):
        insn = struct.unpack("<I", tb[off:off + 4])[0]
        pc = text.addr + off
        if not is_adrp(insn):
            continue
        reg, page = adrp_target(insn, pc)
        if page not in target_pages:
            continue
        for j in range(1, window + 1):
            noff = off + j * 4
            if noff + 4 > len(tb):
                break
            ninsn = struct.unpack("<I", tb[noff:noff + 4])[0]
            npc = text.addr + noff
            if is_add_imm_64(ninsn):
                rd, rn, imm = add_imm_value(ninsn)
                if rn == reg:
                    target = page + imm
                    if target in exact_targets:
                        func = infer_function_start(tb, text.addr, noff)
                        xrefs.append(Xref(npc, text.offset + noff, func, vm_to_file(sections, func) if func else None, target, vm_to_file(sections, target), "ADRP+ADD", reg, f"adrp x{reg}, 0x{page:x}; add x{rd}, x{rn}, #0x{imm:x}"))
            if is_ldr_literal_or_unsigned(ninsn):
                rt, rn, imm = ldr_unsigned_value(ninsn)
                if rn == reg:
                    target = page + imm
                    if target in exact_targets:
                        func = infer_function_start(tb, text.addr, noff)
                        xrefs.append(Xref(npc, text.offset + noff, func, vm_to_file(sections, func) if func else None, target, vm_to_file(sections, target), "ADRP+LDR", reg, f"adrp x{reg}, 0x{page:x}; ldr x{rt}, [x{rn}, #0x{imm:x}]"))
    # Dedup preserving order.
    seen = set()
    out = []
    for x in xrefs:
        k = (x.insn_addr, x.target_addr, x.kind)
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


def locate_app(names: list[str]) -> tuple[str, str]:
    info = next((n for n in names if n.startswith("Payload/") and n.endswith(".app/Info.plist")), None)
    if not info:
        raise SystemExit("No Payload/*.app/Info.plist found")
    return info[:-len("Info.plist")], info


def get_main_macho_from_ipa(ipa: str) -> tuple[dict[str, Any], bytes]:
    with zipfile.ZipFile(ipa) as z:
        names = z.namelist()
        app_prefix, info_path = locate_app(names)
        info = plistlib.loads(z.read(info_path))
        exe_path = app_prefix + info["CFBundleExecutable"]
        full = z.read(exe_path)
    slices = fat_slices(full)
    selected = next((s for s in slices if s.cputype == CPU_ARM64), slices[0])
    return {
        "app_prefix": app_prefix,
        "bundle_id": info.get("CFBundleIdentifier"),
        "short_version": info.get("CFBundleShortVersionString"),
        "executable": exe_path,
        "full_binary_sha256": hashlib.sha256(full).hexdigest(),
        "slice_offset": selected.offset,
        "slice_size": selected.size,
    }, full[selected.offset:selected.offset + selected.size]


def analyze(ipa: str, patterns: list[str], limit: int) -> dict[str, Any]:
    meta, macho = get_main_macho_from_ipa(ipa)
    endian, sections = parse_sections(macho)
    if endian != "<":
        raise SystemExit("This xref scanner currently expects little-endian arm64 Mach-O")
    strings = extract_ascii_strings(macho, min_len=5)
    hits: list[StringHit] = []
    for pat in patterns:
        rx = re.compile(pat, re.I)
        count = 0
        for off, st in strings:
            if not rx.search(st):
                continue
            va = file_to_vm(sections, off)
            sec = section_for_file_offset(sections, off)
            if va is None or sec is None:
                continue
            hits.append(StringHit(off, va, st, pat, f"{sec.segname},{sec.sectname}"))
            count += 1
            if count >= limit:
                break
    target_addrs = {h.vmaddr for h in hits}
    xrefs = scan_xrefs(macho, sections, target_addrs)
    grouped: dict[str, list[dict[str, Any]]] = {}
    by_addr = {h.vmaddr: h for h in hits}
    for x in xrefs:
        h = by_addr.get(x.target_addr)
        if not h:
            continue
        grouped.setdefault(h.string, []).append(asdict(x))
    return {
        "ipa": os.path.abspath(ipa),
        "ipa_sha256": hashlib.sha256(open(ipa, "rb").read()).hexdigest(),
        **meta,
        "section_count": len(sections),
        "string_hits": [asdict(h) for h in hits],
        "xref_count": len(xrefs),
        "xrefs": [asdict(x) for x in xrefs],
        "grouped_xrefs": grouped,
    }


def print_text(r: dict[str, Any]) -> None:
    print(f"IPA: {r['ipa']}")
    print(f"IPA sha256: {r['ipa_sha256']}")
    print(f"Executable: {r['executable']} binary_sha256={r['full_binary_sha256']} slice=0x{r['slice_offset']:x}+0x{r['slice_size']:x}")
    print(f"sections={r['section_count']} string_hits={len(r['string_hits'])} xrefs={r['xref_count']}")
    print("\nString hits:")
    for h in r["string_hits"]:
        print(f"  VA 0x{h['vmaddr']:x} file 0x{h['file_offset']:x} [{h['section']}] {h['string']}")
    print("\nXrefs:")
    for x in r["xrefs"]:
        target = next((h for h in r["string_hits"] if h["vmaddr"] == x["target_addr"]), None)
        s = target["string"] if target else ""
        func = x.get('inferred_func_addr')
        func_s = f" func=0x{func:x}" if func else " func=<unknown>"
        print(f"  0x{x['insn_addr']:x} file 0x{x['insn_file_offset']:x}{func_s} -> 0x{x['target_addr']:x} {x['kind']} {x['text']} :: {s}")
    if not r["xrefs"]:
        print("  <none found by simple ADRP+ADD/LDR scan; use IDA/r2 xrefs from the listed VA strings>")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ipa", required=True)
    ap.add_argument("--pattern", action="append", default=[], help="regex pattern; may be repeated")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--limit", type=int, default=10)
    ns = ap.parse_args()
    patterns = ns.pattern or DEFAULT_PATTERNS
    r = analyze(ns.ipa, patterns, ns.limit)
    if ns.json:
        json.dump(r, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print_text(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
