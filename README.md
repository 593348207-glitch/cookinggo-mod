# CookingGo Mod — Cooking GO 1.25.03

iOS 16.2 / arm64 / Dopamine rootless tweak. **Latest: 1.2.0**

* Install: `/var/jb/usr/lib/TweakInject/CookingGoMod.dylib` (+ `.plist`, `.cfg`, `.bootstrap.js`)
* Bundle filter: `com.airplanecooking.chef.kitchen.restaurant.diner`
* Package id: `com.seagull.cookinggomod`, arch `iphoneos-arm64`

## Verified on device (iPhone12,2 / iOS 16.2 / Dopamine)

| item | status |
|---|---|
| game launches, no crash | PASS |
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
| scripts | plain JS, `encrypted:false`, zero `.jsc` | `assets/scriptBundle/config.json` |
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

Working approach, used since 1.0.5: **`DEBIAN/postinst` appends `CookingGoMod.bootstrap.js` to the
on-disk `index.js` as root**, keeping a pristine copy at
`/var/mobile/Library/Caches/cookingmod/index.js.orig`. `DEBIAN/postrm` restores it.
The ObjC hooks remain in the dylib for diagnostics only (`objc=0` disables them).

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
```

## Bridge (inside the app sandbox)

`<container>/Documents/cookingmod/`

| file | direction |
|---|---|
| `js_hello.json` | JS -> native handshake |
| `state.json` | JS -> native, current values of all five resources |
| `cmd.json` | native -> JS `{seq,res,action,value}` |
| `res.json` | JS -> native `{before,after,expr,ok}` |
| `ui_cmd.json` | native -> JS UI commands (panel open/close) |
| `ui_state.json` | native -> file, real frames (ball/panel/input/stage) |
| `hits.json` | native -> file, hook and touch counters |
| `ball_pos.json` | native -> file, persisted ball position |
| `probe.json` | JS -> file, runtime self-check |
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