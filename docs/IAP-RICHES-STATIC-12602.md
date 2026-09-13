# Cooking GO 1.26.02 static IAP and Riches evidence

> Date: 2026-09-13
> Scope: local static analysis and local `node:vm` bootstrap harness only.
> No phone/device actions are required for the evidence below.

## Table loading chain

Confirmed in `F:\测试\cookingGO\_work\patched_12602_v134.js`:

| Evidence | Meaning |
|---|---|
| `102827: ye.Table = new u.default();` | `Manager.Table` is a `TableMgr` instance. |
| `102837: ye.Pay = new m.default();` | `Manager.Pay` is a `PayMgr` instance. |
| `102850: ye.PayData = new L.default();` | `Manager.PayData` records purchase history. |
| `102862: ye.VipCard = new X.default();` | `Manager.VipCard` owns VIP-card state. |
| `129982: static_purchase_tbl: "purchaseTbl"` | resource `tables/static_purchase_tbl` maps to `Table.purchaseTbl`. |
| `129984: static_reward_tbl: "rewardTbl"` | resource `tables/static_reward_tbl` maps to `Table.rewardTbl`. |
| `130002: gift_tbl: "giftTbl"` | resource `tables/gift_tbl` maps to `Table.giftTbl`. |
| `130065: this.purchaseTbl = n[++s].json;` | purchase table assignment. |
| `130066: this.rewardTbl = n[++s].json;` | reward table assignment. |
| `130074: this.giftTbl = n[++s].json;` | gift table assignment. |

Resource index evidence in `F:\测试\cookingGO\_work\static12602\assets\resources\config.json:1`:

| Resource key | Resource path |
|---|---|
| `13989` | `tables/static_purchase_tbl` |
| `15766` | `tables/static_reward_tbl` |
| `19990` | `tables/gift_tbl` |

## Core field relationships

```text
giftTbl.ID
  <- activityTbl.GiftID

giftTbl.GiftType
  <- EGiftType.*

giftTbl.PurchaseId[index]
  -> purchaseTbl.ID

purchaseTbl.ID
  -> Pay.pay(purchaseTbl)
  -> PayData.addPayData(purchaseId, price, orderId)
  -> payInfo[].purchaseId

purchaseTbl.ProductID
purchaseTbl.ProductIDiOSInland
purchaseTbl.ProductIDiOSOversea
purchaseTbl.ProductIDFb
purchaseTbl.ProductNameFb
  -> platform ProductID / SKU selected by Table.getPurchaseProductID(row)

purchaseTbl.RewardID
  -> rewardTbl.ID

giftTbl.RewardIds[index]
  -> rewardTbl.ID
```

SKU selection evidence:

| Path | Evidence |
|---|---|
| `F:\测试\cookingGO\_work\patched_12602_v134.js:130236` | `getPurchaseProductID(e) {` |
| `F:\测试\cookingGO\_work\patched_12602_v134.js:130237` | selects `ProductIDiOSInland`, `ProductIDiOSOversea`, `ProductID`, `ProductIDFb` by platform. |
| `F:\测试\cookingGO\_work\patched_12602_v134.js:130246` | `getPurchaseTblByProductID(e) {` |
| `F:\测试\cookingGO\_work\patched_12602_v134.js:130247` | reverse lookup checks iOS/default/FB product fields. |
| `F:\测试\cookingGO\_work\patched_12602_v134.js:110072` | `initSKUS() {` |
| `F:\测试\cookingGO\_work\patched_12602_v134.js:110108` | `validateProductIds(this._inAppSKUS)` |
| `F:\测试\cookingGO\_work\patched_12602_v134.js:110128` | `buyProduct(Table.getPurchaseProductID(e), ...)` |

## `EGiftType` values used by the current analysis

Confirmed in `F:\测试\cookingGO\_work\patched_12602_v134.js:129775-129823`:

| Name | Value | Evidence line |
|---|---:|---|
| `PassCheck` | 17 | `129793` |
| `PassCheckSeason` | 19 | `129794` |
| `PassCheckSeasonGift` | 20 | `129795` |
| `vipCard` | 24 | `129799` |
| `superExpCard` | 25 | `129800` |
| `adVip` | 26 | `129801` |
| `GrowthFund` | 27 | `129802` |
| `Riches` | 28 | `129803` |
| `GiftLimit` | 34 | `129807` |
| `PiggyBankCoin` | 40 | `129813` |

## Pay success dispatch model

Confirmed in `F:\测试\cookingGO\_work\modules_iap\PayMgr.js`:

| Evidence | Meaning |
|---|---|
| `440: pay(e, t) {` | `Pay.pay` receives one `purchaseTbl` row and callback object. |
| `445: this._purchaseTbl = e;` | active purchase table row is stored. |
| `446: this._payCb = t;` | callback object is stored. |
| `349: paySuc(e, t, i, a) {` | platform success paths converge into `paySuc`. |
| `364-366: if (this._payCb && this._payCb.OnSuccess) ... this._payCb.OnSuccess();` | actual product fulfillment returns to each callsite's `OnSuccess`. |
| `395-398` | payment timestamps/count/total are updated. |
| `405: PayData.addPayData(this._purchaseTbl.ID, r, e);` | purchase history records internal purchase id. |
| `413` | Riches red-dot is refreshed after payment stats update. |

Conclusion: `PayMgr.paySuc(...)` is the central success dispatcher and accounting point. Product-specific state or reward changes live in the individual `Pay.pay(..., { OnSuccess })` callsites, not in one central reward switch.

## `Pay.pay` callsite map

The static JS contains 50 `Pay.pay` callsites. Main source path: `F:\测试\cookingGO\_work\patched_12602_v134.js`; the same locations are present in `F:\测试\cookingGO\_work\index12602.patched.js`.

| # | Line | Module / method | purchase/gift source | OnSuccess / reward-state path |
|---:|---:|---|---|---|
| 1 | 6445 | `ActivityEndlessSurpriseCtr.onClickGet` | `giftTbl.PurchaseId[e]` | `getReward()`, then `rewardTbl.find(...RewardIds[i])` |
| 2 | 11350 | `ActivityPassCheckBuyCtr.onClickBuy` | `EGiftType.PassCheck`, `PurchaseId[parseInt(t)]` | `buySuc(o)`, `Activity.activityPassCheckBuyReward(e)` |
| 3 | 13480 | `ActivityPassCheckSeasonCtr.onClickBuy` | `uiData.giftTbl.PurchaseId[parseInt(t)]` | set `firstPay/secondPay`, `saveActivityPassCheckSeasonInfo(false)`, `buyGoldRefresh()` |
| 4 | 15318 | `ActivityPiggyBankCtr.onClickBuy` | `uiData.purchaseTbl` | `getReward()`, `PlayerData.addGem(...)`, `Activity.piggyAddReward()` |
| 5 | 27152 | `CCAdVipCtr.onBtnBuyClick` | `purchaseTbl.find(...this.purchaseId)` | update `adVipEndTimes/adVipData`, `saveAdVipData(false)` |
| 6 | 29110 | `CCVipCardBuyViewCtr.onBtnBuyClicked` | `EGiftType.vipCard`, `PurchaseId[curTab]` | `dealBuyVipCardInfo()`, `getAward(...)`, `setPlayerVipDataByGiftId(...)` |
| 7 | 29372 | `CCVipExperienceCardViewCtr.onBtnBuyClicked` | `_purchaseId` | `VipCard.onBuySuperExpCard()`, `RewardMgr.getReward(...)` |
| 8 | 33231 | `CoinShopCtr.onClickBuy1` | `uiData.purchaseTbl1` | `MapData.addCoin(getExpansionCoin(...))` |
| 9 | 33267 | `CoinShopCtr.onClickBuy2` | `uiData.purchaseTbl2` | `MapData.addCoin(getExpansionCoin(...))` |
| 10 | 59746 | `GamePropGift.onClickBuy` | `this.purchaseTbl` | `buySuc(...)`, prop/energy/souvenir reward path |
| 11 | 60260 | `GameReviveGift.onClickBuy` | gift purchase/reward index | `reviveGiftPurchaseId`, `buySuc(...)`, gem/coin/power reward |
| 12 | 60493 | `GameReviveVip.onBtnBuyClicked` | `EGiftType.vipCard`, `PurchaseId[1]` | `dealBuyVipCardInfo()`, `getAward(...)`, VIP state update |
| 13 | 61766 | `GameThemeCoinShopCtr.onClickBuy1` | `uiData.purchaseTbl1` | `ActivityGame.addActivityCoin(...)` |
| 14 | 61804 | `GameThemeCoinShopCtr.onClickBuy2` | `uiData.purchaseTbl2` | `ActivityGame.addActivityCoin(...)` |
| 15 | 61842 | `GameThemeCoinShopCtr.onClickBuy3` | `uiData.purchaseTbl3` | `ActivityGame.addActivityCoin(...)` |
| 16 | 64260 | `GameThemeUpLessCtr.onClickBuy1` | `uiData.purchaseTbl1` | `ActivityGame.addActivityCoin(...)` |
| 17 | 64299 | `GameThemeUpLessCtr.onClickBuy2` | `uiData.purchaseTbl2` | `ActivityGame.addActivityCoin(...)` |
| 18 | 64338 | `GameThemeUpLessCtr.onClickBuy3` | `uiData.purchaseTbl3` | `ActivityGame.addActivityCoin(...)` |
| 19 | 66457 | `GiftActivityChallengeCtr.buyPackage` | parameter purchase/reward | `buySuc(t)`, `showNormalReward([e.ID])` |
| 20 | 66861 | `GiftActivityHolidayCtr.buyPackage` | parameter purchase/reward | `buySuc(t)`, `showNormalReward([e.ID])` |
| 21 | 67194 | `GiftAdBreakIceCtr.onClickBuy` | `uiData.purchaseTbl` | `buySuc()`, `showBoxSpineReward(...)` |
| 22 | 67473 | `GiftAdDiamondsCtr.onClickBuy` | `uiData.purchaseTbl` | `buySuc()`, `showBoxSpineReward(...)` |
| 23 | 67731 | `GiftAutoMachineCtr.buyPackage` | parameter purchase/reward | set `autoMachine=true`, `showUI("NormalReward", ...)` |
| 24 | 69567 | `GiftDreamTreasureCtr.onClickBuy` | purchase `i`, reward `a` | `showNormalReward([a.ID])`, buy-times update |
| 25 | 70069 | `GiftEnergyLessCtr.onEnergygiftClick` | `this.purchaseTbl` | daily limit + `purchaseTbl.RewardID` reward |
| 26 | 70093 | `GiftEnergyLessCtr.onEnergygiftClick2` | `this.purchaseTbl2` | daily limit + `purchaseTbl2.RewardID` reward |
| 27 | 70181 | `GiftEnergyLessCtr.onIcegiftClick` | `uiData.purchaseTbl` | `addPowerNum(...)`, `GiftIceBreakMgr.addIceBreakData()` |
| 28 | 70636 | `GiftGameThemeEnergyLessCtr.onEnergygiftClick` | `this.purchaseTbl` | daily limit + reward + theme energy |
| 29 | 70660 | `GiftGameThemeEnergyLessCtr.onEnergygiftClick2` | `this.purchaseTbl2` | daily limit + reward + theme energy |
| 30 | 71005 | `GiftHoliday2Ctr.buyPackage` | parameter purchase/reward | `buySuc(t)`, `RewardMgr.getReward(..., purchaseId)` |
| 31 | 71426 | `GiftHolidayCtr.buyPackage` | parameter purchase/reward | `buySuc(t)`, `showNormalReward([e.ID])` |
| 32 | 71932 | `GiftIceBreakFuelCtr.onClickBuy` | `uiData.purchaseTbl` | `GiftIceBreakMgr.addIceBreakData()`, `RewardMgr.getReward(...)` |
| 33 | 72200 | `GiftLimitCtr.onClickBuy` | `uiData.purchaseTbl` | `Activity.buyGiftLimit()`, normal reward UI |
| 34 | 72421 | `GiftNewPlayerCtr.onClickBuy` | `uiData.purchaseTbl` | strategy update, normal reward UI |
| 35 | 72850 | `GiftRichesCtr.buyNewPlayer1` | `uiData.lessPurchaseTbl` | `buySuc(lessRewardTbl, 18)`, `RewardMgr.getReward(...)` |
| 36 | 72879 | `GiftRichesCtr.buyNewPlayer2` | `uiData.morePurchaseTbl` | `buySuc(moreRewardTbl, 19)`, `RewardMgr.getReward(...)` |
| 37 | 72909 | `GiftRichesCtr.buyMonthCard` | `uiData.monthPurchaseTbl` | `VipCard.setPlayerVipDataByGiftId(...)`, `getAward(...)` |
| 38 | 72958 | `GiftRichesCtr.buyNoAdCard` | `uiData.adPurchaseTbl` | permanent ad VIP fields, `saveAdVipData(false)` |
| 39 | 73146 | `GiftRichesCtr.buyConstGem` | `uiData.constPurchaseTbl` | normal reward + refresh accumulated Riches view |
| 40 | 74142 | `GiftSweetCtr.onClickBuy` | `uiData.purchaseTbl` | `buySuc(rewardTbl)`, `RewardMgr.getReward(..., purchaseTbl.ID)` |
| 41 | 75799 | `GrowthFundViewCtr.onBtnBuyClicked` | `purchaseTbl.find(ID === data.purchaseId)` | set `GrowthFund.buyState`, save and red-dot update |
| 42 | 101665 | `MainGameUpLessCtr.onClickBuy1` | `uiData.purchaseTbl1` | `MapData.addCoin(getExpansionCoin(...))` |
| 43 | 101702 | `MainGameUpLessCtr.onClickBuy2` | `uiData.purchaseTbl2` | `MapData.addCoin(getExpansionCoin(...))` |
| 44 | 123251 | `ShopGemItem.onBuyClick` | `this.purchaseTbl` | `PlayerData.addGem(...)`, ad coupon reward |
| 45 | 123696 | `ShopGiftAdDiamonds.onBuyClick` | `this.purchaseTbl` | `buySuc()`, reward branch after `123732` |
| 46 | 123953 | `ShopGiftItem.onBuyClick` | `this.purchaseTbl` | `PlayerData.addGem(...)`, `PlayerData.addPowerNum(...)` |
| 47 | 124134 | `ShopIceItem.onClickBuy` | `this.purchaseTbl` | `GiftIceBreakMgr.addIceBreakData()`, power reward |
| 48 | 124315 | `ShopNewGiftItem.onBuyClick` | `this.purchaseTbl` | gem, coin, map-coin rewards |
| 49 | 125416 | `ShopVipBuyView.onBtnBuyClicked` | `EGiftType.vipCard`, `PurchaseId[curTab]` | `dealBuyVipCardInfo()`, `getAward(...)`, VIP state update |
| 50 | 126999 | `SpecialGuestItem.onBuyClick` | `purchaseTbl.find(ID == guest.ObtainWay[1])` | guest unlock + reward UI |

## Riches / 财富日历 chain

Confirmed flow:

```text
Activity.richesInfo
  -> PlayerData.payTotal compared with Table.constById(146)
  -> beginTime / beginTime2 / beginTime3 are opened per threshold
  -> Table.giftTbl.filter(GiftType === EGiftType.Riches)
  -> each Riches gift has 3 RewardIds
  -> claim index = dayIndex + 3 * trackIndex
  -> Activity.getRichesReward(index)
  -> ServerData.saveRichesInfo(false)
  -> storage key richesInfo / d6
```

### Riches state fields

`F:\测试\cookingGO\_work\patched_12602_v134.js:10642-10651` initializes:

```js
{
  rewardGetIdx: [],
  beginTime: 0,
  dailyRedDot: false,
  firstRedDot: true,
  beginTime2: 0,
  beginTime3: 0,
  accumulateNum: 0
}
```

### Thresholds

`F:\测试\cookingGO\_work\patched_12602_v134.js:10719-10735` uses `Table.constById(146)`. The table row is in the IPA resource behind `tables/constant_tbl`:

```json
{"ID":146,"Value":[[0.99,6],[5.99,38],[21.99,128]]}
```

| Track | Overseas threshold | Inland threshold | Open field |
|---:|---:|---:|---|
| 0 | `0.99` | `6` | `richesInfo.beginTime` |
| 1 | `5.99` | `38` | `richesInfo.beginTime2` |
| 2 | `21.99` | `128` | `richesInfo.beginTime3` |

### Riches gifts and rewards

`EGiftType.Riches = 28`, confirmed at `F:\测试\cookingGO\_work\patched_12602_v134.js:129803`.

`gift_tbl` contains three `GiftType:28` rows:

| Track | Gift ID | PurchaseId | RewardIds |
|---:|---:|---|---|
| 0 | `28` | `[]` | `[4001,4002,4003]` |
| 1 | `31` | `[]` | `[4004,4005,4006]` |
| 2 | `32` | `[]` | `[4007,4008,4009]` |

Claim index mapping:

| Track | Day | Reward ID | Claim index |
|---:|---:|---:|---:|
| 0 | 0 | 4001 | 0 |
| 0 | 1 | 4002 | 1 |
| 0 | 2 | 4003 | 2 |
| 1 | 0 | 4004 | 3 |
| 1 | 1 | 4005 | 4 |
| 1 | 2 | 4006 | 5 |
| 2 | 0 | 4007 | 6 |
| 2 | 1 | 4008 | 7 |
| 2 | 2 | 4009 | 8 |

Reward row summary from `static_reward_tbl`:

| Reward ID | CoinNumExpansion | RewardPropIDs | RewardPropNum | HeadFrameID | ClothIDs |
|---:|---:|---|---|---|---|
| 4001 | 5 | `[2]` | `[1]` | `[]` | `[]` |
| 4002 | 10 | `[46]` | `[5]` | `[]` | `[]` |
| 4003 | 15 | `[5,7]` | `[1,1]` | `[]` | `[]` |
| 4004 | 15 | `[46]` | `[5]` | `[]` | `[]` |
| 4005 | 20 | `[47]` | `[5]` | `[]` | `[]` |
| 4006 | 25 | `[7]` | `[2]` | `[6]` | `[]` |
| 4007 | 20 | `[48]` | `[5]` | `[]` | `[]` |
| 4008 | 25 | `[48]` | `[5]` | `[]` | `[]` |
| 4009 | 30 | `[7]` | `[3]` | `[]` | `[2001]` |

### Claim and persistence evidence

| Path | Evidence |
|---|---|
| `F:\测试\cookingGO\_work\patched_12602_v134.js:10667-10671` | `getRichesReward(e)` pushes `e` into `rewardGetIdx`, saves Riches info, updates red dot. |
| `F:\测试\cookingGO\_work\patched_12602_v134.js:10710-10711` | all claimed when `rewardGetIdx.length >= 9`. |
| `F:\测试\cookingGO\_work\patched_12602_v134.js:125261-125278` | UI claim uses `Activity.getRichesReward(e + 3 * this.curIdx)`. |
| `F:\测试\cookingGO\_work\patched_12602_v134.js:121701` | storage map contains `d6: "richesInfo"`. |
| `F:\测试\cookingGO\_work\patched_12602_v134.js:121751` | reverse map contains `richesInfo: "d6"`. |
| `F:\测试\cookingGO\_work\patched_12602_v134.js:121987-121990` | `saveRichesInfo(false)` persists `gameData.richesInfo`. |

## Current bootstrap harness

`F:\测试\cookingGO\github-cookinggo-mod\tools\mock_cgm_bootstrap.js` validates the local JS bootstrap without a device.

Coverage:

- missing `jsb.fileUtils` abort path;
- mailbox discovery and fallback candidate;
- `js_hello.json`, `state.json`, `probe.json`, `res.json` writes;
- `Manager` missing and `PlayerData.playerInfo` late-load diagnostics;
- unknown resource and bad numeric input error responses;
- `cmd.seq` and `probe_cmd.seq` de-duplication;
- file read/write exception containment;
- default-off IAP state: `state.iapHook === 0`;
- default-off `Manager.Pay.pay` wrapper passes calls to the original implementation and does not synthesize `OnSuccess`.

Run:

```powershell
node F:\测试\cookingGO\github-cookinggo-mod\tools\mock_cgm_bootstrap.js
```

Expected:

```text
11/11 tests passed
```

## Device-test gate

Device control is now permitted by the operator, but the current evidence above does not require device access. Recommended next device action is diagnostic-only: launch/read mailbox/logs to confirm runtime handshake freshness (`js_hello.json`, `state.json`, `probe.json`) after local static and harness checks pass.
