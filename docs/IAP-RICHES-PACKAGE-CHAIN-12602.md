# Cooking GO 1.26.02 礼包 → 财富日历链路

> 更新时间：2026-09-14  
> 范围：local-only purchase simulator、运行时商品目录探针、Node.js mock 回归。  
> 真实 App Store 交易路径保持原样；本变更不生成 Store receipt，也不调用 `YiFaniOSIAPBridge.buyProduct`。

## 已确认的原生链路

```text
purchase success
  -> PlayerData/ServerData.gameData.playerInfo.payTotal += price
  -> Activity.richesInfo getter
  -> Table.constById(146)
  -> beginTime / beginTime2 / beginTime3
  -> ServerData.saveRichesInfo(false)
```

静态证据：

- `F:\测试\cookingGO\_work\patched_12602_v134.js:10642-10665`：`Activity.richesInfo` 根据 `playerInfo.payTotal` 打开三个 track。
- `F:\测试\cookingGO\_work\patched_12602_v134.js:10719-10735`：`Table.constById(146)` 读取阈值。
- `F:\测试\cookingGO\_work\patched_12602_v134.js:121987-121990`：`saveRichesInfo(false)` 持久化 `gameData.richesInfo`。
- `F:\测试\cookingGO\_work\static12602\assets\resources\config.json:1`：资源 key `13989`、`19990`、`15766` 分别对应 purchase/gift/reward 表。

海外阈值：

```text
Track 0: 0.99 USD -> beginTime
Track 1: 5.99 USD -> beginTime2
Track 2: 21.99 USD -> beginTime3
```

## 商品目录处理

`src/CGMBootstrap.js` 新增 `iap_catalog` 命令：

- 从当前运行时 `Manager.Table.purchaseTbl` 读取 `ID`、价格字段、iOS/default ProductID、`RewardID`；
- 从 `Manager.Table.giftTbl` 读取 `GiftType === 28` 的 Riches rows、`PurchaseId[]` 和 `RewardIds[]`；
- 不硬编码真实商品 ID 或 SKU；
- 真实导出商品行仍需在运行时 `iap_catalog` 回执或后续静态表导出中确认。

命令示例：

```json
{
  "seq": 1,
  "res": "iap_catalog",
  "action": "read",
  "sessionGen": 1
}
```

## local-only 模拟礼包

命令名：`purchase_sim`。它必须显式带 `localOnly: true`，否则直接拒绝执行且不改变 `payTotal`。

```json
{
  "seq": 2,
  "res": "purchase_sim",
  "action": "success",
  "value": 0.99,
  "amount": 0.99,
  "orderId": "local-r01",
  "localOnly": true,
  "sessionGen": 1
}
```

可选字段：

- `amountCents: 99`：用 cents 表示金额；优先于 `amount/value`；
- `purchaseId`：仅在 `iap_catalog` 已确认后填写；
- `requireCatalog: true`：要求 `purchaseId` 必须存在于当前运行时目录；
- `allowPriceOverride`：mock/fixture 需要时才使用，默认要求金额与 `purchaseTbl.Price` 一致；
- `orderId`：用于重放去重，同一 session 下重复 order 不会再次累计。

成功回执包含：

```json
{
  "ok": true,
  "localOnly": true,
  "amount": 0.99,
  "payTotalBefore": 0,
  "payTotalAfter": 0.99,
  "richesTrack0Unlocked": true,
  "riches": {
    "track0Unlocked": true,
    "track1Unlocked": false,
    "track2Unlocked": false,
    "beginTime": 1700000000
  },
  "sessionGen": 1,
  "sessionKey": "session-1"
}
```

Native 面板新增 `礼包100` 按钮。按钮写入 `purchase_sim` local-only mailbox 命令，使用 `targetPayTotal: 100.00`，只补齐当前账号到目标额度的差额；重复点击不会继续膨胀 `payTotal`。它不是 Store 购买按钮。

## 100 USD 目标额度与末档加赠

```json
{
  "res": "purchase_sim",
  "action": "success",
  "value": 100.0,
  "targetPayTotal": 100.0,
  "orderId": "local-r100",
  "localOnly": true,
  "sessionGen": 1
}
```

达到 `100.00 USD` 后，海外阈值 `0.99 / 5.99 / 21.99` 的三个财富日历 Track 均解锁。静态代码确认额外加赠不是第四个 `payTotal` 阈值，而是在 `GiftRiches.onClickGet` 领取 Track 2 第 3 天奖励后执行 `getWeekCard()`：

```text
Riches Track 2 / Day 2 claim
  -> Activity.getRichesReward(8)
  -> getWeekCard()
  -> VipCard.setPlayerVipDataByGiftId(weekPurchaseTbl.ID, true)
  -> getAward(weekRewardTbl.ID, false)
```

因此回执中的 `riches.extraBonus.eligible=true` 表示末档领取路径具备加赠资格，`granted=false` 表示仅完成消费额度模拟，没有伪造领取点击。

## 回归结果

运行：

```powershell
node --check F:\测试\cookingGO\github-cookinggo-mod\src\CGMBootstrap.js
node --check F:\测试\cookingGO\github-cookinggo-mod\tools\mock_cgm_bootstrap.js
node F:\测试\cookingGO\github-cookinggo-mod\tools\mock_cgm_bootstrap.js
```

当前结果：`22/22 tests passed`。

覆盖：

1. 目录探针含 purchase rows 与 Riches rows；
2. 无 `localOnly` 时不改数据；
3. `0.98` 不解锁、累计到 `0.99` 解锁 Track 0；
4. 绑定 `purchaseId=1001` 的 mock 0.99 row 时价格匹配；
5. `5.99` 解锁 Track 0/1，累计到 `21.99` 解锁 Track 0/1/2；
6. `targetPayTotal=100` 精确补齐到 100 USD，重复目标点击不继续增加；
7. 末档 `getWeekCard` 加赠资格被识别，但未伪造领取；
8. 重复 `orderId` 不重复累计；
9. `saveRichesInfo(false)` 被调用；
10. A→B→A 账号隔离；
11. stale `sessionGen` 命令在 mutation 前拒绝。

## 下一步接入条件

在正式购买链路接入前，必须先从运行时 `iap_catalog` 或可信静态导出确认：

```text
purchaseTbl.ID
purchaseTbl.Price
purchaseTbl.ProductID / ProductIDiOSOversea
purchaseTbl.RewardID
Riches giftTbl.PurchaseId[]（当前静态结果为空）
```

确认这些字段后，再单独设计真实商品成功回调的奖励派发；当前版本不改变线上 App Store callback chain。
