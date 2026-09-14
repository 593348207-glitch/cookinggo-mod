# Cooking GO Mod 项目交接

> 更新时间：2026-09-14
> 继续开发目录：`F:\测试\cookingGO\github-cookinggo-mod`
> 分支：`codex/iap-month-card-hook`
> HEAD：`a93d85b Require fresh JS handshake for runtime verifier`
> 当前工作区：`src\CGMBootstrap.js`、`src\CookingGoMod.m` 有未提交修改；修改前先检查 `git diff`。

## 1. 项目目标

维护 Cooking GO `1.26.02` 的 iOS rootless Mod：保留钻石、金币、燃油、广告券、换装币、悬浮球/面板；重构为**账号无关、会话可重绑**，切换账号、重启游戏后仍能使用资源功能、月卡测试和 IAP UI。

## 2. 当前目录结构

```text
F:\测试\cookingGO\
├─ Cooking Go_1.26.02.ipa      # 目标 IPA
├─ github-cookinggo-mod\       # 当前 Git 开发目录（本交接文件所在处）
│  ├─ src\                     # Objective-C tweak + JS bootstrap
│  ├─ packaging\               # deb/control/cfg/plist/内置 JSC
│  ├─ tools\                   # JSC、IPA、DEB、设备验证工具
│  ├─ docs\                    # 签名、闪退、runtime/IAP 证据
│  └─ scripts\                 # macOS/Xcode 构建脚本
├─ dist\                      # DEB 产物
├─ _extract\                  # IPA 解包临时目录
├─ _work\                     # 解密、报告、设备验证结果
├─ mod\                       # 历史同步副本
└─ mcp_65.py                  # 新设备 MCP 客户端
```

## 3. 正在开发功能

- **Session-aware JS rebind**：每轮 heartbeat/command poll 重新获取 `Manager/PlayerData/MapData/Pay/VipCard`；对象变化时重绑、重装 Hook、递增 `sessionGen`、清理旧 mailbox 状态。
- **Native mailbox 重发现**：检测 `sessionGen`、mailbox 被清理或写入失败时重新执行 `CGMResolveActiveMailbox()`，重置 `gLastSeq/gEngineState`。
- **资源功能稳定化**：五类资源走 `PlayerData/MapData/setPropNum` setter + event，避免依赖旧 JS 对象；目标是账号切换后重新绑定仍可执行。
- **月卡测试**：`vip_card` 命令调用 `VipCard.setPlayerVipDataByGiftId()` + `ServerData.saveVipCardData(false)`；商品 ID 仍需通过商品表/真实回调确认，不能继续盲猜。
- **IAP 开关 UI**：按钮先 optimistic 更新为“内购:开/关”，随后由 `state/res` 校正；不能永久停在“等待 JS 回执”。
- **等待超时诊断**：资源/IAP 命令超过约 3 秒无回执时显示会话、JS、mailbox 不一致，而不是无限等待。

## 4. 正在开发的功能区

1. `CGMBootstrap.js`：bind、heartbeat、mailbox、资源 setter、IAP/月卡 Hook。
2. `CookingGoMod.m`：runtime `evalString` 注入、mailbox、命令/回执、悬浮窗和 UI 状态。
3. `packaging/`：配置、生成 JSC、DEB 打包；版本/源码/JSC/DEB 必须一致。
4. `tools/mock_cgm_bootstrap.js`：补账号切换、对象替换、Pay/VipCard 重绑回归。
5. 新设备运行时验证：MCP `http://192.168.125.65:8090/mcp`，先确认注入和 fresh mailbox，再做功能测试。

## 5. 关键技术

- iOS arm64、rootless、ElleKit/TweakInject；Objective-C + JavaScript。
- 游戏引擎：Cocos Creator `2.4.11` + cocos2d-x lite + V8；不是 IL2CPP。
- `assets/scriptBundle/index.jsc` 为 `encrypted:true`，静态链为 XXTEA → gzip → JS；不要直接改 live signed bundle。
- 运行时注入：`ScriptEngine::evalString` image-base offset `0x1c28a30`；`ScriptEngine::getInstance` 候选 `0x1c263cc`。
- 数据入口：`__require("Manager").default`，包含 `PlayerData/MapData/ServerData/Pay/VipCard`；事件总线为 `__require("Core").default.Event`。
- mailbox：`Documents/cookingmod/{cmd,res,state,js_hello,probe,iap_hook,ui_state}.json`。

## 6. 重要文件说明

- `F:\测试\cookingGO\github-cookinggo-mod\src\CGMBootstrap.js`：JS 主逻辑；当前工作副本版本字符串为 `1.3.9`。
- `F:\测试\cookingGO\github-cookinggo-mod\src\CookingGoMod.m`：native tweak、UI、命令/回执、runtime Hook；当前工作副本版本字符串为 `1.3.9`。
- `F:\测试\cookingGO\github-cookinggo-mod\src\CGMBootstrap.generated.h`：JS 嵌入头，源码变化后必须重新生成。
- `F:\测试\cookingGO\github-cookinggo-mod\packaging\CookingGoMod.index12602.jsc`：打包 JSC；由 `tools/embed_js.py`、`tools/patch_cocos_jsc.py` 生成。
- `F:\测试\cookingGO\github-cookinggo-mod\packaging\CookingGoMod.cfg`：当前 `objc=1,posix=0,overlay=1,panel=0,rot=0,vlog=0,iap=0,rt=0`。
- `F:\测试\cookingGO\github-cookinggo-mod\tools\mock_cgm_bootstrap.js`：本地 Node mock；先用它验证会话切换再上设备。
- `F:\测试\cookingGO\github-cookinggo-mod\tools\static_verify_12602.py`：DEB/JSC/config 静态闭环。
- `F:\测试\cookingGO\github-cookinggo-mod\tools\postfix_verify_12602.py`：真机 mailbox/runtime 验证。
- `F:\测试\cookingGO\mcp_65.py`：新设备 MCP JSON-RPC 客户端；设备锁屏时先 `wake_and_home`。
- `F:\测试\cookingGO\github-cookinggo-mod\docs\IAP-RICHES-STATIC-12602.md`：商品与财富日历静态证据。

## 7. 已知问题

- 旧 iPhone12：切换账号重新登录后出现“等待 JS 回执”，资源和月卡失效；说明旧方案缓存了旧 `Manager/Pay/VipCard` 或旧 mailbox/session，不能继续作为单账号方案。
- 新设备 iPhone14,5 / iOS 15.6.1 / rootless：此前无 `js_hello.json/state.json/probe.json/mod.log`，且未确认重启越狱后的注入是否真正加载；当前设备验证尚未通过。
- 当前工作副本有**未完成的 1.3.8 修改**：`CookingGoMod.m` 的 `CGMSendCommand` 附近曾被错误替换，当前仍需先检查第 726 行是否含字面量 `` `r`n ``；修复后再生成头文件/JSC、编译和打包。
- `iap=0/rt=0` 是默认配置；IAP/月卡不能宣称已生效，必须有 fresh `js_hello/state/res/mod.log` 和真实 UI/功能证据。
- `postinst` 不得直接修改 live 加密/签名 `index.jsc`；启动闪退曾由 `AdjustSdk.framework/AdjustSdk` Team ID/Library Validation 不一致引起。
- Windows 不能真实编译 iOS dylib；`scripts/build.sh` 依赖 macOS + Xcode + iphoneos SDK + `ldid`。

## 8. 下一步需要做什么

1. 先读取本文件、`F:\ObsidianMemory\02-Projects\Cooking-Go-Mod.md`，执行 `git status`、`git diff --check`，修复 `CookingGoMod.m:726` 的异常字面量；不要丢弃用户修改。
2. 完成 JS session-aware rebind、Pay/IAP/VipCard 按对象变化重装 Hook、`sessionGen` 和旧 mailbox 清理。
3. 完成 native mailbox 重发现与命令超时 UI；补 optimistic IAP UI 后的回执校正。
4. 扩展 `tools/mock_cgm_bootstrap.js`：Manager/PlayerData/Pay/VipCard 替换、seq 重置、账号 A→B→A 的资源/月卡回归。
5. 运行 `node --check`、mock、`py_compile`、`embed_js.py`、JSC round-trip、`static_verify_12602.py`；然后在 macOS 构建 dylib/DEB。
6. 新 MCP 设备按顺序验证：注入 → fresh mailbox → 五类资源 → IAP UI → 月卡 → 账号切换 → 重启复测。证据保存到 `F:\测试\cookingGO\_work\`。
7. 只有所有回归通过后才更新 README、版本号、DEB、SHA-256，并同步 `F:\测试\cookingGO\mod`。


## 2026-09-14 1.3.9 礼包链路与真机安装结果

- Commit：`0ba1cd8 Fix local Riches test button declaration`，已推送 `main` 与 `codex/iap-month-card-hook`。
- GitHub Actions main run：`34848893985`，页面显示完成；正式 DEB：`F:\测试\cookingGO\dist\com.seagull.cookinggomod_1.3.9_iphoneos-arm64.deb`。
- 正式 DEB SHA-256：`7495BF04A261A52C20C3EA7A2697B9D935C72B38E1AFBA5862BE26C74AFE5934`。
- 设备安装：`dpkg -i` 返回 `exitCode=0`，`dpkg -s` 为 `Status: install ok installed`、`Version: 1.3.9`。安装输出里的旧 postrm 对 live signed `index.jsc` 的回写尝试被系统 `Operation not permitted` 拒绝；postinst 随后按预期保留 live bundle，使用 runtime injection。
- fresh 真机报告：`F:\测试\cookingGO\_work\package-chain-139-fresh.json`。`base_gate`、`rt0_gate`、`rt1_gate` 均 PASS；`lv=0`、`dyld=0`、无闪退。fresh log 确认 `CookingGoMod v1.3.9`、`runtime evalString hook installed`、`runtime evalString bootstrap OK`；fresh `js_hello/state/probe` 均为 `version=1.3.9`，`state.ready=true`、`sessionGen=1`。
- 真机 `probe.json` 已读到真实运行时 `iapCatalog`：真实 purchase rows 共 150 条左右，包含 `ID/Price/ProductID/RewardID`；Riches rows 为 `GiftType=28`、`Gift ID 28/31/32`，其中运行时 `PurchaseId[]` 仍需按回执完整读取，不把价格相同商品当作财富日历礼包。
- local-only 真机命令尚未执行：设备在写入时先处于锁屏，唤醒后 mailbox `cmd.json` 仍因设备侧 `Operation not permitted` 无法写入，未产生 `res.json`，`payTotal` 保持 `0`。没有操作 StoreKit、没有生成真实订单。
- 本地 mock 已通过 `21/21 tests passed`；静态验证 `static closure: OK`。


## 9. 不能改动 / 需要注意的约束

- 不把 JS receipt 当唯一成功条件；不得无限显示“等待 JS 回执”。
- 不缓存跨账号的 `Manager/PlayerData/Pay/VipCard`、旧 `sessionGen`、旧 seq 或旧 mailbox 状态。
- 不盲猜商品 ID、SKU、RewardId、回调名；静态证据和真机证据分开记录。
- 不直接改 live signed/encrypted `index.jsc`；默认 `iap=0`、`rt=0`，除非验证阶段明确切换。
- 修改源码后同步生成 `CGMBootstrap.generated.h`、packaged JSC 和 DEB，并跑静态验证。
- 保留现有资源修改、悬浮窗、rootless 配置和历史用户改动；先看 `git status`。
- 不保存设备 root 密码、账号、token、Apple 凭据或其他敏感信息到仓库/Obsidian。
- 真机命令必须先确认设备亮屏；任何“已生效”结论必须附 mailbox/log/UI 证据。

## 新会话首条提示词

```text
读取 F:\测试\cookingGO\github-cookinggo-mod\PROJECT_HANDOFF.md，并以它作为唯一当前上下文。继续 Cooking GO 1.26.02 Mod 的账号无关重构：先检查 git status/diff，修复 CookingGoMod.m 第 726 行异常字面量；然后完成 CGMBootstrap.js 的 session-aware Manager/PlayerData/Pay/VipCard rebind、sessionGen/旧 mailbox 清理、Pay/IAP Hook 重装、native mailbox 重发现、命令超时 UI 和 IAP optimistic 状态回执校正。补 mock 的账号 A→B→A 资源/月卡回归，运行 node/python/static/JSC 验证并生成可测试 DEB。暂时不要宣称真机功能已生效；完成静态闭环后再用 F:\测试\cookingGO\mcp_65.py 验证新设备，保存全部证据到 F:\测试\cookingGO\_work\。所有结论给绝对路径、行号和日志/JSON 证据，不要丢弃现有修改。
```

## 新对话操作

1. 新建 Codex 对话。
2. 选择“使用现有文件夹”。
3. 添加：`F:\测试\cookingGO\github-cookinggo-mod`。
4. 将上面的“新会话首条提示词”作为第一条消息发送。


## 2026-09-14 本轮实现结果

- 已完成 `src/CGMBootstrap.js` session-aware rebind：按 `Manager/PlayerData/MapData/Pay/VipCard/YiFaniOSIAPBridge` 引用和内存身份指纹检测切换，递增 `sessionGen`，清理旧 mailbox receipt，恢复旧 hook 并重装新 hook。
- 已完成 `src/CookingGoMod.m` native mailbox 重发现、sessionGen/seq 重置、旧 result 丢弃和 3 秒命令超时诊断；第 726 行异常 `` `r`n `` 已修复。
- `tools/mock_cgm_bootstrap.js` 当前 `13/13 tests passed`，覆盖 A→B→A 资源/月卡回归与 stale command。
- 已重新生成 `src/CGMBootstrap.generated.h` 与 `packaging/CookingGoMod.index12602.jsc`；静态 verifier 输出 `static closure: OK`。
- 已生成 Windows 静态测试 DEB：`F:\测试\cookingGO\dist\com.seagull.cookinggomod_1.3.8_iphoneos-arm64-js-test.deb`。该包复用旧 1.3.7 dylib，仅能验证新 JS/JSC/control；正式设备验收必须使用 macOS workflow 编译出的新 dylib。
- 真机当前报告 `F:\测试\cookingGO\_work\postfix_verify_12602_v138_js_test_current.json`：base launch `lv=0/dyld=0`，但 fresh tweak load marker 未观察到，mailbox 仍为 1.3.7，因此没有把新逻辑记为 device PASS。
- 新增说明：`docs/SESSION-REBIND-12602.md`。
