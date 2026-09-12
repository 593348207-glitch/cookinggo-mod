# 运行时验证步骤（真机）

> 安装后按顺序执行，任何一步的输出都可以直接回贴。

## 0. 安装

```bash
scp com.seagull.cookinggomod_<ver>_iphoneos-arm64.deb root@<device>:/var/mobile/Documents/
ssh root@<device>
dpkg -i /var/mobile/Documents/com.seagull.cookinggomod_<ver>_iphoneos-arm64.deb
```

确认注入文件就位：

```bash
ls -l /var/jb/usr/lib/TweakInject/CookingGoMod.*
```

## 1. 进程内注入确认（日志）

```bash
# 直接看进程日志
idevicesyslog 2>/dev/null | grep -i CookingGoMod
# 或真机上
tail -f /var/mobile/Containers/Data/Application/<UUID>/Documents/cookingmod/mod.log
```

期望看到：

```
[CookingGoMod] mailbox ready at ...
[CookingGoMod] CookingGoMod v1.0.x loaded (bundle=com.airplanecooking.chef.kitchen.restaurant.diner)
[CookingGoMod] ObjC hooks installed (NSData x3, NSFileManager x1, NSString x1)
[CookingGoMod] POSIX hooks: fopen=1/1 open=1 openat=1 guarded=? dprotected=?
[CookingGoMod] target script: /var/containers/Bundle/Application/<UUID>/AirplaneCooking-mobile.app/assets/scriptBundle/index.js
[CookingGoMod] overlay window created (level=...)
[CookingGoMod] observed JS read: ...
[CookingGoMod] JS injected through ObjC file API (index.js, +9xxx bytes)
```

**判定点**

| 现象 | 含义 | 处理 |
|---|---|---|
| 有 `JS injected through ObjC file API` | NSData 路径命中（预期主路径） | 正常 |
| 只有 `POSIX-level injection armoured` 且无 ObjC 注入 | 走的是 open/fopen 路径 | 也正常 |
| 两者都没有 | 文件读取路径未命中 | 把 `observed JS read:` 全部行回贴，按实际路径补 matcher |
| 无 `target script:` | 资源布局与静态分析不同 | 回贴该行 |

## 2. JS 侧握手确认

```bash
ls -l <container>/Documents/cookingmod/
cat <container>/Documents/cookingmod/js_hello.json
cat <container>/Documents/cookingmod/state.json
cat <container>/Documents/cookingmod/probe.json
```

期望：

* `js_hello.json` 存在 → bootstrap 已在同一 V8 VM 里执行，且找到了信箱目录
* `state.json` 里 `ready:true` 且四个资源字段是数字 → `__require("Game").default.PlayerData` 绑定成功
* `probe.json` 里 `typeofRequire:"function"`、`gameDefault:true`、`eventIdCount` 有值、`coreEvent:true`

## 3. UI 观测

1. 悬浮球出现且可拖动（拖动后 `mod.log` 无异常，游戏不闪退）
2. 点球展开面板；四个输入/选择控件完整可见，不被键盘或安全区遮挡
3. 点 `自检` → 日志区出现 `[自检] require=... jsb=... cc=...` 等行

## 4. 功能验证（核心验收）

1. 选择 `钻石`，记下面板显示的 `当前: N`
2. 输入 `100`，点绿色 `+`
3. 日志区应出现：

```
资源: 钻石
修改前: N
输入表达: N + 100
修改后: N+100
← JS 回执 #k
  修改前: N
  输入表达: N + 100 = N+100
  修改后: N+100
  复核: state.json 一致 ✔
```

4. 再输入 `100`，点蓝色 `=` → 结果应为 `100`
5. 对 `金币 / 燃油 / 免广告券` 重复；金币与燃油面板数值应实时跟随 `state.json`

## 5. 持久化验证

* 关闭游戏（后台杀进程）后重开，资源数量应保持修改后的值
* 若被还原：说明服务端/云存档覆盖，回贴 `mod.log` 与 `state.json`，下一步改为「写本地存档 + 覆盖云存档对比」方案