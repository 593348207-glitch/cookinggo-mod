# Cooking GO 1.26.02 runtime hook candidates

Date: 2026-09-13

## Why this exists

Cooking GO 1.26.02 changed the script payload from plain:

```text
assets/scriptBundle/index.js
config.json encrypted:false
```

to encrypted/gzipped XXTEA bytecode-like payload:

```text
assets/scriptBundle/index.jsc
config.json encrypted:true
XXTEA key: 75fa5f0d-2c43-45
```

The DEB keeps the static patched `CookingGoMod.index12602.jsc` for package/static verification, but `postinst` no longer mutates the live signed bundle. The next viable route is runtime injection after the engine has loaded/decrypted script content.

Base game still must launch first. Current installed app exits in dyld/library validation before any runtime hook can execute; see `docs/CRASH-TRIAGE-12602.md`.

## Static discovery command

```powershell
python F:\测试\cookingGO\github-cookinggo-mod\tools\find_runtime_hook_points.py `
  --ipa "F:\测试\cookingGO\Cooking Go_1.26.02.ipa" `
  --limit 30
```

## Current findings

Main binary:

```text
Payload/AirplaneCooking-mobile.app/AirplaneCooking-mobile
sha256: 0062a9bd15f9aeeddcc5f46746579c922e6a82d5cb3009d31c807179ec1424af
arch: arm64
symbols: 4240
ascii strings: 229943
```

High-value string evidence:

```text
ScriptEngine::evalString catch exception:
ScriptEngine::evalString script %s, failed!
ScriptEngine::onGetStringFromFile %s not found, possible missing file.
js_engine_FileUtils_getStringFromFile
js_engine_FileUtils_getDataFromFile
getStringFromFile
getDataFromFile
fullPathForFilename
%@/%@/%@/%@/config.json
%@/%@/config.json?gameId=%@
```

Symbol/string evidence also confirms V8 and zlib/inflate symbols are present:

```text
_ZN2v8...
_inflate
_inflateInit2_
_inflateEnd
```

No clean exported `se::ScriptEngine::evalString` symbol is available from the regular symbol table, so the next static reverse step is xref-based location from the strings above.


## Static xref coordinates

Use the xref helper:

```powershell
python F:\测试\cookingGO\github-cookinggo-mod\tools\macho_string_xrefs.py `
  --ipa "F:\测试\cookingGO\Cooking Go_1.26.02.ipa" `
  --pattern "ScriptEngine::evalString" `
  --limit 5
```

Current result for the 1.26.02 main binary:

```text
String VA 0x1028a6d85 file 0x28a6d85: ScriptEngine::evalString catch exception:
String VA 0x1028a6db0 file 0x28a6db0: ScriptEngine::evalString script %s, failed!

Xref 0x101c28cf0 file 0x1c28cf0 func=0x101c28a48 -> 0x1028a6d85
Xref 0x101c28d3c file 0x1c28d3c func=0x101c28a48 -> 0x1028a6db0
```

Static inferred function:

```text
candidate_evalString_function_va = 0x101c28a48
candidate_evalString_function_file_offset = 0x1c28a48
preferred_image_base = 0x100000000
candidate_runtime_offset_from_image_base = 0x1c28a48
```

Runtime address formula when the main image is loaded:

```c
uintptr_t evalString = (uintptr_t)main_mach_header + 0x1c28a48;
```

or equivalently:

```c
uintptr_t evalString = 0x101c28a48 + _dyld_get_image_vmaddr_slide(main_image_index);
```

The xref scanner also resolves FileUtils wrapper coordinates:

```text
js_engine_FileUtils_getStringFromFile string VA 0x102898087
xrefs around 0x101baec10..0x101baed98

js_engine_FileUtils_getDataFromFile string VA 0x1028980cc
xrefs around 0x101baf1ec..0x101baf36c

binding registration strings:
getStringFromFile xref 0x101bb5b74
getDataFromFile   xref 0x101bb5ba4
```

IDA/r2 follow-up should start at `0x101c28a48` and recover the exact C++ ABI from callers before enabling a live hook.

## Candidate hook levels

### Level A — JSB FileUtils binding

Evidence:

```text
js_engine_FileUtils_getStringFromFile
js_engine_FileUtils_getDataFromFile
getStringFromFile
getDataFromFile
```

Use when the script content is exposed through JSB file APIs. A hook here can append/bootstrap JS text when the engine asks for a script file. This may not catch the earliest encrypted `index.jsc` load if it is native-side only, but it is low-risk and easy to validate with logs.

Needed static follow-up:

1. In IDA/r2, find xrefs to `js_engine_FileUtils_getStringFromFile` and `js_engine_FileUtils_getDataFromFile` strings.
2. Identify the native wrapper functions.
3. Hook wrappers or the underlying `cocos2d::FileUtils` methods with `MSHookFunction`/ElleKit.

### Level B — `se::ScriptEngine::evalString` / runScript

Evidence:

```text
ScriptEngine::evalString catch exception:
ScriptEngine::evalString script %s, failed!
```

This is the best runtime injection point for 1.26.02: inject the bootstrap into the first post-engine script evaluation or run a separate `evalString(gJSPayload)` once the VM is initialized.

Needed static follow-up:

1. Xref both `ScriptEngine::evalString` strings.
2. Locate the function that logs `catch exception` and `script %s, failed!`.
3. Confirm signature by decompile/callers. Common C++ shape is equivalent to `bool evalString(const char *script, ssize_t length, se::Value *ret, const char *filename)` but exact ABI must be verified from call sites.
4. Hook with original-call-first or payload-once guard.

Preferred behavior:

```text
if target bundle && !payloadInjected && ScriptEngine is initialized:
    original_eval(...)
    original_eval(gJSPayload, strlen(gJSPayload), nullptr, "CookingGoMod.bootstrap.js")
```

### Level C — encrypted JSC load/decrypt/decompress buffer

Evidence:

```text
index.jsc
config.json encrypted:true
_inflate / _inflateInit2_ / gzip strings
XXTEA key statically recovered: 75fa5f0d-2c43-45
```

This is more invasive but closest to the old static patch model: intercept decrypted/decompressed JS buffer before evaluation and append `CGMBootstrap.js` in memory.

Needed static follow-up:

1. Xref `config.json`, `encrypted`, `index.jsc`, and ScriptEngine eval strings.
2. Walk the caller chain from file read → XXTEA decrypt → gzip inflate → eval.
3. Patch only the in-memory buffer returned to eval, not the bundle file.

## Current recommended path

1. Fix base app signing and verify game launches without tweak.
2. Use `find_runtime_hook_points.py` output to locate xrefs in IDA/r2.
3. Implement Level B first (`ScriptEngine::evalString` payload-once injection). It avoids signed bundle mutation and does not depend on the encrypted file format once the VM exists.
4. Keep Level A as a low-risk diagnostic/fallback.
5. Only use Level C if Level B cannot run early enough for module patching.

## Verification target after implementation

Inside the app container:

```text
Documents/cookingmod/bootstrap.js
Documents/cookingmod/js_hello.json
Documents/cookingmod/probe.json
Documents/cookingmod/state.json
Documents/cookingmod/iap_hook.json
```

On-device expected log evidence:

```text
CookingGoMod vX loaded
runtime evalString hook installed
runtime JS bootstrap eval OK
js_hello.json exists
probe.json has typeofRequire:function
state.json has ready:true and iapHook fields
```
