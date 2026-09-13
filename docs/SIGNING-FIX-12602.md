# Cooking GO 1.26.02 dyld / Library Validation fix path

## Current failure

The 1.26.02 app currently exits before Cocos/JS startup. The verified failure is a signing/library-validation mismatch:

```text
Library Validation failed: Rejecting .../Frameworks/AdjustSdk.framework/AdjustSdk
for process AirplaneCooking ... (Team ID: none, platform: yes)
reason: mapping process is a platform binary, but mapped file is not
RBSProcessExitStatus| domain:dyld(6) code:1
```

The live `assets/scriptBundle/index.jsc` is original and readable:

```text
cb1825d4c535f77de8cafbec1d4b73e65d10f43835d04cb091c856b4967269d0
```

So the base game bundle must be fixed before testing the mod or IAP hook.

## Static closure commands

```powershell
python F:\测试\cookingGO\github-cookinggo-mod\tools\analyze_ipa_closure.py `
  --ipa "F:\测试\cookingGO\Cooking Go_1.26.02.ipa"
```

Expected current evidence:

```text
Missing non-system @rpath deps: 0
App _CodeSignature/CodeResources: False
Framework CodeResources missing: 23/23
Signing team IDs: <none>
Binaries with empty Team ID: 24
```

## Device launch triage

```powershell
python F:\测试\cookingGO\github-cookinggo-mod\tools\device_launch_triage.py `
  --mcp F:\测试\cookingGO\mcp.py `
  --out F:\测试\cookingGO\_work\device_launch_triage_12602.txt
```

Look for:

```text
has_library_validation_failure: true
has_dyld_exit: true
first_rejected_library: .../Frameworks/AdjustSdk.framework/AdjustSdk
```

## Fix option A: clean install

Install a clean App Store/TestFlight or otherwise correctly signed 1.26.02 build. Then rerun `device_launch_triage.py`. The base game must launch with no `Library Validation failed` line before reinstalling `com.seagull.cookinggomod`.

## Fix option B: live-device ad-hoc re-sign fallback

When macOS signing material is not available, the lab device can repair the installed bundle in place with the MCP root helper:

```powershell
python F:\测试\cookingGO\github-cookinggo-mod\tools\device_resign_live_app.py `
  --mcp F:\测试\cookingGO\mcp.py `
  --out F:\测试\cookingGO\_work\device_resign_live_app.json
```

This signs every embedded framework binary first and `AirplaneCooking-mobile` last via `mcp-root /usr/bin/mcp-ldid -S`. It leaves `assets/scriptBundle/index.jsc` and the DEB payload untouched. Current device result after this path: base launch gate passes with `lv=0`, `dyld=0`.

## Fix option C: recursive re-sign on macOS

Use the provided script on macOS with Xcode command-line tools:

```bash
security find-identity -v -p codesigning

bash tools/resign_ipa_recursive.sh \
  --ipa "/path/to/Cooking Go_1.26.02.ipa" \
  --identity "Apple Development: Your Name (TEAMID)" \
  --provision /path/to/embedded.mobileprovision \
  --out /path/to/CookingGo_1.26.02.resigned.ipa
```

If you already have an entitlements plist:

```bash
bash tools/resign_ipa_recursive.sh \
  --ipa "/path/to/Cooking Go_1.26.02.ipa" \
  --identity "Apple Development: Your Name (TEAMID)" \
  --entitlements ./entitlements.plist \
  --out ./CookingGo_1.26.02.resigned.ipa
```

The analyzer parses Mach-O embedded CodeDirectory identifiers, hash types, flags and Team IDs. The important invariant is that the main executable and every embedded framework are signed consistently and the regenerated archive contains valid bundle/framework CodeResources. The previous broken installed state had:

```text
main executable: TeamIdentifier=not set
AdjustSdk.framework: TeamIdentifier=KT32KPGAK9
```

## One-click post-fix verification

After installing or preparing a fixed/resigned base IPA, use:

```powershell
python F:\测试\cookingGO\github-cookinggo-mod\tools\postfix_verify_12602.py `
  --mcp F:\测试\cookingGO\mcp.py `
  --install-ipa "F:\测试\cookingGO\dist\CookingGo_1.26.02.resigned.ipa" `
  --install-deb "F:\测试\cookingGO\dist\com.seagull.cookinggomod_1.3.4_iphoneos-arm64.deb" `
  --enable-rt `
  --out F:\测试\cookingGO\_work\postfix_verify_after_resign.json
```

Conservative behavior:

- if the base launch still has `Library Validation failed` or `dyld(6) code:1`, the script stops and skips DEB install / `rt=1`;
- it verifies default `rt=0` first;
- `--enable-rt` is required before the script writes `rt=1`;
- full logs go into the JSON report, while the console prints gate summaries.

Base-only current-state check:

```powershell
python F:\测试\cookingGO\github-cookinggo-mod\tools\postfix_verify_12602.py `
  --mcp F:\测试\cookingGO\mcp.py `
  --out F:\测试\cookingGO\_work\postfix_verify_base_current.json
```

Current broken package correctly reports:

```text
base_gate: {'ok': False, 'message': 'base launch failed dyld/library-validation gate'}
final: STOP: base game launch gate failed; DEB install/rt enable skipped
```

## Post-fix verification order

1. Install the clean/resigned IPA.
2. Launch the game without the tweak.
3. Run `device_launch_triage.py`; require no `Library Validation failed` and no `dyld(6) code:1`.
4. Confirm live `index.jsc` SHA if still using the supported static payload path.
5. Install `com.seagull.cookinggomod_1.3.4_iphoneos-arm64.deb`.
6. Validate default `rt=0` cfg and require a fresh `CookingGoMod v... loaded` marker after stale mailbox files are cleared.
7. Flip `rt=1` only after `rt=0` passes, then check `runtime evalString hook installed` and JS handshake files.
8. Only then continue with runtime injection tuning for 1.26.02 encrypted JSC.

## Do not do this while base game is broken

Do not overwrite the live app bundle `assets/scriptBundle/index.jsc` as a crash workaround. The current crash happens before JS execution, and bundle mutation only adds more signing noise.
