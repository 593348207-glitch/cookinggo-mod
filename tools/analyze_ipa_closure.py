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
        result.append(SliceInfo(arch, slice_off, slice_size, rpaths, loads, build, minos, code_signature, encryption))
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
    print(f"  rpaths: {sl.get('rpaths')}")

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
