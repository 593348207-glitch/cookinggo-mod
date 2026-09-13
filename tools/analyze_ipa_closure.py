#!/usr/bin/env python3
"""Static IPA closure triage for Cooking GO 1.26.02.

Checks the parts that explain launch-before-JS failures:
- app bundle signature resource files in the IPA archive;
- Mach-O LC_CODE_SIGNATURE / LC_ENCRYPTION_INFO presence;
- LC_RPATH + LC_LOAD_DYLIB / LC_LOAD_WEAK_DYLIB dependency closure for embedded frameworks.

This script is read-only and does not require Apple tooling.
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
from dataclasses import dataclass, asdict
from typing import Any

LC_NAMES = {
    0x0C: "LC_LOAD_DYLIB",
    0x0D: "LC_ID_DYLIB",
    0x18: "LC_LOAD_WEAK_DYLIB",
    0x80000018: "LC_LOAD_WEAK_DYLIB",
    0x1F: "LC_REEXPORT_DYLIB",
    0x8000001F: "LC_REEXPORT_DYLIB",
    0x20: "LC_LAZY_LOAD_DYLIB",
    0x80000020: "LC_LAZY_LOAD_DYLIB",
}
LC_RPATHS = {0x1C, 0x8000001C}
LC_CODE_SIGNATURE = 0x1D
LC_ENCRYPTION_INFO = 0x21
LC_ENCRYPTION_INFO_64 = 0x2C
LC_BUILD_VERSION = 0x32
LC_VERSION_MIN_IPHONEOS = 0x25

CSMAGIC_EMBEDDED_SIGNATURE = 0xFADE0CC0
CSMAGIC_CODEDIRECTORY = 0xFADE0C02
CSMAGIC_EMBEDDED_ENTITLEMENTS = 0xFADE7171
CSMAGIC_BLOBWRAPPER = 0xFADE0B01
CSSLOT_CODEDIRECTORY = 0
CSSLOT_ENTITLEMENTS = 5
CSSLOT_DER_ENTITLEMENTS = 7
CSSLOT_SIGNATURESLOT = 0x10000
CS_ADHOC = 0x00000002
CS_PLATFORM_BINARY = 0x04000000

HASH_TYPE_NAMES = {
    1: "sha1",
    2: "sha256",
    3: "sha256_truncated",
    4: "sha384",
}

CPU_NAMES = {
    0x0100000C: "arm64",
    0x0200000C: "arm64_32",
    12: "arm",
}
PLATFORM_NAMES = {
    1: "macOS",
    2: "iOS",
    3: "tvOS",
    4: "watchOS",
    6: "macCatalyst",
    7: "iOSSimulator",
}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def cstr(buf: bytes, off: int, end: int) -> str:
    if off < 0 or off >= len(buf):
        return ""
    z = buf.find(b"\0", off, min(end, len(buf)))
    if z < 0:
        z = min(end, len(buf))
    return buf[off:z].decode("utf-8", "replace")


def version24(x: int) -> str:
    return f"{(x >> 16) & 0xffff}.{(x >> 8) & 0xff}.{x & 0xff}"


@dataclass
class SliceInfo:
    arch: str
    offset: int
    size: int
    rpaths: list[str]
    loads: list[dict[str, str]]
    build: list[dict[str, str]]
    minos: list[dict[str, str]]
    code_signature: dict[str, int] | None
    code_signature_info: dict[str, Any] | None
    encryption: dict[str, int] | None


@dataclass
class BinaryInfo:
    path: str
    size: int
    sha256: str
    kind: str
    has_framework_coderesources: bool | None
    slices: list[SliceInfo]


def fat_slices(buf: bytes) -> list[tuple[int, int, int | None, int | None]]:
    if len(buf) < 4:
        return []
    magic = struct.unpack(">I", buf[:4])[0]
    if magic not in (0xCAFEBABE, 0xCAFEBABF):
        return [(0, len(buf), None, None)]
    nfat = struct.unpack(">I", buf[4:8])[0]
    pos = 8
    out: list[tuple[int, int, int | None, int | None]] = []
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
        out.append((int(off), int(size), cputype, cpusubtype))
    return out


def code_sign_flag_names(flags: int) -> list[str]:
    names: list[str] = []
    if flags & CS_ADHOC:
        names.append("adhoc")
    if flags & CS_PLATFORM_BINARY:
        names.append("platform")
    # Preserve the raw value because Apple adds flags over time and the raw bits
    # are more useful than silently dropping unknown security state.
    return names


def _read_be32(buf: bytes, off: int) -> int | None:
    if off < 0 or off + 4 > len(buf):
        return None
    return struct.unpack(">I", buf[off:off + 4])[0]


def _read_be64(buf: bytes, off: int) -> int | None:
    if off < 0 or off + 8 > len(buf):
        return None
    return struct.unpack(">Q", buf[off:off + 8])[0]


def parse_code_directory(cd: bytes, blob_offset: int, slot_type: int) -> dict[str, Any]:
    """Parse the fields needed for signing identity comparison.

    CodeDirectory is big-endian regardless of the Mach-O endianness. Offsets are
    relative to the beginning of the CodeDirectory blob.
    """
    if len(cd) < 44:
        return {"slot": slot_type, "offset": blob_offset, "error": "short CodeDirectory"}
    magic, length, version, flags, hash_off, ident_off, n_special, n_code, code_limit = struct.unpack(">IIIIIIIII", cd[:36])
    hash_size, hash_type, platform, page_size = struct.unpack(">BBBB", cd[36:40])
    scatter_off = _read_be32(cd, 40)
    team_off = _read_be32(cd, 44) if version >= 0x20100 and len(cd) >= 48 else None
    code_limit64 = _read_be64(cd, 56) if version >= 0x20200 and len(cd) >= 64 else None
    exec_seg_flags = _read_be64(cd, 80) if version >= 0x20300 and len(cd) >= 88 else None
    runtime = _read_be32(cd, 88) if version >= 0x20400 and len(cd) >= 92 else None

    ident = cstr(cd, ident_off, length) if ident_off else ""
    team = cstr(cd, team_off, length) if team_off else ""
    return {
        "slot": slot_type,
        "offset": blob_offset,
        "magic": f"0x{magic:08x}",
        "length": length,
        "version": f"0x{version:05x}",
        "flags": f"0x{flags:x}",
        "flag_names": code_sign_flag_names(flags),
        "identifier": ident,
        "team_id": team,
        "hash_offset": hash_off,
        "hash_size": hash_size,
        "hash_type": HASH_TYPE_NAMES.get(hash_type, str(hash_type)),
        "platform": platform,
        "page_size_log2": page_size,
        "scatter_offset": scatter_off,
        "n_special_slots": n_special,
        "n_code_slots": n_code,
        "code_limit": code_limit64 or code_limit,
        "exec_seg_flags": exec_seg_flags,
        "runtime": runtime,
    }


def parse_code_signature_blob(buf: bytes, code_signature: dict[str, int] | None, slice_off: int) -> dict[str, Any] | None:
    if not code_signature:
        return None
    dataoff = code_signature["dataoff"]
    datasize = code_signature["datasize"]
    # Thin Mach-O files use dataoff directly. Some fat/universal tooling reports
    # offsets relative to the slice. Try both to keep the script robust.
    candidates = [dataoff]
    if slice_off:
        candidates.append(slice_off + dataoff)
    base = None
    blob = b""
    for cand in candidates:
        if cand < 0 or cand + 8 > len(buf):
            continue
        magic = _read_be32(buf, cand)
        if magic in (CSMAGIC_EMBEDDED_SIGNATURE, CSMAGIC_CODEDIRECTORY):
            base = cand
            blob = buf[cand:cand + datasize]
            break
    if base is None:
        return {"error": "code signature blob not found", "dataoff": dataoff, "datasize": datasize}

    magic = _read_be32(blob, 0)
    length = _read_be32(blob, 4)
    if magic == CSMAGIC_CODEDIRECTORY:
        return {
            "type": "CodeDirectory",
            "offset": base,
            "length": length,
            "code_directories": [parse_code_directory(blob[:length or len(blob)], base, CSSLOT_CODEDIRECTORY)],
            "has_cms_signature": False,
            "has_entitlements": False,
            "slots": [],
        }
    if magic != CSMAGIC_EMBEDDED_SIGNATURE or len(blob) < 12:
        return {"error": f"unsupported code signature magic 0x{magic or 0:08x}", "offset": base, "length": length}

    count = _read_be32(blob, 8) or 0
    slots: list[dict[str, Any]] = []
    code_dirs: list[dict[str, Any]] = []
    has_entitlements = False
    has_cms = False
    for i in range(count):
        idx_off = 12 + i * 8
        if idx_off + 8 > len(blob):
            break
        slot_type = _read_be32(blob, idx_off)
        rel_off = _read_be32(blob, idx_off + 4)
        if slot_type is None or rel_off is None or rel_off + 8 > len(blob):
            continue
        sub_magic = _read_be32(blob, rel_off) or 0
        sub_len = _read_be32(blob, rel_off + 4) or 0
        slots.append({"type": slot_type, "offset": rel_off, "magic": f"0x{sub_magic:08x}", "length": sub_len})
        if sub_magic == CSMAGIC_CODEDIRECTORY and sub_len:
            code_dirs.append(parse_code_directory(blob[rel_off:rel_off + sub_len], base + rel_off, slot_type))
        elif slot_type in (CSSLOT_ENTITLEMENTS, CSSLOT_DER_ENTITLEMENTS):
            has_entitlements = True
        elif slot_type == CSSLOT_SIGNATURESLOT:
            has_cms = True

    return {
        "type": "SuperBlob",
        "offset": base,
        "length": length,
        "slot_count": count,
        "slots": slots,
        "code_directories": code_dirs,
        "has_cms_signature": has_cms,
        "has_entitlements": has_entitlements,
    }


def parse_macho(buf: bytes) -> list[SliceInfo]:
    result: list[SliceInfo] = []
    for slice_off, slice_size, fat_cpu, fat_sub in fat_slices(buf):
        b = buf[slice_off:slice_off + slice_size]
        if len(b) < 28:
            continue
        magic_le = struct.unpack("<I", b[:4])[0]
        magic_be = struct.unpack(">I", b[:4])[0]
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
            continue

        if is64:
            if len(b) < 32:
                continue
            _magic, cputype, cpusubtype, _filetype, ncmds, _sizeofcmds, _flags, _reserved = struct.unpack(endian + "IiiIIIII", b[:32])
            pos = 32
        else:
            _magic, cputype, cpusubtype, _filetype, ncmds, _sizeofcmds, _flags = struct.unpack(endian + "IiiIIII", b[:28])
            pos = 28
        if fat_cpu is not None:
            cputype, cpusubtype = fat_cpu, fat_sub or cpusubtype
        arch = CPU_NAMES.get(cputype, f"cpu:{cputype}/sub:{cpusubtype}")
        rpaths: list[str] = []
        loads: list[dict[str, str]] = []
        build: list[dict[str, str]] = []
        minos: list[dict[str, str]] = []
        code_signature: dict[str, int] | None = None
        encryption: dict[str, int] | None = None

        for _ in range(ncmds):
            if pos + 8 > len(b):
                break
            cmd, cmdsize = struct.unpack(endian + "II", b[pos:pos + 8])
            if cmdsize < 8 or pos + cmdsize > len(b):
                break
            if cmd in LC_RPATHS and pos + 12 <= len(b):
                pathoff = struct.unpack(endian + "I", b[pos + 8:pos + 12])[0]
                rpaths.append(cstr(b, pos + pathoff, pos + cmdsize))
            elif cmd in LC_NAMES and pos + 12 <= len(b):
                noff = struct.unpack(endian + "I", b[pos + 8:pos + 12])[0]
                loads.append({"cmd": LC_NAMES[cmd], "path": cstr(b, pos + noff, pos + cmdsize)})
            elif cmd == LC_CODE_SIGNATURE and pos + 16 <= len(b):
                dataoff, datasize = struct.unpack(endian + "II", b[pos + 8:pos + 16])
                code_signature = {"dataoff": int(dataoff), "datasize": int(datasize)}
            elif cmd in (LC_ENCRYPTION_INFO, LC_ENCRYPTION_INFO_64) and pos + 20 <= len(b):
                cryptoff, cryptsize, cryptid = struct.unpack(endian + "III", b[pos + 8:pos + 20])
                encryption = {"cryptoff": int(cryptoff), "cryptsize": int(cryptsize), "cryptid": int(cryptid)}
            elif cmd == LC_BUILD_VERSION and pos + 24 <= len(b):
                platform, minosv, sdk, _ntools = struct.unpack(endian + "IIII", b[pos + 8:pos + 24])
                build.append({"platform": PLATFORM_NAMES.get(platform, str(platform)), "minos": version24(minosv), "sdk": version24(sdk)})
            elif cmd == LC_VERSION_MIN_IPHONEOS and pos + 16 <= len(b):
                ver, sdk = struct.unpack(endian + "II", b[pos + 8:pos + 16])
                minos.append({"minos": version24(ver), "sdk": version24(sdk)})
            pos += cmdsize
        code_signature_info = parse_code_signature_blob(buf, code_signature, slice_off)
        result.append(SliceInfo(arch, slice_off, slice_size, rpaths, loads, build, minos, code_signature, code_signature_info, encryption))
    return result


def locate_app(names: list[str]) -> tuple[str, str]:
    info = next((n for n in names if n.startswith("Payload/") and n.endswith(".app/Info.plist")), None)
    if not info:
        raise SystemExit("No Payload/*.app/Info.plist found")
    return info[:-len("Info.plist")], info


def framework_binaries(names: list[str], app_prefix: str) -> list[str]:
    out: list[str] = []
    rx = re.compile(re.escape(app_prefix) + r"Frameworks/([^/]+\.framework)/([^/]+)$")
    for name in names:
        m = rx.match(name)
        if not m:
            continue
        fw_name = m.group(1)[:-10]
        if m.group(2) == fw_name:
            out.append(name)
    return sorted(out)


def analyze(ipa: str) -> dict[str, Any]:
    with zipfile.ZipFile(ipa) as z:
        names = z.namelist()
        name_set = set(names)
        app_prefix, info_path = locate_app(names)
        info = plistlib.loads(z.read(info_path))
        exe_path = app_prefix + info["CFBundleExecutable"]
        bins = [exe_path] + framework_binaries(names, app_prefix)

        embedded_fw_paths = {
            "@rpath/" + os.path.basename(os.path.dirname(path)) + "/" + os.path.basename(path): path
            for path in bins
            if "/Frameworks/" in path
        }
        binaries: list[BinaryInfo] = []
        dep_missing: list[dict[str, str]] = []
        dep_os_swift: list[dict[str, str]] = []

        for path in bins:
            data = z.read(path)
            fw_coderesources = None
            kind = "main" if path == exe_path else "framework"
            if kind == "framework":
                fw_coderesources = os.path.dirname(path) + "/_CodeSignature/CodeResources" in name_set
            slices = parse_macho(data)
            binaries.append(BinaryInfo(
                path=path,
                size=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                kind=kind,
                has_framework_coderesources=fw_coderesources,
                slices=slices,
            ))
            for sl in slices:
                for load in sl.loads:
                    dep = load["path"]
                    if not dep.startswith("@rpath/") or load["cmd"] == "LC_ID_DYLIB":
                        continue
                    if dep in embedded_fw_paths:
                        continue
                    if re.match(r"@rpath/libswift.*\.dylib$", dep) and "/usr/lib/swift" in sl.rpaths:
                        dep_os_swift.append({"binary": path, "dep": dep, "resolution": "/usr/lib/swift or dyld shared cache"})
                        continue
                    dep_missing.append({"binary": path, "dep": dep})

        signing_summaries: list[dict[str, Any]] = []
        for b in binaries:
            if not b.slices:
                continue
            sig = b.slices[0].code_signature_info or {}
            cds = sig.get("code_directories") or []
            # Prefer the strongest modern CodeDirectory when a SuperBlob carries
            # both SHA-1 and SHA-256/384 alternate code directories.
            cd = next((x for x in cds if x.get("hash_type") in ("sha384", "sha256")), cds[0] if cds else {})
            signing_summaries.append({
                "path": b.path,
                "kind": b.kind,
                "identifier": cd.get("identifier", ""),
                "team_id": cd.get("team_id", ""),
                "flags": cd.get("flags", ""),
                "flag_names": cd.get("flag_names", []),
                "hash_type": cd.get("hash_type", ""),
                "has_cms_signature": sig.get("has_cms_signature"),
                "has_entitlements": sig.get("has_entitlements"),
            })
        non_empty_team_ids = sorted({x["team_id"] for x in signing_summaries if x.get("team_id")})
        empty_team_paths = [x["path"] for x in signing_summaries if not x.get("team_id")]

        return {
            "ipa": os.path.abspath(ipa),
            "ipa_sha256": sha256_file(ipa),
            "app_prefix": app_prefix,
            "bundle_id": info.get("CFBundleIdentifier"),
            "short_version": info.get("CFBundleShortVersionString"),
            "bundle_version": info.get("CFBundleVersion"),
            "minimum_os_version": info.get("MinimumOSVersion"),
            "dt_sdk_name": info.get("DTSDKName"),
            "executable": exe_path,
            "has_app_coderesources": app_prefix + "_CodeSignature/CodeResources" in name_set,
            "app_codesign_entry_count": sum(1 for n in names if n.startswith(app_prefix + "_CodeSignature/")),
            "has_embedded_mobileprovision": app_prefix + "embedded.mobileprovision" in name_set,
            "framework_count": len(bins) - 1,
            "binaries": [asdict(b) for b in binaries],
            "signing_summaries": signing_summaries,
            "non_empty_team_ids": non_empty_team_ids,
            "empty_team_id_paths": empty_team_paths,
            "missing_rpath_dependencies": dep_missing,
            "os_swift_rpath_dependencies": dep_os_swift,
        }


def print_text(r: dict[str, Any]) -> None:
    print(f"IPA: {r['ipa']}")
    print(f"IPA sha256: {r['ipa_sha256']}")
    print(f"App: {r['app_prefix']}  bundle={r['bundle_id']}  version={r['short_version']}  minOS={r['minimum_os_version']}  sdk={r['dt_sdk_name']}")
    print(f"App _CodeSignature/CodeResources: {r['has_app_coderesources']}  entries={r['app_codesign_entry_count']}")
    print(f"embedded.mobileprovision: {r['has_embedded_mobileprovision']}")
    print(f"Embedded framework binaries: {r['framework_count']}")

    main = r['binaries'][0]
    sl = main['slices'][0] if main['slices'] else {}
    print("\nMain executable:")
    print(f"  path: {main['path']}")
    print(f"  sha256: {main['sha256']}")
    print(f"  arch: {sl.get('arch')}  build={sl.get('build')}  encryption={sl.get('encryption')}  code_signature={sl.get('code_signature')}")
    main_cds = (sl.get('code_signature_info') or {}).get('code_directories') or [{}]
    main_cd = next((x for x in main_cds if x.get('hash_type') in ('sha384', 'sha256')), main_cds[0])
    print(f"  signing: identifier={main_cd.get('identifier', '')} team={main_cd.get('team_id', '') or '<empty>'} flags={main_cd.get('flags', '')} {main_cd.get('flag_names', [])}")
    print(f"  rpaths: {sl.get('rpaths')}")

    teams = r.get('non_empty_team_ids', [])
    empty_team = r.get('empty_team_id_paths', [])
    print(f"\nSigning team IDs: {teams if teams else '<none>'}")
    if empty_team:
        print(f"Binaries with empty Team ID: {len(empty_team)}")
        for path in empty_team[:20]:
            print(f"  - {path}")

    no_coderes = [b['path'] for b in r['binaries'] if b['kind'] == 'framework' and not b.get('has_framework_coderesources')]
    if no_coderes:
        print(f"\nFramework CodeResources missing: {len(no_coderes)}/{r['framework_count']}")
        for path in no_coderes[:50]:
            print(f"  - {path}")

    print(f"\nMissing non-system @rpath deps: {len(r['missing_rpath_dependencies'])}")
    for item in r['missing_rpath_dependencies'][:80]:
        print(f"  - {item['binary']} -> {item['dep']}")
    print(f"Swift @rpath deps expected from OS/dyld cache: {len(r['os_swift_rpath_dependencies'])}")

    print("\nClosure verdict:")
    if r['missing_rpath_dependencies']:
        print("  FAIL: IPA has unresolved embedded @rpath dependencies.")
    else:
        print("  PASS: All non-system @rpath framework dependencies referenced by Mach-O load commands exist in the IPA.")
    if not r['has_app_coderesources']:
        print("  WARN: App bundle has no _CodeSignature/CodeResources in the IPA; expect signing/library-validation trouble after ad-hoc/resign installs.")
    if no_coderes:
        print("  WARN: Embedded frameworks also lack _CodeSignature/CodeResources entries in the archive.")
    if r.get('empty_team_id_paths') and r.get('non_empty_team_ids'):
        print("  WARN: Mixed signing identity state: at least one binary has empty Team ID while others have Team IDs. This matches Library Validation failure patterns after bad resigning.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--ipa', required=True)
    ap.add_argument('--json', action='store_true')
    ns = ap.parse_args()
    r = analyze(ns.ipa)
    if ns.json:
        json.dump(r, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print_text(r)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
