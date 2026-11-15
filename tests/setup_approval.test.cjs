const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function fixture(session) {
  const button = {disabled: false};
  const message = {textContent: ''};
  const password = {value: 'disposable fixture password'};
  const form = {isConnected: true, dataset: {}, querySelector(selector) {
    return {'button': button, '#auth-error': message, '#password': password}[selector];
  }};
  const callbacks = [];
  let calls = 0;
  let boots = 0;
  const context = vm.createContext({
    URLSearchParams, location: {hash: ''}, history: {}, window: {addEventListener() {}},
    api: async () => {calls++; return typeof session === 'function' ? session() : session;},
    boot: async () => {boots++;},
    setTimeout: callback => {callbacks.push(callback); return callbacks.length;},
    clearTimeout() {},
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../stackarr/static/launcher.js'), 'utf8'), context);
  const controls = vm.runInContext('({checkSetupApproval, watchSetupApproval, setupApprovalExpired})', context);
  return {form, button, message, password, callbacks, controls,
    get calls() {return calls;}, get boots() {return boots;}};
}

test('expiry disables submission, explains recovery and retains the entered password', async () => {
  const f = fixture({setup_required: true, setup_approved: false});
  assert.equal(await f.controls.checkSetupApproval(f.form), false);
  assert.equal(f.button.disabled, true);
  assert.match(f.message.textContent, /Reopen Start Stackarr/);
  assert.match(f.message.textContent, /password has not been saved/);
  assert.equal(f.password.value, 'disposable fixture password');
});

test('a new host approval restores the same form without submitting it', async () => {
  const f = fixture({setup_required: true, setup_approved: true});
  f.message.textContent = f.controls.setupApprovalExpired;
  f.button.disabled = true;
  assert.equal(await f.controls.checkSetupApproval(f.form), true);
  assert.equal(f.button.disabled, false);
  assert.match(f.message.textContent, /approval renewed/);
  assert.equal(f.password.value, 'disposable fixture password');
  assert.equal(f.calls, 1);
});

test('background checks cannot reenable an in-flight submission or update a replaced form', async () => {
  const f = fixture({setup_required: true, setup_approved: true});
  f.message.textContent = f.controls.setupApprovalExpired;
  f.button.disabled = true;
  f.form.dataset.submitting = 'true';
  await f.controls.checkSetupApproval(f.form);
  assert.equal(f.button.disabled, true);
  f.form.isConnected = false;
  f.message.textContent = 'replacement';
  assert.equal(await f.controls.checkSetupApproval(f.form), false);
  assert.equal(f.message.textContent, 'replacement');
});

test('checks stop for removed forms and skip active submissions', async () => {
  const f = fixture({setup_required: true, setup_approved: false});
  f.controls.watchSetupApproval(f.form);
  f.form.dataset.submitting = 'true';
  await f.callbacks.shift()();
  assert.equal(f.calls, 0);
  assert.equal(f.callbacks.length, 1);
  f.form.dataset.submitting = 'false';
  await f.callbacks.shift()();
  assert.equal(f.button.disabled, true);
  f.form.isConnected = false;
  await f.callbacks.shift()();
  assert.equal(f.calls, 1);
  assert.equal(f.callbacks.length, 0);
});

test('an account created elsewhere leaves first-time setup', async () => {
  const f = fixture({setup_required: false, authenticated: false});
  assert.equal(await f.controls.checkSetupApproval(f.form), false);
  assert.equal(f.boots, 1);
});
