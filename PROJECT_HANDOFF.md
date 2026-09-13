# Cooking GO Mod 项目交接

> 更新时间：2026-09-13  
> 主开发目录：`F:\测试\cookingGO`  
> Git 仓库：`F:\测试\cookingGO\github-cookinggo-mod`  
> 当前分支：`codex/iap-month-card-hook`  
> 当前 HEAD：`ddc307f Regenerate 1.26.02 packaged JSC for v1.3.4`  
> 状态：本轮新增本地静态报告、Node mock harness、Windows DEB payload 重包工具，并重新同步 packaged JSC/DEB；这些改动尚未提交；此前 `main` 与 `codex/iap-month-card-hook` 已推送到 `ddc307f`

## 1. 项目目标

维护 Cooking GO iOS rootless Mod，兼容游戏 `1.26.02`，保留既有钻石/金币/燃油/免广告券/换装币和悬浮窗功能；新增一个**独立管理的 IAP Hook 开关**，后续沿真实购买成功回调扩展到月卡、财富日历及其他商品。所有结论必须基于静态证据或用户明确测试后的日志，不能猜测。

## 2. 当前目录结构

```text
F:\测试\cookingGO\
├─ Cooking Go_1.26.02.ipa       # 最新 IPA，SHA-256 8fd0e3a5...
├─ github-cookinggo-mod\        # 主 Git 仓库/开发目录
│  ├─ src\                       # Objective-C tweak + JS bootstrap
│  ├─ packaging\                # deb 控制文件、cfg、plist、内置 JSC
│  ├─ tools\                    # 解包、解密、静态验证、设备验证工具
│  ├─ docs\                     # 闪退、签名、runtime hook 文档
│  ├─ scripts\                  # macOS/Xcode 构建脚本
│  └─ .github\workflows\        # CI 构建/Release
├─ dist\                        # 历史及当前 DEB
├─ _extract\                    # IPA 解包临时目录
├─ _work\                       # 解密 JS、分析结果、验证报告
├─ mod\                         # 曾同步的开发/发布副本
└─ HANDOFF.md                    # 旧版长交接记录
```

## 3. 正在开发功能

- **Runtime bootstrap**：通过 1.26.02 `ScriptEngine::evalString` Hook 注入 `CookingGoMod.bootstrap.js`，解决加密 `index.jsc` 无法直接改写的问题。
- **独立 IAP 开关**：`iap=0` 默认关闭，状态持久化于 `Documents/cookingmod/iap_hook.json`，不改变其他 DEB 功能。
- **当前 JS IAP Hook 范围**：已接管 VIP/月卡相关购买；普通商品目前仍调用原始支付链。
- **商品扩展目标**：从真实 `Pay.pay` / `paySuc` / `OnSuccess` 发放链路提取完整商品目录，覆盖财富日历、礼包、通行证、钻石/金币/道具等，不先假定商品 ID 或回调。
- **财富日历**：已完成静态链路定位，尚未落地完整商品/发放实现。

## 4. 正在开发的功能区

1. **启动与闪退闭环**：1.26.02 的首要问题是 dyld/Library Validation；已定位 `AdjustSdk.framework/AdjustSdk` 签名身份不一致路径。
2. **JS 回执闭环**：native 写 `cmd.json` 后，JS 应生成 `res.json`、`state.json`；用户此前钻石功能卡在“等待 JS 回执”。
3. **IAP 商品目录**：静态解析 `Table` 初始化、`purchaseTbl/giftTbl/rewardTbl`、`EGiftType`、`ProductID/SKU`、`PurchaseId/GiftId/RewardIds` 及成功回调。
4. **财富日历发放链路**：确认 `Activity.richesInfo → payTotal/constById(146) → giftTbl(EGiftType.Riches) → RewardIds → getRichesReward → saveRichesInfo`。
5. **构建与发布**：静态验证通过后再构建 DEB/CI Release；设备测试必须等用户明确说“测试”。

## 5. 关键技术

- 平台：iOS arm64、rootless、ElleKit/TweakInject；实现语言 Objective-C + JavaScript。
- 游戏：Cocos/JSB；`assets/scriptBundle/index.jsc` 为 `encrypted:true`，静态链为 XXTEA → gzip → JS。
- Runtime Hook：
  - `evalString` 函数入口：VA/file offset `0x101c28a30` / `0x1c28a30`。
  - 旧坐标 `0x1c28a48` 位于 prologue 内，不能继续使用。
  - `ScriptEngine` getter 候选：`0x101c263cc`。
  - 调用 ABI：`x0=this, x1=script, x2=length, x3=ret, x4=filename`。
- 配置：`objc=1, posix=0, overlay=1, panel=0, rot=0, vlog=0, iap=0, rt=0`。
- Mailbox：`js_hello.json`、`state.json`、`cmd.json`、`res.json`、`probe_cmd.json`、`probe.json`、`iap_hook.json`。

## 6. 重要文件说明

- `F:\测试\cookingGO\github-cookinggo-mod\src\CookingGoMod.m`：native tweak、悬浮窗、命令写入、回执读取、runtime hook。
- `F:\测试\cookingGO\github-cookinggo-mod\src\CGMBootstrap.js`：JS bind、资源命令、IAP Hook、mailbox 主循环；当前版本 `1.3.4`。
- `F:\测试\cookingGO\github-cookinggo-mod\packaging\CookingGoMod.cfg`：运行开关；`iap`/`rt` 默认均为 0。
- `F:\测试\cookingGO\github-cookinggo-mod\packaging\CookingGoMod.index12602.jsc`：CI/DEB 内置的静态 patched JSC；由源码重新生成。
- `tools/patch_cocos_jsc.py`：解密/重打包 JSC。
- `tools/static_verify_12602.py`、`tools/verify_deb.sh`：静态闭环与 DEB 结构验证。
- `tools/analyze_ipa_closure.py`：IPA 依赖、签名、嵌入 Framework 分析。
- `tools/find_runtime_hook_points.py`、`tools/macho_string_xrefs.py`：runtime Hook 候选点与字符串交叉引用。
- `tools/postfix_verify_12602.py`、`tools/run_postfix_verify_12602.ps1`：设备验证流程；涉及手机/日志，需用户明确授权测试时再运行。
- `docs/CRASH-TRIAGE-12602.md`、`docs/SIGNING-FIX-12602.md`、`docs/RUNTIME-HOOK-12602.md`：已确认的启动、签名和 Hook 结论。

## 7. 已知问题

- 1.26.02 原始 IPA 曾因 `AdjustSdk` 与主程序 Team ID/Library Validation 不一致而启动即退出；历史 live re-sign 后 base launch gate 通过，但当前设备状态没有新的测试证据。
- v1.3.4 已修正 `evalString` 入口并增加 delayed `getInstance` bootstrap；静态 JSC/DEB 已重新生成，但用户暂停手机操作后，尚未取得新的 JS handshake 实测证据。
- 钻石命令历史现象为“等待 JS 回执”，静态上表示 native 已发命令但 JS 没有产出 `res.json`/`state.json`；具体失败点仍需本地 mock harness 或用户明确测试后的真实日志确认。
- 当前 IAP Hook 仍是 VIP/月卡范围；全商品统一接管、财富日历完整发放和商品映射尚未实现。
- `postinst` 不得直接修改 live 加密/签名 `index.jsc`；当前策略是保留原 bundle，走 runtime 注入。
- 当前 v1.3.4 DEB：`F:\测试\cookingGO\dist\com.seagull.cookinggomod_1.3.4_iphoneos-arm64.deb`，SHA-256 `96E43997EDFA8E4AA46E6BE917C28119F11F868E0CE352E93B258737D40C1921`。旧包备份：`F:\测试\cookingGO\_work\com.seagull.cookinggomod_1.3.4_iphoneos-arm64.before-static-harness.deb`，SHA-256 `E0410052E967EA1D752B484740F3E4D90C22BB1619AB5CE29F434CF3A4E5F49E`。

## 7.1 本轮已完成（2026-09-13 晚）

- 新增 `F:\测试\cookingGO\github-cookinggo-mod\docs\IAP-RICHES-STATIC-12602.md`：固化 Table 初始化、`EGiftType`、`Pay.pay -> paySuc -> OnSuccess` 50 个静态调用点、财富日历三档阈值/RewardIds/claim index/持久化字段证据。
- 新增 `F:\测试\cookingGO\github-cookinggo-mod\tools\mock_cgm_bootstrap.js`：用 `node:vm` + mock JSB/Cocos 本地验证 `CGMBootstrap.js` 的 mailbox/bind/state/res/probe/seq 去重/异常容错，并确认 `iapHook` 默认关闭、默认关闭时 `Pay.pay` 透传原实现。
- 新增 `F:\测试\cookingGO\github-cookinggo-mod\tools\repack_deb_payload.py`：Windows 无 `dpkg-deb` 时，只替换 DEB 内 `CookingGoMod.bootstrap.js` 和 `CookingGoMod.index12602.jsc`，保留旧 dylib/control。
- 增强 `tools/static_verify_12602.py`：新增断言 packaged JSC 含当前 `src/CGMBootstrap.js`，DEB 内 bootstrap/JSC 与仓库文件字节一致，并检查静态报告/harness 存在。
- 重新生成 `packaging\CookingGoMod.index12602.jsc`：SHA-256 `FBB2643C59216B616A483C150C2D60EEB2EAAC19180583C3880E1AFE50062C39`。
- 重包 `F:\测试\cookingGO\dist\com.seagull.cookinggomod_1.3.4_iphoneos-arm64.deb`：SHA-256 `96E43997EDFA8E4AA46E6BE917C28119F11F868E0CE352E93B258737D40C1921`；已同步到 `F:\测试\cookingGO\mod\dist\`。
- 本地验证通过：`node --check src/CGMBootstrap.js`、`node --check tools/mock_cgm_bootstrap.js`、`node tools/mock_cgm_bootstrap.js`（11/11）、`python -m py_compile tools/static_verify_12602.py tools/repack_deb_payload.py`、`python tools/static_verify_12602.py ...`（`static closure: OK`）。

## 8. 下一步需要做什么

### 先做静态/本地，不操作手机

1. 本轮 1-4 项已完成，证据见 `docs/IAP-RICHES-STATIC-12602.md` 与 `tools/mock_cgm_bootstrap.js`。
2. 后续若继续开发，先围绕“诊断与默认关闭安全性”设计，不直接猜商品 ID/回调；任何真机步骤必须记录 fresh `js_hello/state/res/probe` 证据。
3. Windows 侧重新打包 DEB 时使用 `tools/repack_deb_payload.py` 后必须跑 `tools/static_verify_12602.py`，确认 DEB 内 bootstrap/JSC 与仓库字节一致。

### 用户明确要求测试后

1. 先跑 base launch gate，再按 `rt=0 → rt=1` 顺序验证；读取后台日志和 mailbox 证据。
2. 依次测试钻石、月卡、财富日历、礼包/通行证等已映射商品，记录 `js_hello/state/res/iap_hook` 与实际 `OnSuccess` 结果。
3. 根据真实回执闭环修复 JS Hook；完成后运行 `node --check`、Python 编译检查、JSC round-trip、`static_verify_12602.py`、`verify_deb.sh`。
4. 更新版本、构建 DEB、计算 SHA-256、同步 `F:\测试\cookingGO\mod`，再发布 Release。

## 9. 不能改动 / 需要注意的约束

- 用户未明确说“测试”前：不操作手机、不启动/退出游戏、不安装/卸载、不读取后台日志。
- 不改变现有资源修改、悬浮窗、配置默认值和现有 DEB 行为；IAP 必须是独立开关，默认关闭。
- 不在 `postinst` 修改 live 加密/签名 App Bundle 或 `index.jsc`。
- 不使用未经确认的偏移、商品 ID、SKU、RewardId 或回调名；静态结论与实测结论分开记录。
- 没有 `js_hello.json`、`state.json`、`res.json` 或明确日志证据时，不宣称 runtime/IAP 已生效。
- 保留用户现有文件和工作区改动；先检查 `git status` 再修改。
- 构建脚本 `scripts/build.sh` 依赖 macOS + Xcode；Windows 侧主要做静态分析、打包验证和文档整理。

## 新会话首条提示词

```text
读取 F:\测试\cookingGO\PROJECT_HANDOFF.md，并以它作为当前项目上下文。继续 Cooking GO Mod 1.26.02 的静态分析：先完成 Table/purchaseTbl/giftTbl/rewardTbl/EGiftType 商品目录映射、Pay.pay 成功回调映射、财富日历发放链路报告，以及 CGMBootstrap.js 的本地 Node.js mock 回执 harness。暂时不要操作手机、不要启动游戏、不要安装/卸载、不要读取后台日志；不改现有 DEB 功能和默认配置。所有结论给出绝对路径、行号或静态证据。
```

