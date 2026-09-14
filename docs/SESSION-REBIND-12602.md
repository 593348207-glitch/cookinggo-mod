# Cooking GO 1.26.02 Session-aware Rebind

更新时间：2026-09-14

## 目标

让资源命令、月卡测试和 IAP UI 的 bridge 不再把第一次登录得到的 `Manager`、`PlayerData`、`Pay`、`VipCard` 或 mailbox receipt 当成永久对象。每次 heartbeat 都重新取当前模块对象；检测到账号/对象变化时递增 `sessionGen`、清理旧回执、恢复旧对象上的 wrapper，并对新对象重新安装 hook。

## JS 实现

文件：`src/CGMBootstrap.js`

- `sessionFingerprint()` 只在内存中使用稳定身份字段（`uid/userId/playerId/accountId/roleId/openId/openid/id`）和对象引用标签，不把 token 写入 mailbox。
- `bind()` 每轮重新读取 `Manager.default`、`PlayerData`、`MapData`、`Pay`、`VipCard` 与 `YiFaniOSIAPBridge`；引用或身份指纹变化时触发 session rebind。
- `resetSessionState()` 递增 `sessionGen`，重置 JS command/probe 去重，清理 `cmd/res/state/probe/probe_cmd`，写入 fresh `js_hello.json`，并保留独立的 `iap_hook.json` 开关。
- `installIapHook()` 记录 `gHookedPay/gHookedIOS`；切换对象时恢复旧方法，再给新对象安装 wrapper，避免旧账号对象继续持有闭包。
- `snapshot()`、`probe()`、`res.json`、`iap_hook.json` 都携带 `sessionGen/sessionKey`；带旧 `sessionGen` 的 command 被拒绝。

## Native bridge 实现

文件：`src/CookingGoMod.m`

- `CGMSendCommand()` 在发送前重新解析 active mailbox，并把当前 `sessionGen` 写入 command。
- `CGMTick()` 每轮检查 mailbox 路径和 `js_hello/state` 的 `sessionGen`；账号切换或 runtime rebind 时重置 native 的 `gLastSeq/gPendingSeq/gEngineState`。
- 收到旧 session 的 `res.json` 时丢弃，不再把旧账号回执显示到当前 UI。
- command 等待超过 3 秒时在 `mod.log` 和面板显示诊断信息，说明当前 session/mailbox，不再无限显示等待。
- 修复 `CGMSendCommand()` 处工作副本中的字面量 `` `r`n ``，恢复为正常 Objective-C 语句。

## 本地验证

```powershell
Set-Location F:\测试\cookingGO\github-cookinggo-mod
node --check src\CGMBootstrap.js
node tools\mock_cgm_bootstrap.js
python -m py_compile tools\*.py
python tools\embed_js.py
python tools\patch_cocos_jsc.py --input "F:\测试\cookingGO\Cooking Go_1.26.02.ipa" --key "75fa5f0d-2c43-45" --bootstrap src\CGMBootstrap.js --output packaging\CookingGoMod.index12602.jsc --dump-js "F:\测试\cookingGO\_work\CookingGoMod.index12602.patched.js"
python tools\static_verify_12602.py --ipa "F:\测试\cookingGO\Cooking Go_1.26.02.ipa" --deb "F:\测试\cookingGO\dist\com.seagull.cookinggomod_1.3.8_iphoneos-arm64-js-test.deb" --repo "F:\测试\cookingGO\github-cookinggo-mod"
```

当前 Node harness 结果：`13/13 tests passed`，包括账号 A→B→A 的资源隔离、Pay hook 恢复/重装、月卡 test double、旧 session command 拒绝。

静态闭环结果：

- patched JSC SHA-256：`445045da019b47e8522c661a80431da324057b0f5ad78cb181c01251adfee494`
- Windows 静态测试 DEB：`F:\测试\cookingGO\dist\com.seagull.cookinggomod_1.3.8_iphoneos-arm64-js-test.deb`
- DEB SHA-256：在本轮打包后以 `Get-FileHash` 读取；`static_verify_12602.py` 输出 `deb version: 1.3.8`、`packaged cfg rt: rt=0`、`static closure: OK`。

## 构建边界

Windows 工作区没有 Xcode/iphoneos SDK/`ldid`，所以本轮的 `-js-test` 包由既有 1.3.7 dylib 复用，仅替换当前 JS/JSC/control，用于静态和 mailbox 结构验证；`src/CookingGoMod.m` 的新增 native 逻辑必须在 macOS workflow 重新编译后才算最终设备包。GitHub Actions workflow 位于 `.github/workflows/build-deb.yml`，macOS runner 会执行 `scripts/build.sh` 并产出正式 `outputs/com.seagull.cookinggomod_1.3.8_iphoneos-arm64.deb`。

## 真机证据状态

设备：iPhone14,5 / iOS 15.6.1 / rootless，bundle `com.airplanecooking.chef.kitchen.restaurant.diner`。

本轮已完成：

- 设备唤醒、安装 `1.3.8-js-test` DEB、启动游戏；base launch gate：`lv=0`、`dyld=0`。
- 安装日志显示 `dpkg` 成功设置 `com.seagull.cookinggomod (1.3.8)`。
- 设备当前 mailbox 的 `js_hello.json`/`bootstrap.js` 仍为 `1.3.7`，因为包内 dylib 是复用的旧二进制；因此这次设备操作不能作为新 session-aware JS/native 逻辑的生效证明。
- 设备报告：`F:\测试\cookingGO\_work\postfix_verify_12602_v138_js_test_current.json`；该报告明确为 `STOP: rt=0 tweak smoke gate failed; fresh tweak load marker not observed`，不能把它记作新版本 PASS。

最终设备验收必须使用 macOS 编译出的正式 1.3.8 dylib/DEB，依次保存 fresh `js_hello.json`、`state.json`、`probe.json`、`res.json`、`mod.log` 与 UI 截图，再执行 A→B→A 账号切换复测。
