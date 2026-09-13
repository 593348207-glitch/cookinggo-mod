/* =========================================================================
 * CookingGo Mod - JS bootstrap payload
 * Target : Cooking GO 1.25.03 (Cocos Creator 2.4.11 + cocos2d-x lite + V8)
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
;(function () {
  var VERSION = "1.1.4";
  var TAG = "[CookingMod]";

  function log(s) {
    try { console.log(TAG + " " + s); } catch (e) {}
  }
  function str(e) {
    try { return String(e && e.message ? e.message : e); } catch (x) { return "unknown-error"; }
  }

  try {
    if (window.__cookingMod && window.__cookingMod.version) {
      log("bootstrap skipped, already v" + window.__cookingMod.version);
      return;
    }
  } catch (e) {}

  var fs = null;
  try { fs = (window.jsb && window.jsb.fileUtils) ? window.jsb.fileUtils : null; } catch (e) { fs = null; }
  if (!fs) { log("jsb.fileUtils unavailable -> abort"); return; }

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
    return;
  }
  log("mailbox=" + DIR + " writable=" + writable);

  function now() { return (new Date()).getTime(); }
  writeJson(DIR + "js_hello.json", { version: VERSION, dir: DIR, writable: writable, ts: now() });

  /* ---------------- engine binding ----------------------------------------- */
  var G = null, APP = null, CORE = null, PD = null, MD = null;

  function req(name) {
    try { return window.__require(name); } catch (e) { return null; }
  }

  /* Evidence (static analysis + on-device probe, 2026-09-12):
     __require("Game")    -> cc.Component scene controller, NOT the data holder
     __require("Manager") -> the manager singleton whose static props are
                             assigned in _loadAllManagers(): PlayerData,
                             MapData, ServerData, Auth, Pay, ...            */
  var gBindWhy = "not attempted";

  function bind() {
    if (G && PD && MD && APP && CORE) { return true; }
    var m = req("Manager");
    if (!m || !m.default) { gBindWhy = "module Manager missing"; return false; }
    var app = req("AppConst");
    if (!app || !app.EVENT_ID) { gBindWhy = "AppConst.EVENT_ID missing"; return false; }
    var core = req("Core");
    if (!core || !core.default) { gBindWhy = "module Core missing"; return false; }
    var mgr = m.default;
    var pd = mgr.PlayerData, md = mgr.MapData;
    if (!pd) { gBindWhy = "Manager.PlayerData missing"; return false; }
    if (!md) { gBindWhy = "Manager.MapData missing"; return false; }
    try {
      if (!pd.playerInfo) { gBindWhy = "PlayerData.playerInfo not loaded yet"; return false; }
    } catch (e) {
      gBindWhy = "PlayerData.playerInfo threw: " + str(e);
      return false;
    }
    G = mgr; APP = app; CORE = core.default; PD = pd; MD = md;
    gBindWhy = "ok";
    log("bound: Manager.PlayerData + EVENT_ID + Core.Event ready");
    return true;
  }

  /* ServerConst.EPropID (verified in scriptBundle/index.js):
       45 = ClothNum  -> PlayerData.clothingCionNum  (换装币)
       57 = AdCoupon  -> PlayerData.adCouponNum      (免广告券)            */
  var EPropID_ClothNum = 45;
  var EPropID_AdCoupon = 57;

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
    if (!bind()) { return null; }
    var t = table(), out = { ready: true, ts: now(), version: VERSION, why: gBindWhy };
    for (var k in t) {
      try { out[k] = Number(t[k].get()); } catch (e) { out[k] = null; out[k + "_err"] = str(e); }
    }
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
    var res = { seq: cmd.seq, res: cmd.res, action: cmd.action, input: cmd.value, ts: now(), version: VERSION };
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
    var out = { version: VERSION, dir: DIR, ts: now() };
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
    out.state = snapshot();
    writeJson(DIR + "probe.json", out);
  }

  /* ---------------- main loop --------------------------------------------- */
  var lastSeq = -1;
  var ticks = 0;

  function tick() {
    ticks++;
    try {
      if (bind()) {
        var st = snapshot();
        if (st) { writeJson(DIR + "state.json", st); }
        var cmd = readJson(DIR + "cmd.json");
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