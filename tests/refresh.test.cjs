'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function fixture(refreshSeconds = 60) {
  const callbacks = [];
  const cleared = [];
  const root = {querySelector: () => ({})};
  const context = vm.createContext({
    document: {querySelector: () => root, addEventListener() {}},
    window: {addEventListener() {}},
    setTimeout: (callback, delay) => {callbacks.push({callback, delay}); return callbacks.length;},
    clearTimeout: id => cleared.push(id),
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../stackarr/static/preferences.js'), 'utf8'), context);
  const source = fs.readFileSync(path.join(__dirname, '../stackarr/static/app.js'), 'utf8');
  vm.runInContext(source.replace(/\r?\nboot\(\);\s*$/, ''), context);
  vm.runInContext('refreshStatusRegions = () => {};', context);
  const controls = vm.runInContext('({state, poll, schedule, stopSchedule, renderPreservingContext})', context);
  controls.state.config = {dashboard: {refresh_seconds: refreshSeconds}};
  controls.state.storageChecked=Date.now();
  return {controls, callbacks, cleared,
    setApi(api) {context.fixtureApi = api; vm.runInContext('api = fixtureApi;', context);},
    setRender(render) {context.fixtureRender = render; vm.runInContext('render = fixtureRender; captureContext = () => {throw new Error("Dirty forms must stay mounted");};', context);},
  };
}

test('automatic refresh honors the configured interval instead of capping it at ten seconds', () => {
  for (const seconds of [10, 30, 60, 3600]) {
    const f = fixture(seconds);
    f.controls.schedule();
    assert.equal(f.callbacks[0].delay, seconds * 1000);
  }
});

test('rescheduling applies a changed interval and cancels the previous timer', () => {
  const f = fixture(3600);
  f.controls.schedule();
  f.controls.state.config.dashboard.refresh_seconds = 30;
  f.controls.schedule();
  assert.equal(f.callbacks.at(-1).delay, 30000);
  assert.ok(f.cleared.includes(1));
});

test('stopping refresh while a request is in flight cannot restart the timer', async () => {
  const f = fixture();
  let resolve;
  f.setApi(() => new Promise(done => {resolve = done;}));
  f.controls.schedule();
  const completion = f.callbacks[0].callback();
  f.controls.stopSchedule();
  resolve({integrations: []});
  await completion;
  assert.equal(f.callbacks.length, 1);
});

test('manual and scheduled refreshes share one request and retain an unrelated action error', async () => {
  const f = fixture();
  let resolve;
  let calls = 0;
  f.setApi(() => {calls++; return new Promise(done => {resolve = done;});});
  f.controls.state.error = 'Review the failed backup.';
  const first = f.controls.poll();
  const second = f.controls.poll();
  assert.equal(calls, 1);
  resolve({integrations: []});
  await Promise.all([first, second]);
  assert.equal(f.controls.state.error, 'Review the failed backup.');
  assert.equal(f.controls.state.refreshError, '');
});

test('a failed refresh keeps the last collected status and recovers independently of action errors', async () => {
  const f = fixture();
  const last = {integrations: [{id: 'plex'}]};
  f.controls.state.status = last;
  f.controls.state.error = 'Review the failed backup.';
  f.setApi(async () => {throw new Error('Offline');});
  await f.controls.poll();
  assert.equal(f.controls.state.status, last);
  assert.match(f.controls.state.refreshError, /Displayed data may be stale.*Offline/);
  assert.equal(f.controls.state.error, 'Review the failed backup.');
  f.setApi(async () => last);
  await f.controls.poll();
  assert.equal(f.controls.state.refreshError, '');
  assert.equal(f.controls.state.error, 'Review the failed backup.');
});

test('a context refresh leaves a dirty form and its newly entered private key mounted', () => {
  const f = fixture();
  const privateField = {value: 'synthetic newly entered key'};
  const mode = {value: 'connect'};
  const address = {hidden: false};
  let renders = 0;
  f.setRender(() => {renders++; privateField.value = ''; mode.value = 'install'; address.hidden = true;});
  f.controls.state.dirty = true;
  f.controls.state.appDirty = true;
  f.controls.renderPreservingContext();
  assert.equal(renders, 0);
  assert.equal(privateField.value, 'synthetic newly entered key');
  assert.equal(mode.value, 'connect');
  assert.equal(address.hidden, false);
  assert.equal(f.controls.state.dirty, true);
  assert.equal(f.controls.state.appDirty, true);
});

test('edits made while a refresh awaits a response prevent its eventual form render', async () => {
  const f = fixture();
  let finishRequest;
  const response = new Promise(resolve => {finishRequest = resolve;});
  const privateField = {value: ''};
  let renders = 0;
  f.setRender(() => {renders++; privateField.value = '';});
  const refresh = (async () => {await response; f.controls.renderPreservingContext();})();
  privateField.value = 'synthetic key typed during request';
  f.controls.state.dirty = true;
  f.controls.state.indexerDirty = true;
  finishRequest();
  await refresh;
  assert.equal(renders, 0);
  assert.equal(privateField.value, 'synthetic key typed during request');
  assert.equal(f.controls.state.indexerDirty, true);
});
