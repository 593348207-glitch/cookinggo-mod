# CookingGo Mod — Cooking GO 1.25.03/1.26.02

iOS 16.2 / arm64 / Dopamine rootless tweak. **Latest: 1.3.2**

* Install: `/var/jb/usr/lib/TweakInject/CookingGoMod.dylib` (+ `.plist`, `.cfg`, `.bootstrap.js`)
* Bundle filter: `com.airplanecooking.chef.kitchen.restaurant.diner`
* Package id: `com.seagull.cookinggomod`, arch `iphoneos-arm64`

## Verified on device (iPhone12,2 / iOS 16.2 / Dopamine)

| item | status |
|---|---|
| game launches, no crash | PASS on 1.25.03; 1.26.02 current IPA launch fails before JS due Library Validation / dyld |
| floating ball visible, draggable, snaps to edge | PASS |
| panel layout correct in the game's landscape orientation | PASS |
| 钻石 / 金币 / 燃油 / 免广告券 / 换装币 | PASS (all five) |
| logs `修改前 / 输入表达 / 修改后` | PASS |
| survives game restart (persistence) | PASS |

## Engine (static analysis, not guesswork)

| item | finding | evidence |
|---|---|---|
| engine | **Cocos Creator 2.4.11 + cocos2d-x lite** | binary string `/Applications/Cocos/Creator/2.4.11/.../jsb_cocos2dx_auto.cpp`; `src/cocos2d-jsb.js`; `jsb-adapter/*` |
| script VM | **V8** (not JavaScriptCore, not IL2CPP) | 550 `_ZN2v8*` symbols; `--expose-gc-as=__jsb_gc__`; `se::ScriptEngine::evalString` |
| scripts | 1.25.03 plain `index.js`; 1.26.02 encrypted/gzipped XXTEA `index.jsc` | `assets/scriptBundle/config.json` |
| module system | `window.__require(name)` over 775 modules in `assets/scriptBundle/index.js` | first line of that file |
| singleton root | **`__require("Manager").default`** | keys include `PlayerData`, `MapData`, `ServerData`, `Auth`, `Pay`, ... |
| event bus | `__require("Core").default.Event` | `Core` module `static get Event()` |
| constants | `__require("AppConst").EVENT_ID` | `AppConst` module |
| script read path | `cocos2d::FileUtilsApple` -> POSIX/fstream (NOT the ObjC file APIs) | hook-hit telemetry on device |

**`__require("Game")` is a trap** — it is the scene `cc.Component`, not the data holder. Its keys are only
`["$super","_sealed","__props__","__values__"]`. The manager singleton lives in `"Manager"`.

## Resources

| key | field | write | refresh event |
|---|---|---|---|
| `gem` | `PlayerData.gemNum` | `PD.gemNum = v` | `UPDATE_GEM` |
| `coin` | `MapData.mapCoinNum` | `MD.mapCoinNum = v` | `UPDATE_COIN`, `UPDATE_MAXMAP_COIN` |
| `power` | `PlayerData.powerNum` | `PD.powerNum = v` | `UPDATE_POWER` |
| `adcoupon` | `PlayerData.adCouponNum` | `PD.setPropNum(57, v)` | `UPDATE_AD_COUPON`, `UPDATE_PROP_NUM` |
| `cloth` | `PlayerData.clothingCionNum` | `PD.setPropNum(45, v)` | `UPDATE_CLOTHINGCOIN`, `UPDATE_PROP_NUM` |

`EPropID` values confirmed in `scriptBundle/index.js`: `ClothNum = 45`, `AdCoupon = 57`.
`clothingCionNum` is a **getter only** (`getPropNum(EPropID.ClothNum)[EIdIdx.val]`), so writes must go
through `setPropNum`, exactly like the ad coupon.

Setters are used instead of `addGem` / `addPowerNum` / `addCoin` on purpose: those carry
`ClientData.cheatTimes++` / `CheckCheatMgr.isCheatByPay()` thresholds. The setters persist by
themselves (`ServerData.savePlayerInfo` / `saveMapInfo`).

## How the JS gets in (important)

The game **does not** read `assets/scriptBundle/index.js` through `+[NSData dataWithContentsOfFile:]`,
`-[NSFileManager contentsAtPath:]` or `-[NSString initWithContentsOfFile:encoding:error:]`.
On-device hook-hit telemetry (v1.0.4) recorded hundreds of hits on those APIs but **none** for the
target file, and hooking the POSIX `open` family killed the process during startup.

Working approach for 1.25.03, used since 1.0.5: **`DEBIAN/postinst` appends `CookingGoMod.bootstrap.js` to the
on-disk `index.js` as root**, keeping a pristine copy at
`/var/mobile/Library/Caches/cookingmod/index.js.orig`. `DEBIAN/postrm` restores it.
The ObjC hooks remain in the dylib for diagnostics only (`objc=0` disables them).

For 1.26.02, `index.jsc` is encrypted/gzipped XXTEA. v1.3.1 ships a statically verified patched JSC payload for CI/package closure, but **postinst deliberately leaves the live signed app bundle unchanged**. Direct live mutation of the app bundle can break the install/signature state; runtime injection must move to a decrypted-buffer / Cocos script-engine hook before launch.

Because the pod is re-signed after a game update, **re-run `dpkg -i` after updating the game**; the
runtime logs a warning if the bootstrap is missing.

## Runtime config

`/var/jb/usr/lib/TweakInject/CookingGoMod.cfg`, read once at load:

```
objc=1     ObjC file-API hooks (diagnostics only)
posix=0    POSIX open-family hooks - KILLS THIS GAME. Keep 0.
overlay=1  floating ball + panel
panel=0    open the panel at launch
rot=0      overlay rotation; game and overlay are both landscape, so 0
vlog=0     mirror native diagnostics into the on-screen log; 0 = results only
iap=0      seed monthly-card/IAP hook state; default off, panel can toggle runtime state
rt=0       experimental 1.26.02 ScriptEngine::evalString runtime bootstrap hook; default off
```

## Bridge (inside the app sandbox)

`<container>/Documents/cookingmod/`

| file | direction |
|---|---|
| `js_hello.json` | JS -> native handshake |
| `state.json` | JS -> native, current values of all five resources + IAP/VIP state |
| `cmd.json` | native -> JS `{seq,res,action,value}` |
| `res.json` | JS -> native `{before,after,expr,ok}` |
| `ui_cmd.json` | native -> JS UI commands (panel open/close) |
| `ui_state.json` | native -> file, real frames (ball/panel/input/stage) |
| `hits.json` | native -> file, hook and touch counters |
| `ball_pos.json` | native -> file, persisted ball position |
| `probe.json` | JS -> file, runtime self-check |
| `iap_hook.json` | JS/native persisted independent IAP hook switch |
| `mod.log` | native diagnostics (never surfaced in the UI) |

## Build

```bash
bash scripts/build.sh          # macOS + Xcode
```

Artifact: `outputs/com.seagull.cookinggomod_<version>_iphoneos-arm64.deb`.
CI: `.github/workflows/build-deb.yml` (macos-15, builds and publishes a Release).
`tools/verify_deb.sh` runs at the end of every build and fails on structural problems.

### Rootless constraints honoured

* only `./var/jb/...` and `./DEBIAN/...` at the top level
* no `.DS_Store`, `._*`, `__MACOSX`, `.dSYM`
* `dpkg-deb --root-owner-group -Zgzip`
* `control` ends with a newline (dpkg-deb rejects it otherwise)

## Install / uninstall

```bash
dpkg -i com.seagull.cookinggomod_<ver>_iphoneos-arm64.deb   # as root
dpkg -r com.seagull.cookinggomod                            # restores index.js
```
## 1.26.02 launch-failure closure

Current device state (2026-09-13): the game exits before JS/bootstrap. This is not caused by `CookingGoMod.bootstrap.js` or the patched `index.jsc` payload. Evidence:

- tweak package was removed and live `assets/scriptBundle/index.jsc` SHA-256 is still the original `cb1825d4c535f77de8cafbec1d4b73e65d10f43835d04cb091c856b4967269d0`;
- launch log shows `RBSProcessExitStatus| domain:dyld(6) code:1`;
- kernel log shows `Library Validation failed: Rejecting .../Frameworks/AdjustSdk.framework/AdjustSdk ... for process ... (Team ID: none, platform: yes), reason: mapping process is a platform binary, but mapped file is not`;
- `ldid -h` on the installed main executable reports `TeamIdentifier=not set`, while `AdjustSdk.framework` reports `TeamIdentifier=KT32KPGAK9`;
- the supplied 1.26.02 IPA has no `.app/_CodeSignature/CodeResources`, and all 23 embedded frameworks are missing framework `_CodeSignature/CodeResources` entries in the archive; the static analyzer also reports `Signing team IDs: <none>` / `Binaries with empty Team ID: 24`.

Repro tools:

```powershell
python F:\测试\cookingGO\github-cookinggo-mod\tools\analyze_ipa_closure.py --ipa F:\测试\cookingGO\Cooking Go_1.26.02.ipa
python F:\测试\cookingGO\github-cookinggo-mod\tools\device_launch_triage.py --mcp F:\测试\cookingGO\mcp.py --out F:\测试\cookingGO\_work\device_launch_triage_12602.txt
```

Fix helper for macOS recursive re-signing:

```bash
bash tools/resign_ipa_recursive.sh --ipa "Cooking Go_1.26.02.ipa" --identity "Apple Development: Name (TEAMID)" --provision embedded.mobileprovision --out CookingGo_1.26.02.resigned.ipa
```

Full notes: `docs/CRASH-TRIAGE-12602.md`, `docs/SIGNING-FIX-12602.md`, and `docs/RUNTIME-HOOK-12602.md`.

Verdict: the immediate crash root is signing/library-validation/dyld loading state of the installed 1.26.02 app bundle. The mod DEB static closure is clean; do not write the live `index.jsc` while this dyld issue is unresolved.

## 1.3.1/1.3.2 月卡/IAP Hook + 1.26.02 encrypted JSC/runtime hook

- 新增独立运行期开关：面板按钮 `内购:关/开`，状态持久化到 `<container>/Documents/cookingmod/iap_hook.json`。
- 新增按钮 `免费月卡`：直接触发已定位的月卡发放链路 `Manager.VipCard.setPlayerVipDataByGiftId(...)`，随后 `saveVipCardData(false)` 并刷新相关 UI event。
- JS hook 点：`Manager.Pay.pay(purchaseTbl, callbacks)`；开关开启时只接管 VIP/月卡 purchaseId（优先月卡 `87`，兼容 `86/82/89/90/91`），普通商品仍走原始支付逻辑。
- 辅助 hook 点：`YiFaniOSIAPBridge.buyProduct(sku, onDone, onValidate)`；仅在 SKU 命中 vip/month/card 关键词时返回本地成功。
- 默认配置 `iap=0`，不改变 1.2.0 既有资源修改、overlay、postinst/postrm 行为。

验证文件：`state.json` 会增加 `iapHook`、`iapHookInstalledPay`、`iapHookInstalledIOS`、`vip` 字段；`probe.json` 会增加 `hasPay`、`hasYiFaniOS`、`vip`。

- 1.26.02 support: package carries `CookingGoMod.index12602.jsc` for static verification. `postinst` only verifies/backs up/reports the supported original JSC and leaves the live app bundle unchanged.
- Added default-off runtime evalString hook skeleton: `rt=1` hooks the 1.26.02 candidate at image-base offset `0x1c28a48` and evals `CookingGoMod.bootstrap.js` once after the original script evaluation. Keep `rt=0` until the base game signing issue is fixed.


## 1.3.1/1.3.2 静态闭环验证

- 新 IPA SHA-256：`8fd0e3a5259f8561773fb6a60db5aaf21c57ab44df1487b9981018f865057710`。
- `1.26.02` 的 `scriptBundle/config.json` 为 `encrypted:true`，运行时脚本是 `index.jsc`；不再尝试把 JS 文本追加到 `index.jsc`。
- 工具 `tools/patch_cocos_jsc.py` 完成 XXTEA → gzip 解包、追加 bootstrap、gzip → XXTEA 回封，并执行 round-trip self-check。
- 静态包验收：`dpkg-deb -f`、`dpkg-deb -c`、`tools/verify_deb.sh` 均通过；目标 DEB SHA-256：`2D7F44A0EDC1E3F8465EC62AFE933EE4825055357EF90517DACA19B687486FD9`。
- 设备侧已确认原始 `index.jsc` SHA-256 为 `cb1825d4c535f77de8cafbec1d4b73e65d10f43835d04cb091c856b4967269d0`；旧版路径未被错误修改。
