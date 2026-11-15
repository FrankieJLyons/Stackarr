'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function element(id, properties = {}) {
  return {id, isConnected: true, disabled: false, parentElement: null,
    focuses: 0, scrolls: 0, clicks: 0,
    matches: () => true,
    scrollIntoView() {this.scrolls++;},
    focus() {this.focuses++;},
    click() {this.clicks++;},
    ...properties};
}

function fixture(action = {id: 'verification'}) {
  const nodes = new Map();
  const messages = [];
  const calls = [];
  let renders = 0;
  let loads = 0;
  const state = {dirty: false};
  const draft = {revision: 4, draft: {step: 0, apps: ['plex']}};
  const context = vm.createContext({
    document: {getElementById: id => nodes.get(id), querySelectorAll: () => []},
    state, setupDraft: draft, setupDeployment: {journey: {next_action: action}},
    announce: message => messages.push(message),
    api: async (path, method, body) => {calls.push({path, method, body}); return {revision: 5, draft: body.draft};},
    loadSetup: async () => {loads++;},
    load: async () => {loads++;},
    render: () => {renders++;},
    renderPreservingContext: () => {renders++;},
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../stackarr/static/setup_journey.js'), 'utf8'), context);
  const controls = vm.runInContext('({runSetupAction, bindSetupJourney})', context);
  return {controls, nodes, messages, calls, state,
    get renders() {return renders;}, get loads() {return loads;}};
}

test('disabled and disconnected controls cannot be invoked again by the checklist', async () => {
  for (const properties of [{disabled: true}, {isConnected: false}]) {
    const f = fixture();
    let requests = 0;
    const target = element('check', {...properties, onclick: async () => {requests++;}});
    await f.controls.runSetupAction(target);
    assert.equal(requests, 0);
    assert.equal(target.clicks, 0);
    assert.equal(target.focuses, 0);
    assert.equal(target.scrolls, 0);
    assert.match(f.messages[0], /already running/);
  }
});

test('the checklist awaits the existing async action before it finishes', async () => {
  const f = fixture();
  let complete;
  let finished = false;
  const target = element('check');
  target.onclick = async function () {
    assert.equal(this, target);
    await new Promise(resolve => {complete = resolve;});
  };
  const running = f.controls.runSetupAction(target).then(() => {finished = true;});
  assert.equal(target.focuses, 1);
  assert.equal(target.clicks, 0);
  assert.equal(finished, false);
  complete();
  await running;
  assert.equal(finished, true);
});

test('an enabled control without an onclick handler uses its normal click action once', async () => {
  const f = fixture();
  const target = element('check');
  await f.controls.runSetupAction(target);
  assert.equal(target.clicks, 1);
  assert.equal(target.focuses, 1);
});

test('verification navigates to its saved setup step and focuses the instructions without claiming success', async () => {
  const f = fixture();
  const next = element('setup-journey-next');
  const verification = element('setup-verification');
  f.nodes.set(next.id, next);
  f.nodes.set(verification.id, verification);
  f.controls.bindSetupJourney();
  await next.onclick();
  assert.equal(f.calls.length, 1);
  assert.equal(f.calls[0].path, 'onboarding');
  assert.equal(f.calls[0].method, 'PUT');
  assert.equal(f.calls[0].body.draft.step, 2);
  assert.equal(f.loads, 1);
  assert.equal(f.renders, 1);
  assert.equal(verification.focuses, 1);
  assert.equal(next.disabled, false);
  assert.equal(f.messages.length, 0);
});

test('a dirty form blocks checklist navigation and sends focus to saving the current choices', async () => {
  const f = fixture();
  const next = element('setup-journey-next');
  const save = element('setup-next');
  f.nodes.set(next.id, next);
  f.nodes.set(save.id, save);
  f.state.dirty = true;
  f.controls.bindSetupJourney();
  await next.onclick();
  assert.equal(f.calls.length, 0);
  assert.equal(f.renders, 0);
  assert.equal(save.focuses, 1);
  assert.equal(next.disabled, false);
  assert.match(f.messages[0], /Save your current choices/);
});

test('movie and TV checklist searches select the right category and focus without issuing a probe', async () => {
  for (const media_type of ['movie', 'tv']) {
    const f = fixture({id: 'source-validation', media_type});
    const next = element('setup-journey-next');
    const query = element('indexer-validation-query');
    const type = element('indexer-validation-type', {value: 'movie'});
    for (const target of [next, query, type, element('indexer-setup')]) f.nodes.set(target.id, target);
    f.controls.bindSetupJourney();
    await next.onclick();
    assert.equal(type.value, media_type);
    assert.equal(query.focuses, 1);
    assert.equal(query.clicks, 0);
    assert.equal(f.calls.length, 0);
    assert.equal(next.disabled, false);
  }
});

test('choosing a source opens the provider choices once and focuses its selector', async () => {
  const f = fixture({id: 'source-setup'});
  const next = element('setup-journey-next');
  const provider = element('indexer-provider');
  let catalogLoads = 0;
  const catalog = element('indexer-load-providers', {onclick: async () => {catalogLoads++;}});
  for (const target of [next, provider, catalog, element('indexer-setup')]) f.nodes.set(target.id, target);
  f.controls.bindSetupJourney();
  await next.onclick();
  assert.equal(catalogLoads, 1);
  assert.equal(provider.focuses, 1);
  assert.equal(f.calls.length, 0);
});
