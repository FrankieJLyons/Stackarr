'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const provider = {id: 'example-account', name: 'Example <Provider>', supported: true, privacy: 'private', fields: [
  {name: 'apiKey', label: 'Provider key', type: 'password', private: true, required: true, help: 'From your provider account'},
  {name: 'tier', label: 'Tier', type: 'select', required: true, options: [{value: 'basic', label: 'Basic'}]},
  {name: 'timeout', label: 'Timeout', type: 'number'},
  {name: 'special', label: 'Option', type: 'checkbox'},
]};

function fixture() {
  const nodes = new Map();
  const calls = [], messages = [];
  let renders = 0;
  const state = {view: 'setup', dirty: false, appDirty: false, indexerDirty: false,
    credentials: ['prowlarr'], config: {integrations: {
      prowlarr: {enabled: true, url: 'http://prowlarr.invalid'},
      plex: {enabled: true, url: 'http://plex.invalid'},
      radarr: {enabled: true}, sonarr: {enabled: true},
    }}};
  const selected = new Set(['prowlarr', 'plex', 'radarr', 'sonarr']);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
  const context = vm.createContext({state, setupDeployment: {operations: [], web_login_apps: []},
    setupAppSelected: key => selected.has(key), escape,
    field: (label, id, value, type = 'text', extra = '') => `<label for="${id}">${label}</label><input id="${id}" value="${escape(value)}" type="${type}" ${extra}>`,
    document: {getElementById: id => nodes.get(id), querySelectorAll: query => query.includes('#indexer-provider-details') ? [...nodes.values()].filter(node => node.formField) : []},
    announce: message => messages.push(message),
    api: async (url, method, body) => {
      calls.push({url, method, body});
      if (url === 'deployments') return {journey: {checkpoints: []}};
      if (url === 'indexers/providers/review' || url === 'indexers/review') return {name: body.name, notice: 'Synthetic review', review_token: 'review-token'};
      if (url === 'indexers/apply') return {state: 'connected', detail: 'Source tested and saved.'};
      if (url === 'indexers/status') return {sources: [], apps: []};
      return {providers: [provider]};
    },
    render: () => {renders++;state.dirty = state.appDirty = state.indexerDirty = false;},
    renderPreservingContext: () => {if (!state.dirty) renders++;},
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../stackarr/static/browser_links.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../stackarr/static/setup_extras.js'), 'utf8'), context);
  const controls = vm.runInContext('({indexerPanel,indexerProviderFieldId,bindSetupExtras})', context);
  function node(id, properties = {}) {
    const item = {id, value: '', type: 'text', disabled: false, reportValidity: () => true,
      listeners: new Map(), addEventListener(name, handler) {this.listeners.set(name, [...(this.listeners.get(name) || []), handler]);},
      dispatch(name) {for (const handler of this.listeners.get(name) || []) handler();},
      replaceChildren() {this.textContent = '';}, remove() {nodes.delete(id);}, ...properties};
    nodes.set(id, item);
    return item;
  }
  return {controls, context, state, calls, messages, nodes, node, selected, get renders() {return renders;}};
}

test('unselected and unconnected source apps do not create source setup tasks', () => {
  const f = fixture();
  assert.match(f.controls.indexerPanel(), /id="indexer-setup"/);
  f.selected.delete('prowlarr');
  assert.equal(f.controls.indexerPanel(), '');
  f.selected.add('prowlarr');f.state.credentials = [];
  assert.equal(f.controls.indexerPanel(), '');
});

test('provider forms use only schema controls with blank private values and escaped labels', () => {
  const f = fixture();
  f.state.indexerCatalog = {providers: [provider]};f.state.indexerProvider = provider.id;
  const html = f.controls.indexerPanel();
  assert.match(html, /Example &lt;Provider&gt;/);
  assert.doesNotMatch(html, /Example <Provider>/);
  assert.match(html, /type="password" value="" autocomplete="new-password" required/);
  assert.match(html, /provider’s account details/);
  assert.match(html, /value="basic">Basic/);
  assert.match(html, /without a download source/);
  assert.match(html, /<details id="indexer-advanced"><summary>Advanced provider setup/);
  assert.doesNotMatch(html, /id="indexer-advanced" open/);
  f.selected.delete('sonarr');
  assert.doesNotMatch(f.controls.indexerPanel(), /<option value="tv">/);
});

test('review sends typed provider details once, clears private inputs and retains only the public plan', async () => {
  const f = fixture();
  f.state.indexerCatalog = {providers: [provider]};f.state.indexerProvider = provider.id;
  f.state.dirty = f.state.indexerDirty = true;
  f.node('indexer-provider-review');f.node('indexer-provider-name', {value: 'My source'});
  const secret = f.node(f.controls.indexerProviderFieldId(provider, 0), {value: 'fixture-key', type: 'password', formField: true});
  f.node(f.controls.indexerProviderFieldId(provider, 1), {value: 'basic', type: 'select-one', formField: true});
  f.node(f.controls.indexerProviderFieldId(provider, 2), {value: '12', type: 'number', formField: true});
  f.node(f.controls.indexerProviderFieldId(provider, 3), {checked: true, type: 'checkbox', formField: true});
  f.controls.bindSetupExtras();
  await f.nodes.get('indexer-provider-review').onclick();
  assert.equal(f.calls.length, 1);
  assert.equal(f.calls[0].url, 'indexers/providers/review');
  assert.deepEqual(JSON.parse(JSON.stringify(f.calls[0].body)), {provider_id: provider.id, name: 'My source', fields: {apiKey: 'fixture-key', tier: 'basic', timeout: 12, special: true}});
  assert.equal(secret.value, '');
  assert.doesNotMatch(JSON.stringify(f.state), /fixture-key/);
  assert.equal(f.state.indexerReview.review_token, 'review-token');
  assert.equal(f.state.dirty, false);
});

test('failed source review still clears provider key and never leaves an old approval actionable', async () => {
  const f = fixture();
  f.state.indexerCatalog = {providers: [provider]};f.state.indexerProvider = provider.id;
  f.state.indexerReview = {review_token: 'old-review'};
  f.node('indexer-provider-review');f.node('indexer-provider-name', {value: 'My source'});
  const secret = f.node(f.controls.indexerProviderFieldId(provider, 0), {value: 'secret-on-error', type: 'password'});
  [1, 2, 3].forEach(index => f.node(f.controls.indexerProviderFieldId(provider, index)));
  f.context.api = async () => {throw new Error('Provider temporarily unavailable. Try again.');};
  f.controls.bindSetupExtras();await f.nodes.get('indexer-provider-review').onclick();
  assert.equal(secret.value, '');
  assert.equal(f.state.indexerReview, null);
  assert.match(f.messages[0], /temporarily unavailable/);
  assert.doesNotMatch(JSON.stringify(f.state), /secret-on-error|old-review/);
});

test('schema select values retain their scalar types and blank optional numbers are omitted', async () => {
  const f = fixture();
  const numeric = {...provider, fields: [
    {name: 'tier', label: 'Tier', type: 'select', required: true, options: [{value: 0, label: 'Default'}]},
    {name: 'limit', label: 'Limit', type: 'number', required: false},
  ]};
  f.state.indexerCatalog = {providers: [numeric]};f.state.indexerProvider = numeric.id;
  f.node('indexer-provider-review');f.node('indexer-provider-name', {value: 'Numeric options'});
  f.node(f.controls.indexerProviderFieldId(numeric, 0), {value: '0', type: 'select-one'});
  f.node(f.controls.indexerProviderFieldId(numeric, 1), {value: '', type: 'number'});
  f.controls.bindSetupExtras();await f.nodes.get('indexer-provider-review').onclick();
  assert.deepEqual(JSON.parse(JSON.stringify(f.calls[0].body.fields)), {tier: 0});
});

test('invalid required fields and unsaved app settings cannot submit a provider review', async () => {
  for (const appDirty of [false, true]) {
    const f = fixture();f.state.indexerCatalog = {providers: [provider]};f.state.indexerProvider = provider.id;
    f.state.appDirty = appDirty;f.state.dirty = true;
    f.node('indexer-provider-review');f.node('indexer-provider-name', {reportValidity: () => false});
    f.controls.bindSetupExtras();await f.nodes.get('indexer-provider-review').onclick();
    assert.equal(f.calls.length, 0);
    assert.equal(f.nodes.get('indexer-provider-review').disabled, false);
  }
});

test('a source search is read-only and sends the chosen media type, then reloads readiness', async () => {
  const f = fixture();f.node('indexers-validate');
  f.node('indexer-validation-query', {value: '  Original sample  '});f.node('indexer-validation-type', {value: 'tv'});
  f.controls.bindSetupExtras();await f.nodes.get('indexers-validate').onclick();
  assert.deepEqual(f.calls.map(call => call.url), ['indexers/validate', 'deployments']);
  assert.deepEqual(JSON.parse(JSON.stringify(f.calls[0].body)), {query: 'Original sample', media_type: 'tv'});
  assert.doesNotMatch(JSON.stringify(f.calls), /download|request|apply/);
});

test('zero matches remain distinct from provider failures and do not claim playback', () => {
  const f = fixture();
  f.state.indexerValidation = {state: 'no-matches', notice: 'No matching release.', sources: [{name: 'Working source', state: 'no-matches', result_count: 0, detail: 'Connection and categories passed.'}]};
  let html = f.controls.indexerPanel();
  assert.match(html, /Sources responded, but no matching copy was found/);
  assert.match(html, /working connection does not need to be replaced/);
  f.state.indexerValidation = {state: 'needs-attention', sources: [{name: 'Failed source', state: 'authentication-failed', result_count: null, detail: 'Check your provider account key.'}]};
  html = f.controls.indexerPanel();
  assert.match(html, /Provider sign-in or key rejected/);
  assert.doesNotMatch(html, /0 result\(s\)|Ready to watch|Sources responded, but no matching copy/);
});

test('unavailable app sharing stays unknown while known empty sharing offers wiring review', () => {
  const f = fixture();
  f.state.indexerStatus = {sources: [{name: 'Working source', enabled: true}], apps: [
    {app: 'sonarr', name: 'Sonarr', shared_sources: null, state: 'unavailable'},
    {app: 'radarr', name: 'Radarr', shared_sources: 0},
  ]};
  let html = f.controls.indexerPanel();
  assert.match(html, /Sonarr: sharing is unavailable/);
  assert.doesNotMatch(html, /Sonarr: 0 source/);
  assert.match(html, /Radarr: 0 source\(s\)/);
  assert.match(html, /id="indexer-test-connections"/);
  assert.match(html, /id="indexer-review-connections"/);
  f.selected.delete('sonarr');html = f.controls.indexerPanel();
  assert.doesNotMatch(html, /Sonarr:|id="indexer-test-connections"/);
});

test('unsaved source details block checks without discarding typed data', async () => {
  const f = fixture();f.state.dirty = f.state.indexerDirty = true;
  f.node('indexers-check');const secret = f.node('indexer-key', {value: 'still-entered'});f.node('indexer-error');
  f.controls.bindSetupExtras();await f.nodes.get('indexers-check').onclick();
  assert.equal(f.calls.length, 0);assert.equal(secret.value, 'still-entered');assert.equal(f.renders, 0);
  assert.match(f.nodes.get('indexer-error').textContent, /Review or clear/);
});

test('source apply requires a current reviewed token and never silently reconstructs a review', async () => {
  const f = fixture();f.node('indexer-apply');f.controls.bindSetupExtras();
  await f.nodes.get('indexer-apply').onclick();assert.equal(f.calls.length, 0);
  f.state.indexerReview = {review_token: 'reviewed-source'};
  await f.nodes.get('indexer-apply').onclick();
  assert.deepEqual(f.calls.map(call => call.url), ['indexers/apply', 'indexers/status', 'deployments']);
  assert.equal(f.calls[0].body.review_token, 'reviewed-source');assert.equal(f.state.indexerReview, null);
});

test('typing changed source details invalidates the displayed approval before another apply', () => {
  const f = fixture();f.state.indexerReview = {review_token: 'old-review'};
  const field = f.node('indexer-key', {value: 'changed-key', formField: true});
  const output = f.node('indexer-review-result', {textContent: 'Old reviewed source'});
  f.controls.bindSetupExtras();field.dispatch('input');
  assert.equal(f.state.indexerReview, null);assert.equal(output.textContent, '');
  assert.equal(field.value, 'changed-key');
});

test('changing query or media type removes stale search results without rewriting the input', () => {
  for (const id of ['indexer-validation-query', 'indexer-validation-type']) {
    const f = fixture();f.state.indexerValidation = {state: 'results'};f.state.indexerValidationFor = {query: 'Previous movie', media_type: 'movie'};
    const field = f.node(id, {value: 'new selection'});f.node('indexer-validation-result');
    f.controls.bindSetupExtras();field.dispatch('input');
    assert.equal(f.state.indexerValidation, null);assert.equal(f.state.indexerValidationFor, null);
    assert.equal(f.nodes.has('indexer-validation-result'), false);assert.equal(field.value, 'new selection');
  }
});

test('provider selection cannot replace unsaved fields and never marks a navigation choice dirty', () => {
  const f = fixture();f.state.dirty = f.state.indexerDirty = true;f.state.indexerProvider = 'previous';
  const select = f.node('indexer-provider', {value: 'new-provider'});
  f.controls.bindSetupExtras();let stopped = false;
  select.onchange({stopImmediatePropagation() {stopped = true;}});
  assert.equal(stopped, true);assert.equal(select.value, 'previous');
  assert.equal(f.renders, 0);assert.equal(f.state.indexerProvider, 'previous');
  assert.match(f.messages[0], /Review or clear/);
});

test('one pending source operation blocks a second check until its result arrives', async () => {
  const f = fixture();f.node('indexer-load-providers');f.node('indexers-check');
  let finish;
  f.context.api = async url => {f.calls.push({url});return new Promise(resolve => {finish = resolve;});};
  f.controls.bindSetupExtras();
  const pending = f.nodes.get('indexer-load-providers').onclick();
  await f.nodes.get('indexers-check').onclick();
  assert.deepEqual(f.calls.map(call => call.url), ['indexers/catalog']);
  assert.match(f.messages[0], /already running/);
  finish({providers: []});await pending;
  assert.equal(f.state.indexerBusy, false);assert.equal(f.nodes.get('indexer-load-providers').disabled, false);
});

test('provider and Torznab reviews discard old responses when source details change in flight', async () => {
  for (const mode of ['provider', 'torznab']) {
    const f = fixture();let finish;
    const simple = {...provider, fields: []};
    const button = mode === 'provider' ? 'indexer-provider-review' : 'indexer-review';
    f.state.indexerCatalog = {providers: [simple]};f.state.indexerProvider = simple.id;
    f.node(button);f.node('indexer-provider-name', {value: 'Original source'});
    f.node('indexer-name', {value: 'Original feed'});f.node('indexer-url', {value: 'https://source.invalid/api'});
    const field = f.node('indexer-key', {value: 'first-key', type: 'password', formField: true});
    f.context.api = async () => new Promise(resolve => {finish = resolve;});
    f.controls.bindSetupExtras();const pending = f.nodes.get(button).onclick();
    field.value = 'newer-key';field.dispatch('input');f.state.dirty = f.state.indexerDirty = true;
    finish({name: 'Old source details', review_token: 'old-reviewed-token'});await pending;
    assert.equal(f.renders, 0);assert.equal(field.value, 'newer-key');
    assert.equal(f.state.dirty, true);assert.equal(f.state.indexerReview, null);
    assert.match(f.messages[0], /Details changed/);
    assert.doesNotMatch(JSON.stringify(f.state), /old-reviewed-token/);
  }
});

test('app edits or a saved configuration revision change invalidate an in-flight source review', async () => {
  for (const change of ['app-edit', 'revision']) {
    const f = fixture();let finish;
    const simple = {...provider, fields: []};
    f.state.revision = 4;f.state.indexerCatalog = {providers: [simple]};f.state.indexerProvider = simple.id;
    f.node('indexer-provider-review');f.node('indexer-provider-name', {value: 'Source'});
    const appField = f.node('app-setting', {value: 'original'});
    f.context.api = async () => new Promise(resolve => {finish = resolve;});
    f.controls.bindSetupExtras();const pending = f.nodes.get('indexer-provider-review').onclick();
    appField.value = 'new setting';
    if (change === 'app-edit') f.state.dirty = f.state.appDirty = true;
    else f.state.revision++;
    finish({name: 'Source', review_token: 'old-reviewed-token'});await pending;
    assert.equal(f.renders, 0);assert.equal(appField.value, 'new setting');assert.equal(f.state.indexerReview, null);
    assert.match(f.messages[0], /Details changed/);
  }
});

test('query or category edits during a search prevent its response appearing under the new selection', async () => {
  for (const change of ['query', 'category', 'checklist-category']) {
    const f = fixture();let finish;
    f.node('indexers-validate');const query = f.node('indexer-validation-query', {value: 'Original sample'});
    const type = f.node('indexer-validation-type', {value: 'movie'});
    f.context.api = async url => url === 'deployments' ? {} : new Promise(resolve => {finish = resolve;});
    f.controls.bindSetupExtras();const pending = f.nodes.get('indexers-validate').onclick();
    if (change === 'query') {query.value = 'New sample';query.dispatch('input');}
    else {type.value = 'tv';if (change !== 'checklist-category') type.dispatch('input');}
    finish({state: 'results', sources: []});await pending;
    assert.equal(f.state.indexerValidation, null);assert.equal(f.state.indexerValidationFor, null);
    assert.equal(f.renders, 0);assert.match(f.messages[0], /Search details changed/);
    assert.equal(query.value, change === 'query' ? 'New sample' : 'Original sample');
  }
});


test('beginner source action reviews, tests and connects once without a second button',async()=>{
 const f=fixture();f.state.indexerCatalog={providers:[provider]};f.state.indexerProvider=provider.id;
 f.node('indexer-provider-connect');f.node('indexer-provider-name',{value:'My source'});
 f.node(f.controls.indexerProviderFieldId(provider,0),{value:'fixture-secret',type:'password',formField:true});
 f.node(f.controls.indexerProviderFieldId(provider,1),{value:'basic',type:'select-one',formField:true});
 f.node(f.controls.indexerProviderFieldId(provider,2),{value:'',type:'number',formField:true});
 f.node(f.controls.indexerProviderFieldId(provider,3),{type:'checkbox',formField:true});
 f.controls.bindSetupExtras();await f.nodes.get('indexer-provider-connect').onclick();
 assert.deepEqual(f.calls.map(call=>call.url),['indexers/providers/review','indexers/apply','indexers/status','deployments']);
 assert.equal(f.state.indexerResult.state,'connected');assert.equal(f.state.indexerReview,null);
 assert.doesNotMatch(JSON.stringify(f.state),/fixture-secret/);
});

test('editing during the one-click provider review prevents its automatic write',async()=>{
 const f=fixture();f.state.indexerCatalog={providers:[provider]};f.state.indexerProvider=provider.id;
 f.node('indexer-provider-connect');f.node('indexer-provider-name',{value:'My source'});
 [0,1,2,3].forEach(index=>f.node(f.controls.indexerProviderFieldId(provider,index),{value:index===0?'fixture-key':index===1?'basic':'',type:index===0?'password':'text',formField:true}));
 let finish;f.context.api=async(url)=>{f.calls.push({url});return new Promise(resolve=>finish=resolve);};
 f.controls.bindSetupExtras();const pending=f.nodes.get('indexer-provider-connect').onclick();
 f.nodes.get(f.controls.indexerProviderFieldId(provider,1)).dispatch('input');
 finish({review_token:'old',name:'My source'});await pending;
 assert.deepEqual(f.calls.map(call=>call.url),['indexers/providers/review']);assert.equal(f.state.indexerReview,null);
});


test('the next-watch action requires known sharing and an enabled request connection',()=>{
 const f=fixture();f.state.config.integrations.seerr={enabled:true};f.state.credentials.push('seerr');
 f.state.indexerStatus={sources:[{enabled:true}],apps:[{app:'sonarr',shared_sources:1},{app:'radarr',shared_sources:0}]};
 assert.doesNotMatch(f.controls.indexerPanel(),/Find a movie or show/);
 f.state.indexerStatus.apps[1].shared_sources=1;assert.match(f.controls.indexerPanel(),/Find a movie or show/);
 f.state.config.integrations.seerr.enabled=false;assert.doesNotMatch(f.controls.indexerPanel(),/Find a movie or show/);
});
