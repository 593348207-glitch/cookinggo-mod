#!/usr/bin/env node
'use strict';

/**
 * Local safety harness for src/CGMBootstrap.js.
 *
 * This runs the bootstrap inside node:vm with mocked Cocos/JSB objects. It does
 * not connect to a device, launch the app, install a package, or exercise any
 * purchase-success synthesis path. The assertions focus on mailbox reliability,
 * Manager binding diagnostics, command/result/state/probe files, de-duplication,
 * error containment, and the important default-off behavior for the IAP wrapper.
 */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const repoRoot = path.resolve(__dirname, '..');
const bootstrapPath = path.join(repoRoot, 'src', 'CGMBootstrap.js');
const source = fs.readFileSync(bootstrapPath, 'utf8');
const expectedVersion = (source.match(/var VERSION = \"([^\"]+)\";/) || [null, 'unknown'])[1];

function json(v) { return JSON.stringify(v); }
function parseMaybe(s) { return s ? JSON.parse(s) : null; }

function makeEventBus(events) {
  return { emit: (...args) => events.push(args) };
}

function makeManager(opts = {}) {
  const accountId = opts.accountId || null;
  const playerInfo = Object.prototype.hasOwnProperty.call(opts, 'playerInfo')
    ? opts.playerInfo
    : Object.assign({ maxMapId: 3, payTotal: opts.payTotal == null ? 0 : opts.payTotal }, accountId ? { uid: accountId } : {});
  if (playerInfo && playerInfo.payTotal == null) playerInfo.payTotal = opts.payTotal == null ? 0 : opts.payTotal;
  const gameData = { playerInfo, richesInfo: null, payInfo: [] };
  const saveCounters = { riches: 0, pay: 0 };
  const ServerData = {
    gameData,
    saveRichesInfo() { saveCounters.riches += 1; },
    savePayInfo() { saveCounters.pay += 1; }
  };
  const PlayerData = {
    playerInfo,
    gemNum: opts.gemNum == null ? 100 : opts.gemNum,
    powerNum: opts.powerNum == null ? 30 : opts.powerNum,
    adCouponNum: opts.adCouponNum == null ? 4 : opts.adCouponNum,
    clothingCionNum: opts.clothingCionNum == null ? 7 : opts.clothingCionNum,
    setPropNum(id, value) {
      if (id === 57) this.adCouponNum = value;
      if (id === 45) this.clothingCionNum = value;
    }
  };
  let originalPayCalls = 0;
  const Pay = {
    pay(purchaseTbl, cb) {
      originalPayCalls += 1;
      if (cb && typeof cb.OnPassthrough === 'function') cb.OnPassthrough(purchaseTbl);
      return { original: true, purchaseId: purchaseTbl && purchaseTbl.ID };
    }
  };
  const PayData = {
    get payInfo() { return gameData.payInfo; },
    addPayData(purchaseId, price, orderId) {
      gameData.payInfo.unshift({ purchaseId, price, orderId, time: 1700000000 });
      ServerData.savePayInfo(false);
    }
  };
  const VipCard = {
    isVipEffectTime: !!opts.vipActive,
    vipEndTimes: opts.vipEndTimes || 0,
    vipCardData: { type: 0, beginT: 0, endT: opts.vipEndTimes || 0, payData: [], hasGetDayNames: [] },
    getVipLeftTime: () => VipCard.isVipEffectTime ? 86400 : 0,
    setPlayerVipDataByGiftId(id) {
      if (opts.vipGrant === false) { throw new Error('vip grant disabled'); }
      VipCard.isVipEffectTime = true;
      VipCard.vipEndTimes = 4102444800;
      VipCard.vipCardData.endT = VipCard.vipEndTimes;
      VipCard.vipCardData.type = id;
    }
  };
  const Table = {
    giftTbl: [
      { ID: 28, GiftType: 28, PurchaseId: [], RewardIds: [4001, 4002, 4003] },
      { ID: 31, GiftType: 28, PurchaseId: [], RewardIds: [4004, 4005, 4006] },
      { ID: 32, GiftType: 28, PurchaseId: [], RewardIds: [4007, 4008, 4009] },
      { ID: 24, GiftType: 24, PurchaseId: [86, 87, 82], RewardIds: [3001, 3002, 3003] }
    ],
    purchaseTbl: [
      { ID: 1001, Price: 0.99, ProductID: 'mock.cookinggo.riches.099', ProductIDiOSOversea: 'mock.cookinggo.riches.099', RewardID: 0 },
      { ID: 1002, Price: 5.99, ProductID: 'mock.cookinggo.riches.599', ProductIDiOSOversea: 'mock.cookinggo.riches.599', RewardID: 0 },
      { ID: 1003, Price: 21.99, ProductID: 'mock.cookinggo.riches.2199', ProductIDiOSOversea: 'mock.cookinggo.riches.2199', RewardID: 0 },
      { ID: 86, Price: 6.00 }, { ID: 87, Price: 30.00 }, { ID: 82, Price: 68.00 }, { ID: 999, Price: 1.99 }
    ],
    rewardTbl: [],
    constById(id) { return id === 146 ? [[0.99, 6], [5.99, 38], [21.99, 128]] : null; }
  };
  const Activity = {};
  Object.defineProperty(Activity, 'richesInfo', {
    enumerable: true,
    get() {
      if (!gameData.richesInfo) gameData.richesInfo = {
        rewardGetIdx: [], beginTime: 0, beginTime2: 0, beginTime3: 0,
        accumulateNum: 0, dailyRedDot: false, firstRedDot: true
      };
      const total = Number(gameData.playerInfo && gameData.playerInfo.payTotal) || 0;
      const thresholds = [[0.99, 6], [5.99, 38], [21.99, 128]];
      if (total >= thresholds[0][0] && !gameData.richesInfo.beginTime) gameData.richesInfo.beginTime = 1700000000;
      if (total >= thresholds[1][0] && !gameData.richesInfo.beginTime2) gameData.richesInfo.beginTime2 = 1700000000;
      if (total >= thresholds[2][0] && !gameData.richesInfo.beginTime3) gameData.richesInfo.beginTime3 = 1700000000;
      return gameData.richesInfo;
    }
  });
  const Manager = {
    PlayerData,
    MapData: { mapCoinNum: opts.mapCoinNum == null ? 200 : opts.mapCoinNum },
    Pay,
    PayData,
    VipCard,
    Activity,
    App: { IsInland: false },
    Http: { serverTime: 1700000000 },
    Table,
    ServerData,
    Reward: {}
  };
  if (accountId) { Manager.Auth = { userInfo: { userId: accountId } }; }
  return {
    Manager, PlayerData, Pay, PayData, ServerData, Table,
    getOriginalPayCalls: () => originalPayCalls,
    getSaveCounts: () => ({ ...saveCounters })
  };
}

function makeFileUtils(files, writeCounts, opts = {}) {
  const writable = opts.writable || '/mock/Documents/';
  const failWritePrefix = opts.failWritePrefix || null;
  return {
    getWritablePath: () => writable,
    createDirectory: () => {
      if (opts.throwCreate) throw new Error('createDirectory boom');
      return true;
    },
    getStringFromFile: (p) => {
      if (opts.throwRead) throw new Error('getStringFromFile boom');
      return files.has(p) ? files.get(p) : '';
    },
    writeStringToFile: (s, p) => {
      if (opts.throwWrite) throw new Error('writeStringToFile boom');
      if (failWritePrefix && p.startsWith(failWritePrefix)) return false;
      files.set(p, String(s));
      writeCounts.set(p, (writeCounts.get(p) || 0) + 1);
      return true;
    },
    removeFile: (p) => { files.delete(p); return true; }
  };
}

function runBootstrap(opts = {}) {
  const files = opts.files || new Map();
  const writeCounts = opts.writeCounts || new Map();
  const timers = [];
  const logs = [];
  const events = [];
  const managerOpts = { events };
  if (Object.prototype.hasOwnProperty.call(opts, 'playerInfo')) managerOpts.playerInfo = opts.playerInfo;
  const managerBundle = opts.managerBundle || makeManager(managerOpts);
  const modules = opts.modules || {
    Manager: opts.managerMissing ? null : { default: managerBundle.Manager },
    AppConst: opts.appConstMissing ? null : { EVENT_ID: {
      UPDATE_GEM: 'UPDATE_GEM',
      UPDATE_COIN: 'UPDATE_COIN',
      UPDATE_POWER: 'UPDATE_POWER',
      UPDATE_AD_COUPON: 'UPDATE_AD_COUPON',
      UPDATE_PROP_NUM: 'UPDATE_PROP_NUM',
      UPDATE_GIFT_MENU_NUM: 'UPDATE_GIFT_MENU_NUM',
      UPDATE_MAXMAP_COIN: 'UPDATE_MAXMAP_COIN',
      UPDATE_CLOTHINGCOIN: 'UPDATE_CLOTHINGCOIN'
    }},
    Core: opts.coreMissing ? null : { default: { Event: makeEventBus(events) } },
    YiFaniOSIAPBridge: { default: { buyProduct() { return { originalIOS: true }; } } },
    Game: { default: { '$super': true } }
  };
  const context = {
    window: {
      jsb: opts.noFileUtils ? {} : { fileUtils: makeFileUtils(files, writeCounts, opts.fileUtilsOpts || {}) },
      cc: {},
      __require(name) { return modules[name] || null; }
    },
    console: { log: (...args) => logs.push(args.join(' ')) },
    Promise,
    setTimeout(fn) { timers.push(fn); return timers.length; }
  };
  vm.runInNewContext(source, context, { filename: bootstrapPath });
  function runTimer(count = 1) {
    for (let i = 0; i < count; i++) {
      const fn = timers.shift();
      assert.equal(typeof fn, 'function', 'expected a queued timer');
      fn();
    }
  }
  const dir = '/mock/Documents/cookingmod/';
  const handle = { context, files, writeCounts, timers, logs, events, modules, managerBundle, dir, runTimer };
  handle.swapManager = (bundle) => {
    handle.modules.Manager.default = bundle.Manager;
    handle.activeManagerBundle = bundle;
    return bundle.Manager;
  };
  handle.activeManagerBundle = managerBundle;
  return handle;
}

function readJsonFile(h, name) { return parseMaybe(h.files.get(h.dir + name)); }
function putJsonFile(h, name, obj) { h.files.set(h.dir + name, json(obj)); }
function issuePurchase(h, seq, amount, orderId, extra = {}) {
  putJsonFile(h, 'cmd.json', Object.assign({
    seq, res: 'purchase_sim', action: 'success', value: amount, localOnly: true, orderId, sessionGen: 1
  }, extra));
  h.runTimer(1);
  return readJsonFile(h, 'res.json');
}

const tests = [];
function test(name, fn) { tests.push({ name, fn }); }

test('defers and recovers when jsb.fileUtils is initially unavailable', () => {
  const h = runBootstrap({ noFileUtils: true });
  assert.equal(h.context.window.__cookingMod, undefined);
  assert.ok(h.logs.some((line) => line.includes('bootstrap deferred: jsb.fileUtils unavailable')));
  assert.equal(h.timers.length, 1);
  h.context.window.jsb.fileUtils = makeFileUtils(h.files, h.writeCounts);
  h.runTimer(1);
  assert.equal(h.context.window.__cookingMod.dir, h.dir);
  assert.equal(readJsonFile(h, 'state.json').ready, true);
});

test('discovers first mailbox, writes hello/probe/state, and keeps IAP disabled by default', () => {
  const files = new Map([['/mock/Documents/cookingmod/mod.json', '{}']]);
  const h = runBootstrap({ files });
  const hello = readJsonFile(h, 'js_hello.json');
  const state = readJsonFile(h, 'state.json');
  const probe = readJsonFile(h, 'probe.json');
  assert.equal(hello.version, expectedVersion);
  assert.equal(h.context.window.__cookingMod.dir, h.dir);
  assert.equal(state.ready, true);
  assert.equal(state.iapHook, 0);
  assert.equal(probe.managerDefault, true);
  assert.equal(probe.hasPay, true);
  assert.equal(probe.state.ready, true);
  assert.equal(probe.bindWhy, 'ok');
});

test('falls back to ../cookingmod when first candidate cannot be written', () => {
  const h = runBootstrap({ fileUtilsOpts: { failWritePrefix: '/mock/Documents/cookingmod/' } });
  assert.equal(h.context.window.__cookingMod.dir, '/mock/Documents/../cookingmod/');
  assert.ok(h.files.has('/mock/Documents/../cookingmod/js_hello.json'));
});

test('reports Manager missing through state.json without crashing', () => {
  const h = runBootstrap({ managerMissing: true });
  const state = readJsonFile(h, 'state.json');
  assert.equal(state.ready, false);
  assert.equal(state.why, 'module Manager missing');
});

test('reports PlayerData.playerInfo not loaded yet and retries on timer', () => {
  const h = runBootstrap({ playerInfo: null });
  let state = readJsonFile(h, 'state.json');
  assert.equal(state.ready, false);
  assert.equal(state.why, 'PlayerData.playerInfo not loaded yet');
  h.managerBundle.PlayerData.playerInfo = { maxMapId: 3 };
  h.runTimer(1);
  state = readJsonFile(h, 'state.json');
  assert.equal(state.ready, true);
});

test('unknown command writes res.json but does not mutate resource state', () => {
  const h = runBootstrap({ files: new Map([['/mock/Documents/cookingmod/mod.json', '{}']]) });
  putJsonFile(h, 'cmd.json', { seq: 10, res: 'unknown', action: 'set', value: 1 });
  h.runTimer(1);
  const res = readJsonFile(h, 'res.json');
  const state = readJsonFile(h, 'state.json');
  assert.equal(res.ok, false);
  assert.match(res.error, /^unknown resource:/);
  assert.equal(state.gem, 100);
  assert.equal(state.coin, 200);
});

test('bad numeric input is rejected and keeps previous value', () => {
  const h = runBootstrap({ files: new Map([['/mock/Documents/cookingmod/mod.json', '{}']]) });
  putJsonFile(h, 'cmd.json', { seq: 11, res: 'gem', action: 'set', value: 'abc' });
  h.runTimer(1);
  const res = readJsonFile(h, 'res.json');
  assert.equal(res.ok, false);
  assert.equal(res.error, 'bad value');
  assert.equal(h.managerBundle.PlayerData.gemNum, 100);
});

test('cmd seq is de-duplicated across ticks', () => {
  const h = runBootstrap({ files: new Map([['/mock/Documents/cookingmod/mod.json', '{}']]) });
  putJsonFile(h, 'cmd.json', { seq: 12, res: 'unknown', action: 'set', value: 1 });
  h.runTimer(1);
  const firstCount = h.writeCounts.get(h.dir + 'res.json') || 0;
  h.runTimer(1);
  const secondCount = h.writeCounts.get(h.dir + 'res.json') || 0;
  assert.equal(secondCount, firstCount);
});

test('probe command writes probe and de-duplicates by seq', () => {
  const h = runBootstrap({ files: new Map([['/mock/Documents/cookingmod/mod.json', '{}']]) });
  const before = h.writeCounts.get(h.dir + 'probe.json') || 0;
  putJsonFile(h, 'probe_cmd.json', { seq: 1 });
  h.runTimer(1);
  const after = h.writeCounts.get(h.dir + 'probe.json') || 0;
  assert.equal(after, before + 1);
  h.runTimer(1);
  assert.equal(h.writeCounts.get(h.dir + 'probe.json') || 0, after);
});

test('default-off Pay wrapper passes purchase calls to original implementation', () => {
  const h = runBootstrap({ files: new Map([['/mock/Documents/cookingmod/mod.json', '{}']]) });
  const ret = h.managerBundle.Manager.Pay.pay({ ID: 87 }, {
    OnSuccess() { throw new Error('OnSuccess should not be synthesized while disabled'); }
  });
  assert.deepEqual(ret, { original: true, purchaseId: 87 });
  assert.equal(h.managerBundle.getOriginalPayCalls(), 1);
  const state = readJsonFile(h, 'state.json');
  assert.equal(state.iapHook, 0);
});


test('runtime catalog exposes purchase rows and Riches gift rows without guessing IDs', () => {
  const h = runBootstrap({ files: new Map([['/mock/Documents/cookingmod/mod.json', '{}']]) });
  putJsonFile(h, 'cmd.json', { seq: 20, res: 'iap_catalog', action: 'read', sessionGen: 1 });
  h.runTimer(1);
  const res = readJsonFile(h, 'res.json');
  assert.equal(res.ok, true);
  assert.equal(res.catalog.source, 'Manager.Table runtime catalog');
  assert.equal(res.catalog.richesGiftType, 28);
  assert.equal(res.catalog.richesGifts.length, 3);
  assert.ok(res.catalog.purchases.some((p) => p.id === 1001 && p.price === 0.99));
  assert.ok(res.catalog.purchases.some((p) => p.productId === 'mock.cookinggo.riches.099'));
});

test('purchase_sim is local-only and requires an explicit localOnly marker', () => {
  const h = runBootstrap({ files: new Map([['/mock/Documents/cookingmod/mod.json', '{}']]) });
  putJsonFile(h, 'cmd.json', { seq: 21, res: 'purchase_sim', action: 'success', value: 0.99, sessionGen: 1 });
  h.runTimer(1);
  const res = readJsonFile(h, 'res.json');
  assert.equal(res.ok, false);
  assert.equal(res.error, 'purchase_sim requires localOnly=true');
  assert.equal(h.managerBundle.PlayerData.playerInfo.payTotal, 0);
});

test('0.98 does not unlock Riches track 0, while 0.99 does', () => {
  const h = runBootstrap({ files: new Map([['/mock/Documents/cookingmod/mod.json', '{}']]) });
  let res = issuePurchase(h, 22, 0.98, 'order-098');
  assert.equal(res.ok, true);
  assert.equal(res.richesTrack0Unlocked, false);
  assert.equal(res.payTotalAfter, 0.98);
  res = issuePurchase(h, 23, 0.01, 'order-001');
  assert.equal(res.ok, true);
  assert.equal(res.richesTrack0Unlocked, true);
  assert.equal(res.payTotalAfter, 0.99);
  assert.equal(res.riches.beginTime > 0, true);
  assert.equal(h.managerBundle.getSaveCounts().riches, 2);
});

test('purchase_sim accepts a runtime catalog row and records the 0.99 package price', () => {
  const h = runBootstrap({ files: new Map([['/mock/Documents/cookingmod/mod.json', '{}']]) });
  const res = issuePurchase(h, 24, 0, 'order-catalog-099', { value: 0.99, purchaseId: 1001, requireCatalog: true });
  assert.equal(res.ok, true);
  assert.equal(res.purchaseId, 1001);
  assert.equal(res.catalogPrice, 0.99);
  assert.equal(res.recorded, true);
  assert.equal(h.managerBundle.PayData.payInfo.length, 1);
  assert.equal(h.managerBundle.getSaveCounts().pay, 1);
});

test('split purchases accumulate to unlock track 0 and duplicate order replay is ignored', () => {
  const h = runBootstrap({ files: new Map([['/mock/Documents/cookingmod/mod.json', '{}']]) });
  let res = issuePurchase(h, 25, 0.50, 'order-half-a');
  assert.equal(res.richesTrack0Unlocked, false);
  res = issuePurchase(h, 26, 0.49, 'order-half-b');
  assert.equal(res.richesTrack0Unlocked, true);
  assert.equal(res.payTotalAfter, 0.99);
  const duplicate = issuePurchase(h, 27, 0.49, 'order-half-b');
  assert.equal(duplicate.ok, true);
  assert.equal(duplicate.duplicate, true);
  assert.equal(duplicate.payTotalAfter, 0.99);
  assert.equal(h.managerBundle.PayData.payInfo.length, 2);
});

test('5.99 and 21.99 cumulative totals unlock the expected Riches tracks', () => {
  const h = runBootstrap({ files: new Map([['/mock/Documents/cookingmod/mod.json', '{}']]) });
  let res = issuePurchase(h, 28, 5.99, 'order-599');
  assert.deepEqual([res.riches.track0Unlocked, res.riches.track1Unlocked, res.riches.track2Unlocked], [true, true, false]);
  res = issuePurchase(h, 29, 16.00, 'order-1600');
  assert.equal(res.payTotalAfter, 21.99);
  assert.deepEqual([res.riches.track0Unlocked, res.riches.track1Unlocked, res.riches.track2Unlocked], [true, true, true]);
});

test('targetPayTotal raises the active account to exactly 100 USD and exposes the final Riches bonus eligibility', () => {
  const h = runBootstrap({ files: new Map([['/mock/Documents/cookingmod/mod.json', '{}']]) });
  let res = issuePurchase(h, 32, 0, 'target-100', { targetPayTotal: 100.00 });
  assert.equal(res.ok, true);
  assert.equal(res.payTotalBefore, 0);
  assert.equal(res.amount, 100);
  assert.equal(res.payTotalAfter, 100);
  assert.deepEqual([res.riches.track0Unlocked, res.riches.track1Unlocked, res.riches.track2Unlocked], [true, true, true]);
  assert.equal(res.riches.extraBonus.eligible, true);
  assert.equal(res.riches.extraBonus.granted, false);
  assert.equal(res.riches.extraBonus.trigger, 'claim Riches track 2 day 2');
  assert.equal(res.riches.extraBonus.bonusPurchaseId, 86);
  assert.equal(res.riches.extraBonus.bonusRewardId, 3001);

  res = issuePurchase(h, 33, 0, 'target-100-again', { targetPayTotal: 100.00 });
  assert.equal(res.ok, true);
  assert.equal(res.alreadyAtTarget, true);
  assert.equal(res.amount, 0);
  assert.equal(res.payTotalAfter, 100);
  assert.equal(h.managerBundle.PayData.payInfo.length, 1);
});

test('Riches persistence is called after a simulated purchase and account sessions stay isolated', () => {
  const a = makeManager({ accountId: 'A' });
  const b = makeManager({ accountId: 'B' });
  const h = runBootstrap({ managerBundle: a, files: new Map([['/mock/Documents/cookingmod/mod.json', '{}']]) });
  const first = issuePurchase(h, 30, 0.99, 'a-order');
  assert.equal(first.richesTrack0Unlocked, true);
  assert.equal(a.getSaveCounts().riches, 1);
  h.swapManager(b);
  h.runTimer(1);
  let state = readJsonFile(h, 'state.json');
  assert.equal(state.sessionGen, 2);
  assert.equal(state.payTotal, 0);
  assert.equal(state.riches.track0Unlocked, false);
  h.swapManager(a);
  h.runTimer(1);
  state = readJsonFile(h, 'state.json');
  assert.equal(state.sessionGen, 3);
  assert.equal(state.payTotal, 0.99);
  assert.equal(state.riches.track0Unlocked, true);
});

test('account rebind publishes a not-ready handshake before the new session becomes command-ready', () => {
  const a = makeManager({ accountId: 'A' });
  const b = makeManager({ accountId: 'B' });
  const h = runBootstrap({ managerBundle: a, files: new Map([['/mock/Documents/cookingmod/mod.json', '{}']]) });
  h.swapManager(b);
  h.runTimer(1);
  let hello = readJsonFile(h, 'js_hello.json');
  let state = readJsonFile(h, 'state.json');
  assert.equal(hello.sessionGen, 2);
  assert.equal(hello.ready, false);
  assert.equal(hello.rebind, true);
  assert.equal(state.sessionGen, 2);
  assert.equal(state.ready, false);
  assert.equal(state.rebind, true);

  h.runTimer(1);
  hello = readJsonFile(h, 'js_hello.json');
  state = readJsonFile(h, 'state.json');
  assert.equal(hello.ready, true);
  assert.equal(hello.rebind, false);
  assert.equal(state.ready, true);
  assert.equal(state.rebind, false);
});

test('stale purchase_sim session commands are rejected before mutation', () => {
  const a = makeManager({ accountId: 'A' });
  const b = makeManager({ accountId: 'B' });
  const h = runBootstrap({ managerBundle: a, files: new Map([['/mock/Documents/cookingmod/mod.json', '{}']]) });
  h.swapManager(b);
  h.runTimer(1);
  putJsonFile(h, 'cmd.json', { seq: 31, res: 'purchase_sim', action: 'success', value: 0.99, orderId: 'stale', localOnly: true, sessionGen: 1 });
  h.runTimer(1);
  const res = readJsonFile(h, 'res.json');
  assert.equal(res.ok, false);
  assert.match(res.error, /stale command sessionGen=1 current=2/);
  assert.equal(b.PlayerData.playerInfo.payTotal, 0);
});

test('rebinds Manager/Pay/VipCard and preserves account-local resources across A to B to A', () => {
  const a = makeManager({ accountId: 'A', gemNum: 100, mapCoinNum: 200, vipGrant: true });
  const b = makeManager({ accountId: 'B', gemNum: 900, mapCoinNum: 800, vipGrant: true });
  const h = runBootstrap({
    managerBundle: a,
    files: new Map([['/mock/Documents/cookingmod/mod.json', '{}']])
  });
  let state = readJsonFile(h, 'state.json');
  assert.equal(state.sessionGen, 1);
  assert.equal(state.gem, 100);
  putJsonFile(h, 'cmd.json', { seq: 1, res: 'gem', action: 'add', value: 25, sessionGen: 1 });
  h.runTimer(1);
  assert.equal(a.PlayerData.gemNum, 125);
  assert.equal(readJsonFile(h, 'res.json').ok, true);

  h.swapManager(b);
  h.runTimer(1);
  state = readJsonFile(h, 'state.json');
  assert.equal(state.sessionGen, 2);
  assert.equal(state.gem, 900);
  assert.equal(state.coin, 800);
  assert.equal(a.Manager.Pay.__cookingModIapHook, undefined);
  assert.equal(typeof b.Manager.Pay.pay, 'function');

  putJsonFile(h, 'cmd.json', { seq: 1, res: 'coin', action: 'set', value: 777, sessionGen: 2 });
  h.runTimer(1);
  assert.equal(b.Manager.MapData.mapCoinNum, 777);

  h.swapManager(a);
  h.runTimer(1);
  state = readJsonFile(h, 'state.json');
  assert.equal(state.sessionGen, 3);
  assert.equal(state.gem, 125);
  assert.equal(state.coin, 200);
  assert.equal(a.PlayerData.gemNum, 125);
  assert.equal(b.Manager.MapData.mapCoinNum, 777);
});

test('rebinds direct month-card test to the active account and rejects stale session commands', () => {
  const a = makeManager({ accountId: 'A', vipGrant: true });
  const b = makeManager({ accountId: 'B', vipGrant: true });
  const h = runBootstrap({ managerBundle: a, files: new Map([['/mock/Documents/cookingmod/mod.json', '{}']]) });
  putJsonFile(h, 'cmd.json', { seq: 9, res: 'vip_card', action: 'buy', value: 30, sessionGen: 1 });
  h.runTimer(1);
  assert.equal(readJsonFile(h, 'res.json').ok, true);
  assert.equal(a.Manager.VipCard.isVipEffectTime, true);

  h.swapManager(b);
  h.runTimer(1);
  putJsonFile(h, 'cmd.json', { seq: 9, res: 'vip_card', action: 'buy', value: 30, sessionGen: 1 });
  h.runTimer(1);
  let res = readJsonFile(h, 'res.json');
  assert.equal(res.ok, false);
  assert.match(res.error, /stale command sessionGen=1 current=2/);
  assert.equal(b.Manager.VipCard.isVipEffectTime, false);

  putJsonFile(h, 'cmd.json', { seq: 10, res: 'vip_card', action: 'buy', value: 30, sessionGen: 2 });
  h.runTimer(1);
  res = readJsonFile(h, 'res.json');
  assert.equal(res.ok, true);
  assert.equal(b.Manager.VipCard.isVipEffectTime, true);
});

test('file read/write exceptions do not escape bootstrap evaluation', () => {
  const h = runBootstrap({ fileUtilsOpts: { throwRead: true, throwWrite: true } });
  assert.equal(h.context.window.__cookingMod, undefined);
  assert.ok(h.logs.some((line) => line.includes('mailbox not found')));
});

let failed = 0;
for (const t of tests) {
  try {
    t.fn();
    console.log(`PASS ${t.name}`);
  } catch (err) {
    failed += 1;
    console.error(`FAIL ${t.name}`);
    console.error(err && err.stack || err);
  }
}
console.log(`${tests.length - failed}/${tests.length} tests passed`);
if (failed) process.exit(1);
