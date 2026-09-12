# CookingGo Mod — 1.25.03

iOS 16.x / arm64 / Dopamine (rootless) tweak for **Cooking GO 1.25.03**.

* Install target: `/var/jb/usr/lib/TweakInject/CookingGoMod.dylib`
* Bundle filter: `com.airplanecooking.chef.kitchen.restaurant.diner`
* Package id: `com.seagull.cookinggomod`, arch `iphoneos-arm64`

## 目标应用的引擎结论（静态分析，非猜测）

| 项 | 结论 | 证据 |
|---|---|---|
| 引擎 | **Cocos Creator 2.4.11 + cocos2d-x lite** | 二进制内字符串 `/Applications/Cocos/Creator/2.4.11/CocosCreator.app/Contents/Resources/cocos2d-x/cocos/scripting/js-bindings/auto/jsb_cocos2dx_auto.cpp`；`src/cocos2d-jsb.js`、`jsb-adapter/*` |
| JS 引擎 | **V8**（不是 JavaScriptCore，不是 IL2CPP） | 符号表 550 个 `_ZN2v8*`；启动参数 `--expose-gc-as=__jsb_gc__`；`se::ScriptEngine::evalString` / `runScript` 日志串 |
| 脚本 | 明文 JS，`encrypted:false`，无 `.jsc` | `assets/scriptBundle/config.json` |
| 业务代码 | `assets/scriptBundle/index.js`（5.26 MB / 775 个模块） | 模块表 `AICtr: [function(e,t,i){...}` |
| 模块系统 | `window.__require(name)`（IIFE 返回的 `o(s,r)`，多 bundle 链式回退） | `assets/scriptBundle/index.js` 第一行 |
| 玩家数据 | `__require("Game").default.PlayerData` | `Game` 模块 `_loadAllManagers()` 中 `ye.PlayerData = new b.default()` |
| 事件总线 | `__require("Core").default.Event` | `Core` 模块 `static get Event()` |
| 事件常量 | `__require("AppConst").EVENT_ID.UPDATE_GEM / UPDATE_COIN / UPDATE_POWER / UPDATE_AD_COUPON / UPDATE_PROP_NUM` | `AppConst` 模块 `i.EVENT_ID = {...}` |
| 免广告券 | prop id **57**（`EPropID.AdCoupon`），走 `setPropNum(57, n)` | `ServerConst` 枚举 + `PlayerDataMgr.setPropNum` |
| 文件读取路径 | `cocos2d::FileUtilsApple` → `[NSData dataWithContentsOfFile:]` | 二进制含 `N7cocos2d14FileUtilsAppleE`、`ResizableBuffer`、`getContents` |

> 本工程**不使用**任何 IL2CPP 方案（`il2cpp_class_from_name` / `FieldInfo` / 类偏移）。JS 对象没有固定内存布局。

## 数据流

```
点击悬浮球 → 面板输入 100 → 绿色 + / 蓝色 =
        ↓ 写入 <沙盒>/cookingmod/cmd.json      {"seq":N,"res":"gem","action":"add","value":100}
   JS bootstrap（已注入到同一 VM，250ms 轮询）
        ↓ __require("Game").default.PlayerData.gemNum = before + 100
        ↓ __require("Core").default.Event.emit(EVENT_ID.UPDATE_GEM, ...)
        ↓ 回写 res.json {before, after, expr} 与 state.json {gem,coin,power,adcoupon}
   原生读取回执 → 日志区打印「修改前 / 输入表达 / 修改后」并复核 state.json
```

## JS 注入点（分层，命中即用；payload 幂等）

1. `+[NSData dataWithContentsOfFile:]`
2. `+[NSData dataWithContentsOfFile:options:error:]`
3. `-[NSData initWithContentsOfFile:]`
4. `-[NSFileManager contentsAtPath:]`
5. `+[NSString stringWithContentsOfFile:encoding:error:]`
6. `fopen` / `fopen$DARWIN_EXTSN` / `open` / `openat` / `guarded_open_np` / `open_dprotected_np`
   （仅当运行时可取到 `MSHookFunction`，否则自动跳过，**不会**造成启动崩溃）

命中 `assets/scriptBundle/index.js` 时在文件内容末尾追加 `src/CGMBootstrap.js`。

## 构建

```bash
bash scripts/build.sh          # 需要 macOS + Xcode
```

产物：`outputs/com.seagull.cookinggomod_<version>_iphoneos-arm64.deb`

CI：`.github/workflows/build-deb.yml`（macos-15，自动打包 + 发布 Release）。

### Rootless / 只读根文件系统约束

* 包内只允许 `./var/jb/...` 与 `./DEBIAN/...` 两类顶层条目
* 排除 `.DS_Store`、`._*`、`__MACOSX`、`.dSYM`
* 用 `dpkg-deb --root-owner-group -Zgzip`（gzip 兼容性最好）
* `tools/verify_deb.sh` 会在构建最后自动校验以上规则，失败即构建失败

## 安装

```bash
scp outputs/*.deb root@<device>:/var/mobile/Documents/
ssh root@<device> 'dpkg -i /var/mobile/Documents/<deb>'
# 然后重启游戏进程；必要时 sbreload
```

## 使用

1. 启动游戏，右上角出现绿色圆形悬浮球（可拖动）。
2. 点球展开面板，选择资源（钻石 / 金币 / 燃油 / 免广告券）。
3. 输入框只填数字，例如 `100`。
4. 绿色 `+` = 当前值 + 输入值；蓝色 `=` = 直接赋值。
5. 日志区输出：

```
资源: 钻石
修改前: 1
输入表达: 1 + 100
修改后: 101
```

6. `自检` 按钮会 dump 运行时探针（`__require` / `Game.default` / `EVENT_ID` / `playerInfo` 字段数）到日志区与 `probe.json`。

## 日志与取证文件（应用沙盒内）

```
<app container>/Documents/cookingmod/
    mod.json      原生写入的桥标记
    js_hello.json JS bootstrap 握手（含注入版本）
    cmd.json      原生 → JS 指令
    res.json      JS → 原生回执（before / expr / after）
    state.json    JS 周期性写入的四个资源当前值
    probe.json    运行时自检结果
    mod.log       原生侧日志
```

## 版本约定

`packaging/control` 的 `Version:` 是唯一版本源，构建时通过 `-DCGM_VERSION` 注入 dylib。
每次修复必须递增。

## 免责

仅用于自有设备 / 自有账号的技术研究与验证。