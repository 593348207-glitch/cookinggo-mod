/* =========================================================================
 * CookingGo Mod - JS bootstrap payload
 * Target : Cooking GO 1.25.03/1.26.02 (Cocos Creator 2.4.11 + cocos2d-x lite + V8)
 * Injected by CookingGoMod.dylib at the end of assets/scriptBundle/index.js
 * Evidence for access path (static analysis, 2026-09-12):
 *   window.__require            -> module table of scriptBundle/index.js (775 modules)
 *   __require("Game").default   -> module "Game" default export, class with static
 *                                  fields PlayerData/MapData/Event/... filled in
 *                                  _loadAllManagers()
 *   __require("AppConst").EVENT_ID.UPDATE_GEM / UPDATE_COIN / UPDATE_POWER /
 *                                  UPDATE_AD_COUPON / UPDATE_PROP_NUM
 *   __require("Core").default.Event -> event bus used by every UI controller
 *   PlayerDataMgr: get/set gemNum, get/set powerNum, get adCouponNum,
 *                  setPropNum(propId, num)   (EPropID.AdCoupon === 57)
 *   MapDataMgr   : get/set mapCoinNum
 * ========================================================================= */
;(function cookingModBootstrapEntry() {
  var VERSION = "1.4.2";
  var TAG = "[CookingMod]";

  function log(s) {
    try { console.log(TAG + " " + s); } catch (e) {}
  }
  function str(e) {
    try { return String(e && e.message ? e.message : e); } catch (x) { return "unknown-error"; }
  }

  function retryBoot(reason) {
    try {
      window.__cookingModBootTries = (window.__cookingModBootTries || 0) + 1;
      if (window.__cookingModBootTries > 80) {
        log("bootstrap deferred limit reached: " + reason);
        return;
      }
      if (window.__cookingModBootPending) { return; }
      window.__cookingModBootPending = true;
      log("bootstrap deferred: " + reason + " try=" + window.__cookingModBootTries);
      setTimeout(function () {
        try { window.__cookingModBootPending = false; } catch (e) {}
        cookingModBootstrapEntry();
      }, 250);
    } catch (e) {
      log("bootstrap retry unavailable: " + str(e));
    }
  }

  try {
    if (window.__cookingMod && window.__cookingMod.version) {
      if (window.__cookingMod.version === VERSION) {
        log("bootstrap skipped, already v" + window.__cookingMod.version);
        return;
      }
      try { delete window.__cookingMod; } catch (x) {}
      log("bootstrap version refresh " + window.__cookingMod.version + " -> " + VERSION);
    }
  } catch (e) {}

  var fs = null;
  try { fs = (window.jsb && window.jsb.fileUtils) ? window.jsb.fileUtils : null; } catch (e) { fs = null; }
  if (!fs) { retryBoot("jsb.fileUtils unavailable"); return; }

  function readFile(p) {
    try { var s = fs.getStringFromFile(p); return (typeof s === "string") ? s : ""; } catch (e) { return ""; }
  }
  function writeFile(p, s) {
    try { return !!fs.writeStringToFile(s, p); } catch (e) { return false; }
  }
  function readJson(p) { var s = readFile(p); if (!s) { return null; } try { return JSON.parse(s); } catch (e) { return null; } }
  function writeJson(p, o) { return writeFile(p, JSON.stringify(o)); }

  /* ---------------- mailbox discovery (native created the folder) ---------- */
  var writable = null;
  try { writable = fs.getWritablePath(); } catch (e) {}
  var cands = [];
  if (writable) {
    var base = (writable.charAt(writable.length - 1) === "/") ? writable : (writable + "/");
    cands.push(base + "cookingmod/");
    cands.push(base + "../cookingmod/");
    cands.push(base + "../../cookingmod/");
  }
  function canCreate(dir) { try { fs.createDirectory(dir); return true; } catch (e) { return false; } }
  var DIR = null;
  for (var i = 0; i < cands.length; i++) {
    var d = cands[i];
    canCreate(d);
    if (readFile(d + "mod.json")) { DIR = d; break; }
    if (writeJson(d + "js_probe.json", { ts: now(), version: VERSION }) && readFile(d + "js_probe.json")) {
      DIR = d;
      break;
    }
  }
  if (!DIR) {
    log("mailbox not found, candidates=" + JSON.stringify(cands));
    retryBoot("mailbox not found");
    return;
  }
  log("mailbox=" + DIR + " writable=" + writable);
  try { window.__cookingModBootPending = false; } catch (e) {}

  function now() { return (new Date()).getTime(); }
  writeJson(DIR + "js_hello.json", { version: VERSION, dir: DIR, writable: writable, sessionGen: gSessionGen, sessionKey: gSessionKey, ts: now() });

  /* ---------------- engine binding ----------------------------------------- */
  var G = null, APP = null, CORE = null, PD = null, MD = null;
  var gSessionGen = 0;
  var gSessionKey = "session-0";
  var gSessionReady = true;
  var gBound = null;
  var gHookedPay = null, gHookedIOS = null;
  var lastSeq = -1;
  var gProbeSeq = 0;
  /* Riches thresholds and GiftType are static-evidence-backed. The purchase
     catalog itself is always read from the live Table manager; no SKU or
     purchase ID is invented here. */
  var RICHES_GIFT_TYPE = 28;
  var RICHES_CONST_ID = 146;
  var RICHES_DEFAULT_THRESHOLDS = [ 0.99, 5.99, 21.99 ];
  var gSimulatedOrders = {};

  function req(name) {
    try { return window.__require(name); } catch (e) { return null; }
  }

  function refTag(value) {
    if (!value || (typeof value !== "object" && typeof value !== "function")) {
      return String(value || "0");
    }
    try {
      if (!window.__cookingModRefObjects) { window.__cookingModRefObjects = []; }
      var list = window.__cookingModRefObjects;
      for (var i = 0; i < list.length; i++) {
        if (list[i].value === value) { return "r" + list[i].id; }
      }
      var item = { value: value, id: list.length + 1 };
      list.push(item);
      return "r" + item.id;
    } catch (e) { return "object"; }
  }

  function identityHint(obj, keys) {
    if (!obj) { return ""; }
    for (var i = 0; i < keys.length; i++) {
      try {
        var v = obj[keys[i]];
        if ((typeof v === "string" && v.length > 0) ||
            (typeof v === "number" && isFinite(v))) {
          return keys[i] + "=" + String(v);
        }
      } catch (e) {}
    }
    return "";
  }

  function sessionFingerprint(mgr, pd) {
    var info = null, auth = null;
    try { info = pd && pd.playerInfo; } catch (e) {}
    try { auth = mgr && (mgr.Auth || mgr.Account || mgr.User); } catch (e) {}
    var keys = ["uid", "userId", "playerId", "accountId", "roleId", "openId", "openid", "id"];
    var hint = identityHint(info, keys) || identityHint(auth, keys);
    return (hint ? hint + "|" : "") + "info:" + refTag(info) + "|auth:" + refTag(auth);
  }

  function removeFile(path) {
    try {
      if (fs && typeof fs.removeFile === "function") { return !!fs.removeFile(path); }
    } catch (e) {}
    return false;
  }

  function restoreHook(target, method) {
    if (!target) { return; }
    try {
      var original = target.__cookingModIapHookOriginal;
      if (target.__cookingModIapHook && typeof original === "function") { target[method] = original; }
      delete target.__cookingModIapHook;
      delete target.__cookingModIapHookOriginal;
      delete target.__cookingModIapHookWrapper;
    } catch (e) { log("restore " + method + " hook failed: " + str(e)); }
  }

  function resetSessionState(reason, refs) {
    var oldKey = gSessionKey;
    var wasBound = !!gBound;
    gSessionGen++;
    gSessionKey = "session-" + gSessionGen;
    gSessionReady = !wasBound;
    lastSeq = -1;
    gProbeSeq = 0;
    try { window.__cookingModProbeSeq = null; } catch (e) {}
    restoreHook(gHookedPay, "pay");
    restoreHook(gHookedIOS, "buyProduct");
    gHookedPay = null;
    gHookedIOS = null;
    if (gIap) {
      gIap.installedPay = false;
      gIap.installedIOS = false;
      gIap.last = "session-rebind:" + gSessionKey;
    }
    ["cmd.json", "res.json", "state.json", "probe.json", "probe_cmd.json"].forEach(function (name) {
      removeFile(DIR + name);
    });
    writeJson(DIR + "js_hello.json", {
      version: VERSION, dir: DIR, sessionGen: gSessionGen, sessionKey: gSessionKey,
      ready: gSessionReady, rebind: !gSessionReady,
      previousSession: oldKey, reason: reason || "binding changed", ts: now()
    });
    if (gIap) { saveIapState(); }
    gSimulatedOrders = {};
    log("session rebind " + oldKey + " -> " + gSessionKey + " reason=" + (reason || "binding changed"));
  }

  /* Evidence (static analysis + on-device probe, 2026-09-12):
     __require("Game")    -> cc.Component scene controller, NOT the data holder
     __require("Manager") -> the manager singleton whose static props are
                             assigned in _loadAllManagers(): PlayerData,
                             MapData, ServerData, Auth, Pay, ...            */
  var gBindWhy = "not attempted";

  function bind() {
    var m = req("Manager");
    if (!m || !m.default) { gBindWhy = "module Manager missing"; return false; }
    var app = req("AppConst");
    if (!app || !app.EVENT_ID) { gBindWhy = "AppConst.EVENT_ID missing"; return false; }
    var core = req("Core");
    if (!core || !core.default) { gBindWhy = "module Core missing"; return false; }
    var mgr = m.default;
    var pd = null, md = null, pay = null, vip = null, ios = null;
    try { pd = mgr.PlayerData; md = mgr.MapData; pay = mgr.Pay || null; vip = mgr.VipCard || null; } catch (e) {}
    try { var iosMod = req("YiFaniOSIAPBridge"); ios = iosMod && iosMod.default || null; } catch (e) {}
    if (!pd) { gBindWhy = "Manager.PlayerData missing"; return false; }
    if (!md) { gBindWhy = "Manager.MapData missing"; return false; }
    try {
      if (!pd.playerInfo) { gBindWhy = "PlayerData.playerInfo not loaded yet"; return false; }
    } catch (e) {
      gBindWhy = "PlayerData.playerInfo threw: " + str(e);
      return false;
    }
    var fingerprint = sessionFingerprint(mgr, pd);
    var refs = { mgr: mgr, pd: pd, md: md, pay: pay, vip: vip, ios: ios, fingerprint: fingerprint };
    var changed = !gBound || gBound.mgr !== refs.mgr || gBound.pd !== refs.pd ||
      gBound.md !== refs.md || gBound.pay !== refs.pay || gBound.vip !== refs.vip ||
      gBound.ios !== refs.ios || gBound.fingerprint !== refs.fingerprint;
    G = mgr; APP = app; CORE = core.default; PD = pd; MD = md;
    if (changed) {
      resetSessionState(gBound ? "manager/session identity changed" : "initial bind", refs);
      gBound = refs;
      installIapHook();
      log("bound session=" + gSessionKey + " Manager.PlayerData/MapData/Pay/VipCard refreshed");
    } else if (!gSessionReady) {
      /* Publish one complete state tick before accepting commands after a
         rebind. Native uses this handshake to avoid the mailbox cleanup
         race during account switching. */
      gSessionReady = true;
      writeJson(DIR + "js_hello.json", {
        version: VERSION, dir: DIR, sessionGen: gSessionGen, sessionKey: gSessionKey,
        ready: true, rebind: false, reason: "session ready", ts: now()
      });
      log("session ready " + gSessionKey);
    }
    gBindWhy = "ok";
    return true;
  }

  /* ServerConst.EPropID (verified in scriptBundle/index.js):
       45 = ClothNum  -> PlayerData.clothingCionNum  (换装币)
       57 = AdCoupon  -> PlayerData.adCouponNum      (免广告券)            */
  var EPropID_ClothNum = 45;
  var EPropID_AdCoupon = 57;
  var IAP_STATE_FILE = "iap_hook.json";
  var gIap = { enabled: false, installedPay: false, installedIOS: false, last: "init" };

  function loadIapState() {
    var st = readJson(DIR + IAP_STATE_FILE);
    if (st && typeof st.enabled !== "undefined") { gIap.enabled = !!st.enabled; }
    gIap.last = "loaded:" + (gIap.enabled ? "on" : "off");
  }

  function saveIapState() {
    writeJson(DIR + IAP_STATE_FILE, {
      enabled: !!gIap.enabled,
      installedPay: !!gIap.installedPay,
      installedIOS: !!gIap.installedIOS,
      sessionGen: gSessionGen,
      sessionKey: gSessionKey,
      last: gIap.last,
      ts: now(),
      version: VERSION
    });
  }

  function asId(v) {
    var n = Number(v);
    return isFinite(n) ? Math.floor(n) : 0;
  }

  function findVipGiftTbl() {
    try {
      var gt = G && G.Table && G.Table.giftTbl;
      if (!Array.isArray(gt)) { return null; }
      for (var i = 0; i < gt.length; i++) {
        var g = gt[i];
        if (!g || !Array.isArray(g.PurchaseId)) { continue; }
        var ids = g.PurchaseId.map(asId);
        if (ids.indexOf(87) >= 0 || ids.indexOf(90) >= 0 || ids.indexOf(86) >= 0) { return g; }
      }
    } catch (e) {}
    return null;
  }

  function monthPurchaseId() {
    var g = findVipGiftTbl();
    if (g && Array.isArray(g.PurchaseId)) {
      var ids = g.PurchaseId.map(asId).filter(function (x) { return x > 0; });
      if (ids.indexOf(87) >= 0) { return 87; }
      if (ids.length > 1) { return ids[1]; }
      if (ids.indexOf(90) >= 0) { return 90; }
      if (ids.length) { return ids[0]; }
    }
    return 87;
  }

  function findPurchaseTbl(id) {
    try {
      var pt = G && G.Table && G.Table.purchaseTbl;
      if (!Array.isArray(pt)) { return null; }
      for (var i = 0; i < pt.length; i++) if (asId(pt[i] && pt[i].ID) === asId(id)) return pt[i];
    } catch (e) {}
    return null;
  }

  function purchaseIdOf(p) {
    if (!p) { return 0; }
    return asId(p.ID || p.id || p.purchaseId || p.PurchaseId || p.productId);
  }

  function moneyNum(v) {
    var n = Number(v);
    if (!isFinite(n)) { return null; }
    return Math.round(n * 100) / 100;
  }

  function firstNumber(obj, keys) {
    if (!obj) { return null; }
    for (var i = 0; i < keys.length; i++) {
      try {
        if (obj[keys[i]] === null || typeof obj[keys[i]] === "undefined" || obj[keys[i]] === "") { continue; }
        var n = moneyNum(obj[keys[i]]);
        if (n !== null) { return n; }
      } catch (e) {}
    }
    return null;
  }

  function purchasePriceOf(p) {
    return firstNumber(p, [ "Price", "price", "priceUsd", "priceUSD", "amount" ]);
  }

  function purchaseProductIdOf(p) {
    if (!p) { return ""; }
    var keys = [ "ProductIDiOSOversea", "ProductIDiOSInland", "ProductID", "ProductId", "productId", "ProductIDFb" ];
    for (var i = 0; i < keys.length; i++) {
      try { if (p[keys[i]] !== null && typeof p[keys[i]] !== "undefined" && String(p[keys[i]]).length) return String(p[keys[i]]); } catch (e) {}
    }
    return "";
  }

  function giftRowsByType(type) {
    var out = [];
    try {
      var gt = G && G.Table && G.Table.giftTbl;
      if (!Array.isArray(gt)) { return out; }
      for (var i = 0; i < gt.length; i++) {
        var row = gt[i];
        if (row && asId(row.GiftType) === asId(type)) { out.push(row); }
      }
    } catch (e) {}
    return out;
  }

  function iapCatalog() {
    var purchases = [];
    var gifts = [];
    try {
      var pt = G && G.Table && G.Table.purchaseTbl;
      if (Array.isArray(pt)) {
        for (var i = 0; i < pt.length; i++) {
          var p = pt[i];
          if (!p) { continue; }
          purchases.push({
            id: purchaseIdOf(p),
            price: purchasePriceOf(p),
            productId: purchaseProductIdOf(p),
            rewardId: asId(p.RewardID) || 0
          });
        }
      }
    } catch (e) {}
    var rows = giftRowsByType(RICHES_GIFT_TYPE);
    for (var j = 0; j < rows.length; j++) {
      var g = rows[j];
      gifts.push({
        id: asId(g.ID),
        giftType: asId(g.GiftType),
        purchaseIds: Array.isArray(g.PurchaseId) ? g.PurchaseId.map(asId) : [],
        rewardIds: Array.isArray(g.RewardIds) ? g.RewardIds.map(asId) : []
      });
    }
    return {
      richesGiftType: RICHES_GIFT_TYPE,
      richesGifts: gifts,
      purchases: purchases,
      source: "Manager.Table runtime catalog"
    };
  }

  function gameServerTime() {
    try {
      var t = G && G.Http && Number(G.Http.serverTime);
      if (isFinite(t) && t > 0) { return t; }
    } catch (e) {}
    return now();
  }

  function richesThresholds() {
    var fallback = RICHES_DEFAULT_THRESHOLDS.slice(0);
    try {
      var raw = G && G.Table && typeof G.Table.constById === "function" ? G.Table.constById(RICHES_CONST_ID) : null;
      if (raw && Array.isArray(raw.Value)) { raw = raw.Value; }
      if (!Array.isArray(raw)) { return { values: fallback, source: "static-evidence-fallback" }; }
      var inland = false;
      try { inland = !!(G && G.App && G.App.IsInland); } catch (e) {}
      var out = [];
      for (var i = 0; i < 3; i++) {
        var row = raw[i];
        var value = Array.isArray(row) ? row[inland ? 1 : 0] : row;
        var n = moneyNum(value);
        out.push(n === null ? fallback[i] : n);
      }
      return { values: out, source: "Table.constById(146)" };
    } catch (e) {
      return { values: fallback, source: "static-evidence-fallback" };
    }
  }

  function richesInfoObject() {
    var gd = null;
    try { gd = G && G.ServerData && G.ServerData.gameData; } catch (e) {}
    if (!gd) { return null; }
    var info = null;
    try {
      if (G.Activity) { info = G.Activity.richesInfo; }
    } catch (e) {}
    if (!info) {
      info = gd.richesInfo || { rewardGetIdx: [], beginTime: 0, beginTime2: 0, beginTime3: 0, accumulateNum: 0, dailyRedDot: false, firstRedDot: true };
      gd.richesInfo = info;
    }
    if (!Array.isArray(info.rewardGetIdx)) { info.rewardGetIdx = []; }
    return info;
  }

  function currentPayTotal() {
    try {
      var gd = G && G.ServerData && G.ServerData.gameData;
      var n = gd && gd.playerInfo ? moneyNum(gd.playerInfo.payTotal) : null;
      if (n !== null) { return n; }
    } catch (e) {}
    try {
      var n2 = PD && PD.playerInfo ? moneyNum(PD.playerInfo.payTotal) : null;
      if (n2 !== null) { return n2; }
    } catch (e) {}
    return 0;
  }

  function setPayTotal(value) {
    var ok = false;
    try {
      /* The real PlayerData exposes a payTotal setter which also persists
         playerInfo. Use it first, then normalize the backing playerInfo for
         runtimes/mocks where the setter is absent. */
      if (PD && typeof PD.payTotal !== "undefined") { PD.payTotal = value; }
    } catch (e) {}
    try {
      var gd = G && G.ServerData && G.ServerData.gameData;
      if (gd && gd.playerInfo) { gd.playerInfo.payTotal = value; ok = true; }
    } catch (e) {}
    try {
      if (PD && PD.playerInfo && (!G.ServerData || !G.ServerData.gameData || PD.playerInfo !== G.ServerData.gameData.playerInfo)) {
        PD.playerInfo.payTotal = value;
        ok = true;
      }
    } catch (e) {}
    return ok;
  }

  function richesExtraBonusInfo(riches) {
    var gifts = giftRowsByType(RICHES_GIFT_TYPE);
    var vipGifts = giftRowsByType(24);
    var finalRiches = gifts.length > 2 ? gifts[2] : null;
    var vipGift = vipGifts.length > 0 ? vipGifts[0] : null;
    var finalRewardId = finalRiches && Array.isArray(finalRiches.RewardIds) ? asId(finalRiches.RewardIds[2]) : 0;
    var bonusPurchaseId = vipGift && Array.isArray(vipGift.PurchaseId) ? asId(vipGift.PurchaseId[0]) : 0;
    var bonusRewardId = vipGift && Array.isArray(vipGift.RewardIds) ? asId(vipGift.RewardIds[0]) : 0;
    return {
      eligible: !!(riches && riches.track2Unlocked && finalRewardId),
      granted: false,
      trigger: "claim Riches track 2 day 2",
      track: 2,
      day: 2,
      finalRichesRewardId: finalRewardId,
      bonusPurchaseId: bonusPurchaseId || null,
      bonusRewardId: bonusRewardId || null,
      source: "GiftRiches.onClickGet -> getWeekCard"
    };
  }

  function refreshRiches(shouldSave) {
    var thresholds = richesThresholds();
    var total = currentPayTotal();
    var info = richesInfoObject();
    var fields = [ "beginTime", "beginTime2", "beginTime3" ];
    if (info) {
      var t = gameServerTime();
      for (var i = 0; i < fields.length; i++) {
        if (total >= thresholds.values[i] && !Number(info[fields[i]])) { info[fields[i]] = t; }
      }
      /* Keep the progress value used by GiftRichesData in sync with payTotal,
         so opening the calendar immediately after the test reflects 100 USD. */
      if (Number(info.accumulateNum) < total) { info.accumulateNum = total; }
      if (shouldSave !== false) {
        try {
          if (G.ServerData && typeof G.ServerData.saveRichesInfo === "function") { G.ServerData.saveRichesInfo(false); }
        } catch (e) { log("saveRichesInfo failed: " + str(e)); }
      }
    }
    var result = {
      payTotal: total,
      thresholds: thresholds.values,
      thresholdSource: thresholds.source,
      beginTime: info ? Number(info.beginTime) || 0 : 0,
      beginTime2: info ? Number(info.beginTime2) || 0 : 0,
      beginTime3: info ? Number(info.beginTime3) || 0 : 0,
      track0Unlocked: !!(info && Number(info.beginTime) > 0),
      track1Unlocked: !!(info && Number(info.beginTime2) > 0),
      track2Unlocked: !!(info && Number(info.beginTime3) > 0)
    };
    result.extraBonus = richesExtraBonusInfo(result);
    return result;
  }

  function simulatedOrderExists(orderId) {
    if (!orderId) { return false; }
    if (gSimulatedOrders[orderId]) { return true; }
    try {
      var pi = G && G.PayData && G.PayData.payInfo;
      if (Array.isArray(pi)) {
        for (var i = 0; i < pi.length; i++) if (String(pi[i] && pi[i].orderId) === orderId) return true;
      }
    } catch (e) {}
    return false;
  }

  function simulatePurchase(cmd) {
    var out = { ok: false, res: "purchase_sim", action: cmd.action || "success", localOnly: true, version: VERSION, sessionGen: gSessionGen, sessionKey: gSessionKey, ts: now() };
    if (cmd.localOnly !== true) { out.error = "purchase_sim requires localOnly=true"; return out; }
    if (!bind()) { out.error = "engine not bound: " + gBindWhy; return out; }
    var before = currentPayTotal();
    var target = cmd.targetPayTotal !== undefined ? moneyNum(cmd.targetPayTotal) : null;
    if (target !== null && (target < 0 || target > 1000)) { out.error = "bad target payTotal"; return out; }
    var amount = cmd.amount !== undefined ? moneyNum(cmd.amount) : moneyNum(cmd.value);
    if (cmd.amountCents !== undefined) { amount = moneyNum(Number(cmd.amountCents) / 100); }
    if (target !== null) {
      if (target < before) { out.error = "target payTotal is below current payTotal"; out.payTotalBefore = before; return out; }
      amount = moneyNum(target - before);
    }
    if (amount === null || amount < 0 || amount > 1000) { out.error = "bad purchase amount"; return out; }
    var orderId = String(cmd.orderId || ("cgm_local_" + gSessionKey + "_" + cmd.seq));
    out.orderId = orderId;
    out.targetPayTotal = target;
    if (simulatedOrderExists(orderId)) {
      var duplicate = refreshRiches(true);
      out.ok = true;
      out.duplicate = true;
      out.amount = amount;
      out.payTotalBefore = duplicate.payTotal;
      out.payTotalAfter = duplicate.payTotal;
      out.riches = duplicate;
      out.message = "local purchase replay ignored: orderId=" + orderId;
      return out;
    }
    if (amount === 0) {
      var already = refreshRiches(true);
      out.ok = true;
      out.alreadyAtTarget = true;
      out.amount = 0;
      out.recorded = false;
      out.payTotalBefore = before;
      out.payTotalAfter = already.payTotal;
      out.riches = already;
      out.richesTrack0Unlocked = already.track0Unlocked;
      out.message = "local Riches target already reached; no additional order recorded";
      return out;
    }
    var purchaseId = asId(cmd.purchaseId);
    var purchase = purchaseId ? findPurchaseTbl(purchaseId) : null;
    var catalogPrice = purchasePriceOf(purchase);
    if (cmd.requireCatalog === true && !purchase) { out.error = "purchaseId not found in runtime catalog"; return out; }
    if (purchase && catalogPrice !== null && cmd.allowPriceOverride !== true && Math.abs(catalogPrice - amount) > 0.001) {
      out.error = "amount does not match purchaseTbl.Price";
      out.catalogPrice = catalogPrice;
      return out;
    }
    var after = moneyNum(before + amount);
    if (after === null || !setPayTotal(after)) { out.error = "playerInfo.payTotal unavailable"; return out; }
    var recorded = false;
    try {
      var payData = G && G.PayData;
      if (payData && typeof payData.addPayData === "function") {
        payData.addPayData(purchaseId, amount, orderId);
        recorded = true;
      }
    } catch (e) { log("local PayData.addPayData failed: " + str(e)); }
    try {
      var pi = G && G.PayData && G.PayData.payInfo;
      if (!recorded && Array.isArray(pi)) {
        pi.unshift({ purchaseId: purchaseId, price: amount, time: gameServerTime(), orderId: orderId });
        try { if (G.ServerData && typeof G.ServerData.savePayInfo === "function") G.ServerData.savePayInfo(false); } catch (e) {}
        recorded = true;
      }
    } catch (e) {}
    gSimulatedOrders[orderId] = { amount: amount, targetPayTotal: target, purchaseId: purchaseId, ts: now(), sessionGen: gSessionGen };
    var riches = refreshRiches(true);
    out.ok = true;
    out.amount = amount;
    out.purchaseId = purchaseId || null;
    out.catalogPrice = catalogPrice;
    out.recorded = recorded;
    out.payTotalBefore = before;
    out.payTotalAfter = riches.payTotal;
    out.riches = riches;
    out.richesTrack0Unlocked = riches.track0Unlocked;
    out.message = target !== null
      ? "local Riches target simulated; payTotal reached " + riches.payTotal.toFixed(2) + " USD; no App Store transaction was created"
      : "local purchase simulated; no App Store transaction was created";
    return out;
  }

  function isVipPurchase(p) {
    var id = purchaseIdOf(p);
    var g = findVipGiftTbl();
    if (g && Array.isArray(g.PurchaseId) && g.PurchaseId.map(asId).indexOf(id) >= 0) { return true; }
    return [ 86, 87, 82, 89, 90, 91 ].indexOf(id) >= 0;
  }

  function isVipSku(sku) {
    var s = String(sku || "").toLowerCase();
    return /vip|month|monthly|card|87|90/.test(s);
  }

  function emitResourceUpdates() {
    try { CORE.Event.emit(APP.EVENT_ID.UPDATE_GEM, PD.gemNum, true); } catch (e) {}
    try { CORE.Event.emit(APP.EVENT_ID.UPDATE_POWER, PD.powerNum); } catch (e) {}
    try { CORE.Event.emit(APP.EVENT_ID.UPDATE_AD_COUPON, PD.adCouponNum); } catch (e) {}
    try { CORE.Event.emit(APP.EVENT_ID.UPDATE_PROP_NUM, EPropID_AdCoupon, PD.adCouponNum); } catch (e) {}
    try { CORE.Event.emit(APP.EVENT_ID.UPDATE_GIFT_MENU_NUM); } catch (e) {}
  }

  function findRewardTbl(id) {
    try {
      var rt = G && G.Table && G.Table.rewardTbl;
      if (!Array.isArray(rt)) { return null; }
      for (var i = 0; i < rt.length; i++) if (asId(rt[i] && rt[i].ID) === asId(id)) return rt[i];
    } catch (e) {}
    return null;
  }

  function applyRewardById(rewardId) {
    var tbl = findRewardTbl(rewardId);
    if (!tbl) { return false; }
    try {
      if (G.Reward && typeof G.Reward.getReward === "function") {
        G.Reward.getReward(tbl, false, [ 8, 8, 8 ]);
        if (typeof G.Reward.updateRewardDisplay === "function") { G.Reward.updateRewardDisplay(tbl); }
        return true;
      }
    } catch (e) { log("Reward.getReward failed: " + str(e)); }
    return false;
  }

  function vipSummary() {
    var v = null;
    try { v = G && G.VipCard; } catch (e) { v = null; }
    var d = null;
    try { d = v && v.vipCardData; } catch (e) { d = null; }
    return {
      active: !!(v && v.isVipEffectTime),
      type: d && typeof d.type !== "undefined" ? d.type : null,
      beginT: d && d.beginT || 0,
      endT: v && v.vipEndTimes || (d && d.endT) || 0,
      leftSeconds: v ? Math.floor(Number(v.getVipLeftTime ? v.getVipLeftTime() : 0)) : 0,
      payDataCount: d && Array.isArray(d.payData) ? d.payData.length : 0,
      hasGetDayNames: d && Array.isArray(d.hasGetDayNames) ? d.hasGetDayNames.length : 0
    };
  }

  function grantVipCardDirect() {
    var out = { ok: false, res: "vip_card", action: "buy", input: 30, before: null, after: null, ts: now(), version: VERSION, sessionGen: gSessionGen, sessionKey: gSessionKey };
    if (!bind()) { out.error = "engine not bound: " + gBindWhy; return out; }
    installIapHook();
    out.before = vipSummary();
    try {
      var vip = G.VipCard;
      if (!vip || typeof vip.setPlayerVipDataByGiftId !== "function") { throw new Error("Manager.VipCard.setPlayerVipDataByGiftId missing"); }
      var candidates = [];
      var mid = monthPurchaseId();
      candidates.push(mid, 87, 90, 86, 89, 91, 82);
      var used = 0;
      for (var i = 0; i < candidates.length; i++) {
        var id = asId(candidates[i]);
        if (!id || candidates.indexOf(id) !== i) { continue; }
        try {
          vip.setPlayerVipDataByGiftId(id, true);
          used = id;
          if (vip.isVipEffectTime) { break; }
        } catch (x) {}
      }
      if (!vip.isVipEffectTime) { throw new Error("vip state still inactive after setPlayerVipDataByGiftId"); }
      try { if (G.ServerData && G.ServerData.saveVipCardData) G.ServerData.saveVipCardData(false); } catch (e) {}
      out.purchaseId = used || mid;
      out.purchaseTbl = findPurchaseTbl(used || mid);
      var rewardId = 0;
      try { rewardId = asId(out.purchaseTbl && out.purchaseTbl.RewardID); } catch (e) { rewardId = 0; }
      if (!rewardId) {
        var gift = findVipGiftTbl();
        if (gift && Array.isArray(gift.PurchaseId) && Array.isArray(gift.RewardIds)) {
          var gi = gift.PurchaseId.map(asId).indexOf(asId(out.purchaseId));
          if (gi >= 0) { rewardId = asId(gift.RewardIds[gi]); }
        }
      }
      out.rewardId = rewardId;
      out.rewardApplied = rewardId ? applyRewardById(rewardId) : false;
      emitResourceUpdates();
      out.ok = true;
      out.after = vipSummary();
      out.expr = "grant monthly vip-card purchaseId=" + out.purchaseId + " rewardId=" + rewardId;
      out.message = "月卡发放完成: purchaseId=" + out.purchaseId + " rewardId=" + rewardId + " rewardApplied=" + (out.rewardApplied ? 1 : 0) + " endT=" + out.after.endT + " leftSeconds=" + out.after.leftSeconds;
      gIap.last = out.message;
      saveIapState();
    } catch (e) {
      out.error = str(e);
      gIap.last = "grant failed: " + out.error;
      saveIapState();
    }
    return out;
  }

  function installIapHook() {
    if (!G) { return false; }
    try {
      var pay = G.Pay;
      if (gHookedPay && gHookedPay !== pay) { restoreHook(gHookedPay, "pay"); gHookedPay = null; gIap.installedPay = false; }
      if (pay && typeof pay.pay === "function" && !pay.__cookingModIapHook) {
        var origPay = pay.pay;
        pay.__cookingModIapHookOriginal = origPay;
        pay.__cookingModIapHook = true;
        pay.pay = function (purchaseTbl, cb) {
          try {
            if (gIap.enabled && isVipPurchase(purchaseTbl)) {
              var pid = purchaseIdOf(purchaseTbl) || monthPurchaseId();
              gIap.last = "Pay.pay intercepted purchaseId=" + pid;
              saveIapState();
              setTimeout(function () {
                try { cb && typeof cb.OnSuccess === "function" && cb.OnSuccess({ cookingMod: true, orderId: "cgm_vip_" + now(), purchaseId: pid }); }
                catch (x) { log("fake OnSuccess error: " + str(x)); }
              }, 0);
              return Promise.resolve({ cookingMod: true, code: 200, status: 1, purchaseId: pid });
            }
          } catch (e) { log("Pay.pay hook error: " + str(e)); }
          return origPay.apply(this, arguments);
        };
        pay.__cookingModIapHookWrapper = pay.pay;
        gHookedPay = pay;
        gIap.installedPay = true;
        log("IAP hook installed on Manager.Pay.pay session=" + gSessionKey);
      }
    } catch (e) { log("install Pay hook failed: " + str(e)); }

    try {
      var iosMod = req("YiFaniOSIAPBridge");
      var ios = iosMod && iosMod.default;
      if (gHookedIOS && gHookedIOS !== ios) { restoreHook(gHookedIOS, "buyProduct"); gHookedIOS = null; gIap.installedIOS = false; }
      if (ios && typeof ios.buyProduct === "function" && !ios.__cookingModIapHook) {
        var origIOSBuy = ios.buyProduct;
        ios.__cookingModIapHookOriginal = origIOSBuy;
        ios.__cookingModIapHook = true;
        ios.buyProduct = function (sku, onDone, onValidate) {
          try {
            if (gIap.enabled && isVipSku(sku)) {
              gIap.last = "YiFaniOSIAPBridge.buyProduct intercepted sku=" + sku;
              saveIapState();
              var ret = { cookingMod: true, status: "success", code: 0, productId: sku, transactionId: "cgm_tx_" + now() };
              setTimeout(function () {
                try { typeof onDone === "function" && onDone(ret); } catch (x) {}
                try { typeof onValidate === "function" && onValidate(ret); } catch (x) {}
              }, 0);
              return Promise.resolve(ret);
            }
          } catch (e) { log("iOS bridge hook error: " + str(e)); }
          return origIOSBuy.apply(this, arguments);
        };
        ios.__cookingModIapHookWrapper = ios.buyProduct;
        gHookedIOS = ios;
        gIap.installedIOS = true;
        log("IAP hook installed on YiFaniOSIAPBridge.buyProduct session=" + gSessionKey);
      }
    } catch (e) {}
    return !!(gIap.installedPay || gIap.installedIOS);
  }

  loadIapState();

  function table() {
    var E = APP.EVENT_ID;
    return {
      gem: {
        label: "\u94bb\u77f3",
        get: function () { return PD.gemNum; },
        set: function (v) { PD.gemNum = v; },
        emit: function () {
          try { CORE.Event.emit(E.UPDATE_GEM, PD.gemNum, true); } catch (e) {}
        }
      },
      coin: {
        label: "\u91d1\u5e01",
        get: function () { return MD.mapCoinNum; },
        set: function (v) { MD.mapCoinNum = v; },
        emit: function () {
          try { CORE.Event.emit(E.UPDATE_COIN, MD.mapCoinNum); } catch (e) {}
          try { CORE.Event.emit(E.UPDATE_MAXMAP_COIN); } catch (e) {}
        }
      },
      power: {
        label: "\u71c3\u6cb9",
        get: function () { return PD.powerNum; },
        set: function (v) { PD.powerNum = v; },
        emit: function () {
          try { CORE.Event.emit(E.UPDATE_POWER, PD.powerNum); } catch (e) {}
        }
      },
      adcoupon: {
        label: "\u514d\u5e7f\u544a\u5238",
        get: function () { return PD.adCouponNum; },
        set: function (v) { PD.setPropNum(EPropID_AdCoupon, v); },
        emit: function () {
          try { CORE.Event.emit(E.UPDATE_AD_COUPON, PD.adCouponNum); } catch (e) {}
          try { CORE.Event.emit(E.UPDATE_PROP_NUM, EPropID_AdCoupon, PD.adCouponNum); } catch (e) {}
        }
      },
      cloth: {
        label: "\u6362\u88c5\u5e01",
        /* PlayerData.clothingCionNum is a getter over
           getPropNum(EPropID.ClothNum)[EIdIdx.val]; there is no setter,
           so writes go through setPropNum like the ad coupon. */
        get: function () { return PD.clothingCionNum; },
        set: function (v) { PD.setPropNum(EPropID_ClothNum, v); },
        emit: function () {
          try { CORE.Event.emit(E.UPDATE_CLOTHINGCOIN, PD.clothingCionNum); } catch (e) {}
          try { CORE.Event.emit(E.UPDATE_PROP_NUM, EPropID_ClothNum, PD.clothingCionNum); } catch (e) {}
        }
      }
    };
  }

  function snapshot() {
    if (!gBound || !PD || !MD) { return null; }
    installIapHook();
    var t = table(), out = { ready: gSessionReady, rebind: !gSessionReady, ts: now(), version: VERSION, why: gBindWhy, sessionGen: gSessionGen, sessionKey: gSessionKey };
    for (var k in t) {
      try { out[k] = Number(t[k].get()); } catch (e) { out[k] = null; out[k + "_err"] = str(e); }
    }
    out.iapHook = gIap.enabled ? 1 : 0;
    out.iapHookInstalledPay = gIap.installedPay ? 1 : 0;
    out.iapHookInstalledIOS = gIap.installedIOS ? 1 : 0;
    out.iapLast = gIap.last;
    out.payTotal = currentPayTotal();
    try { out.riches = refreshRiches(false); } catch (e) { out.riches_err = str(e); }
    try { out.vip = vipSummary(); } catch (e) { out.vip_err = str(e); }
    return out;
  }

  function safeNum(v) {
    var n = Number(v);
    if (!isFinite(n)) { return null; }
    n = Math.floor(n);
    if (n < 0) { n = 0; }
    if (n > 2000000000) { n = 2000000000; }
    return n;
  }

  function execute(cmd) {
    var res = { seq: cmd.seq, res: cmd.res, action: cmd.action, input: cmd.value, ts: now(), version: VERSION, sessionGen: gSessionGen, sessionKey: gSessionKey };
    if (typeof cmd.sessionGen === "number" && cmd.sessionGen !== gSessionGen) {
      res.ok = false; res.error = "stale command sessionGen=" + cmd.sessionGen + " current=" + gSessionGen; return res;
    }
    if (cmd.res === "iap_catalog") {
      if (!bind()) { res.ok = false; res.error = "engine not bound (PlayerData not ready)"; return res; }
      res.ok = true;
      res.catalog = iapCatalog();
      return res;
    }
    if (cmd.res === "purchase_sim") {
      var ps = simulatePurchase(cmd);
      ps.seq = cmd.seq;
      return ps;
    }
    if (cmd.res === "iap_hook") {
      var iapBefore = !!gIap.enabled;
      gIap.enabled = (cmd.action === "on") || (cmd.action === "toggle" ? !!cmd.value : !!cmd.value);
      if (bind()) { installIapHook(); }
      gIap.last = "toggle:" + (gIap.enabled ? "on" : "off");
      saveIapState();
      res.ok = true;
      res.before = iapBefore ? 1 : 0;
      res.after = gIap.enabled ? 1 : 0;
      res.expr = "iap_hook=" + (gIap.enabled ? "on" : "off");
      res.message = "内购钩子已" + (gIap.enabled ? "开启" : "关闭") + " (Pay=" + (gIap.installedPay ? 1 : 0) + ", iOS=" + (gIap.installedIOS ? 1 : 0) + ")";
      return res;
    }
    if (cmd.res === "vip_card") {
      var vr = grantVipCardDirect();
      vr.seq = cmd.seq;
      return vr;
    }
    if (!bind()) { res.ok = false; res.error = "engine not bound (PlayerData not ready)"; return res; }
    var t = table(), item = t[cmd.res];
    if (!item) { res.ok = false; res.error = "unknown resource: " + cmd.res; return res; }
    try {
      var before = safeNum(item.get());
      var val = safeNum(cmd.value);
      if (val === null) { res.ok = false; res.error = "bad value"; res.before = before; return res; }
      var target = (cmd.action === "add") ? (before + val) : val;
      target = safeNum(target);
      item.set(target);
      item.emit();
      var after = safeNum(item.get());
      res.ok = true;
      res.before = before;
      res.after = after;
      res.expr = (cmd.action === "add") ? (before + " + " + val + " = " + after) : (before + " -> " + after);
    } catch (e) {
      res.ok = false;
      res.error = str(e);
    }
    return res;
  }

  function probe() {
    var out = { version: VERSION, dir: DIR, ts: now(), sessionGen: gSessionGen, sessionKey: gSessionKey };
    out.typeofRequire = typeof window.__require;
    out.typeofJsb = typeof window.jsb;
    out.typeofCc = typeof window.cc;
    try {
      var g = req("Game");
      out.gameDefault = !!(g && g.default);
      if (g && g.default) { out.gameKeys = Object.keys(g.default); }
    } catch (e) { out.gameErr = str(e); }
    try {
      var m = req("Manager");
      out.managerDefault = !!(m && m.default);
      if (m && m.default) { out.managerKeys = Object.keys(m.default); }
    } catch (e) { out.managerErr = str(e); }
    try {
      var mgr = req("Manager").default;
      out.hasPlayerData = !!(mgr && mgr.PlayerData);
      out.hasMapData = !!(mgr && mgr.MapData);
      if (mgr && mgr.PlayerData) {
        out.gemNum = mgr.PlayerData.gemNum;
        out.powerNum = mgr.PlayerData.powerNum;
      }
    } catch (e) { out.playerDataErr = str(e); }
    out.bindWhy = gBindWhy;
    try { out.eventIdCount = Object.keys(req("AppConst").EVENT_ID).length; } catch (e) { out.eventIdErr = str(e); }
    try { out.coreEvent = !!(req("Core").default.Event); } catch (e) { out.coreErr = str(e); }
    try { out.playerInfoKeys = Object.keys(PD.playerInfo).length; } catch (e) { out.playerInfoErr = str(e); }
    try { out.hasPay = !!(req("Manager").default.Pay && req("Manager").default.Pay.pay); } catch (e) { out.payErr = str(e); }
    try { var ios = req("YiFaniOSIAPBridge"); out.hasYiFaniOS = !!(ios && ios.default && ios.default.buyProduct); } catch (e) { out.iosIapErr = str(e); }
    try { out.vip = vipSummary(); } catch (e) { out.vipErr = str(e); }
    try { out.iapCatalog = iapCatalog(); } catch (e) { out.iapCatalogErr = str(e); }
    out.state = snapshot();
    writeJson(DIR + "probe.json", out);
  }

  /* ---------------- main loop --------------------------------------------- */
  var ticks = 0;
  var probedAfterBind = false;

  function tick() {
    ticks++;
    try {
      if (bind()) {
        installIapHook();
        var st = snapshot();
        if (st) { writeJson(DIR + "state.json", st); }
        if (!probedAfterBind) {
          probedAfterBind = true;
          probe();
          log("probe refreshed after bind");
        }
        var cmd = gSessionReady ? readJson(DIR + "cmd.json") : null;
        if (cmd && typeof cmd.seq === "number" && cmd.seq !== lastSeq) {
          lastSeq = cmd.seq;
          var res = execute(cmd);
          writeJson(DIR + "res.json", res);
          log("cmd#" + cmd.seq + " " + cmd.res + " " + cmd.action + " " + cmd.value +
              " -> ok=" + res.ok + " before=" + res.before + " after=" + res.after +
              (res.error ? (" err=" + res.error) : ""));
        }
        var pc = readJson(DIR + "probe_cmd.json");
        if (pc && pc.seq && pc.seq !== window.__cookingModProbeSeq) {
          window.__cookingModProbeSeq = pc.seq;
          probe();
          log("probe written");
        }
      } else {
        writeJson(DIR + "state.json", { ready: false, ts: now(), version: VERSION, ticks: ticks, why: gBindWhy });
      }
    } catch (e) {
      log("tick error: " + str(e));
    }
    setTimeout(tick, 250);
  }

  window.__cookingMod = {
    version: VERSION,
    dir: DIR,
    snapshot: snapshot,
    probe: probe,
    execute: execute
  };
  log("injected v" + VERSION);
  probe();
  tick();
})();