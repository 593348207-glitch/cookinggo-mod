# Cooking GO 1.26.02 launch failure triage

Date: 2026-09-13

## Verdict

The current open-and-immediately-exit state is closed as a dyld/library-validation failure in the installed game bundle, not a JavaScript or `index.jsc` mutation failure.

## Device evidence

Current app info:

```text
bundle_id: com.airplanecooking.chef.kitchen.restaurant.diner
short_version: 1.26.02
sdk_version: 26.2
minimum_os_version: 13.0
bundle_path: /var/containers/Bundle/Application/9CE36101-F008-4C6A-9D05-99E548D1F76A/AirplaneCooking-mobile.app
data_container: /var/mobile/Containers/Data/Application/D6A82294-330C-4C26-B707-A811C09861DE
```

The live script is original and readable:

```text
-rw-r--r-- 1 _installd _installd 880072 ... assets/scriptBundle/index.jsc
sha256 cb1825d4c535f77de8cafbec1d4b73e65d10f43835d04cb091c856b4967269d0
```

The installed bundle lacks these archive-level signature resources:

```text
.app/_CodeSignature: missing
.app/_CodeSignature/CodeResources: missing
.app/embedded.mobileprovision: missing
```

Launch log around `2026-09-13 13:41:14 +0800`:

```text
Bootstrap success!
Library Validation failed: Rejecting '/private/var/containers/Bundle/Application/.../AirplaneCooking-mobile.app/Frameworks/AdjustSdk.framework/AdjustSdk' (Team ID: KT32KPGAK9, platform: no) for process 'AirplaneCooking-(19983)' (Team ID: none, platform: yes), reason: mapping process is a platform binary, but mapped file is not
termination reported by launchd (6, 1, 6)
RBSProcessExitStatus| domain:dyld(6) code:1
```

Installed signature headers:

```text
main AirplaneCooking-mobile:
  CodeDirectory flags=0x0(none)
  TeamIdentifier=not set

Frameworks/AdjustSdk.framework/AdjustSdk:
  Authority=Apple iPhone OS Application Signing
  TeamIdentifier=KT32KPGAK9
```

## Static IPA evidence

`tools/analyze_ipa_closure.py` output for `F:\测试\cookingGO\Cooking Go_1.26.02.ipa`:

```text
IPA sha256: 8fd0e3a5259f8561773fb6a60db5aaf21c57ab44df1487b9981018f865057710
App _CodeSignature/CodeResources: False entries=0
embedded.mobileprovision: False
Embedded framework binaries: 23
Framework CodeResources missing: 23/23
Missing non-system @rpath deps: 0
Signing team IDs: <none>
Binaries with empty Team ID: 24
Closure verdict: PASS for non-system @rpath dependencies, WARN for missing CodeResources/signing resources.
```

Main executable Mach-O facts:

```text
arch: arm64
build platform: iOS
minos: 13.0.0
sdk: 26.2.0
LC_ENCRYPTION_INFO_64 cryptid: 0
LC_CODE_SIGNATURE: present
rpaths: /usr/lib/swift, @executable_path/Frameworks, @loader_path/Frameworks
```

## Conclusion

The process starts and reaches FrontBoard bootstrap, then dyld/library validation rejects an embedded framework before app JS logic can run. Since the tweak is uninstalled and the live `index.jsc` matches the original SHA-256, the crash is outside the current DEB feature code.

Next fix path is to install a consistently signed 1.26.02 app bundle: either a clean App Store/TestFlight install or a recursively re-signed bundle where the main executable and all embedded frameworks share a compatible signing identity/entitlement state. Only after the base game launches should the tweak/runtime injection path be validated.

## Reproduction commands

```powershell
python F:\测试\cookingGO\github-cookinggo-mod\tools\analyze_ipa_closure.py --ipa F:\测试\cookingGO\Cooking Go_1.26.02.ipa
python F:\测试\cookingGO\github-cookinggo-mod\tools\device_launch_triage.py --mcp F:\测试\cookingGO\mcp.py --out F:\测试\cookingGO\_work\device_launch_triage_12602.txt
python F:\测试\cookingGO\github-cookinggo-mod\tools\static_verify_12602.py --ipa F:\测试\cookingGO\Cooking Go_1.26.02.ipa --deb F:\测试\cookingGO\dist\com.seagull.cookinggomod_1.3.2_iphoneos-arm64.deb --repo F:\测试\cookingGO\github-cookinggo-mod
```
