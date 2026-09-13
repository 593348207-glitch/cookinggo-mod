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
  const playerInfo = Object.prototype.hasOwnProperty.call(opts, 'playerInfo')
    ? opts.playerInfo
    : { maxMapId: 3 };
  const PlayerData = {
    playerInfo,
    gemNum: 100,
    powerNum: 30,
    adCouponNum: 4,
    clothingCionNum: 7,
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
  const Manager = {
    PlayerData,
    MapData: { mapCoinNum: 200 },
    Pay,
    VipCard: {
      isVipEffectTime: false,
      vipCardData: { type: 0, beginT: 0, endT: 0, payData: [], hasGetDayNames: [] },
      getVipLeftTime: () => 0,
      setPlayerVipDataByGiftId() {
        throw new Error('direct grant path is intentionally not exercised by this harness');
      }
    },
    Table: {
      giftTbl: [{ GiftType: 24, PurchaseId: [86, 87, 82], RewardIds: [3001, 3002, 3003] }],
      purchaseTbl: [{ ID: 86 }, { ID: 87 }, { ID: 82 }, { ID: 999 }],
      rewardTbl: []
    },
    ServerData: {},
    Reward: {}
  };
  return { Manager, PlayerData, Pay, getOriginalPayCalls: () => originalPayCalls };
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
    }
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
  return { context, files, writeCounts, timers, logs, events, modules, managerBundle, dir, runTimer };
}

function readJsonFile(h, name) { return parseMaybe(h.files.get(h.dir + name)); }
function putJsonFile(h, name, obj) { h.files.set(h.dir + name, json(obj)); }

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
