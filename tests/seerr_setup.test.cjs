'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
const { stripTypeScriptTypes } = require('node:module');

function fixture({ post, get, pathname = '/setup', stored } = {}) {
  const storage = new Map(stored ? [['stackarr.plex-signin.v1', JSON.stringify(stored)]] : []);
  const calls = [], navigations = [];
  const axios = {
    post: async (...args) => { calls.push(args); return post ? post(...args) : { data: { id: 51, code: 'strong-pin' } }; },
    get: async (...args) => { calls.push(args); return get ? get(...args) : { data: { authToken: 'fixture-plex' } }; },
  };
  const source = fs.readFileSync('platform/seerr/plex-login.ts', 'utf8')
    .replace("import axios from 'axios';", '')
    .replace('export default PlexOAuth;', 'globalThis.OAuth = PlexOAuth;');
  const scope = { axios, URLSearchParams, Date, AbortController, setTimeout, clearTimeout,
    sessionStorage: { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) },
    window: { location: { pathname, origin: 'http://localhost:43409', assign: url => navigations.push(url) } },
  };
  vm.runInNewContext(stripTypeScriptTypes(source), scope);
  return { oauth: new scope.OAuth(), storage, calls, navigations };
}

test('same-tab sign-in uses strong PIN and exact local callback, without token storage', async () => {
  const f = fixture();
  f.oauth.login('client-id');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(f.navigations.length, 1);
  const destination = new URL(f.navigations[0]);
  assert.equal(destination.origin, 'https://app.plex.tv');
  const params = new URLSearchParams(destination.hash.slice(3));
  assert.equal(params.get('forwardUrl'), 'http://localhost:43409/login/plex/loading');
  assert.equal(params.get('code'), 'strong-pin');
  const saved = JSON.parse([...f.storage.values()][0]);
  assert.equal(saved.returnPath, '/setup');
  assert.deepEqual(Object.keys(saved).sort(), ['client', 'expires', 'id', 'returnPath']);
});

test('callback polls the matching PIN and returns the token only in memory', async () => {
  const f = fixture({ stored: { id: 51, client: 'client-id', expires: Date.now() + 60000, returnPath: '/setup' } });
  assert.equal(await f.oauth.resume(new AbortController().signal), 'fixture-plex');
  assert.equal(f.calls[0][0], 'https://plex.tv/api/v2/pins/51');
  assert.equal(f.calls[0][1].headers['X-Plex-Client-Identifier'], 'client-id');
  assert.ok(![...f.storage.values()][0].includes('fixture-plex'));
  f.oauth.clear();
  assert.equal(f.storage.size, 0);
});

for (const altered of [
  { expires: Date.now() - 1000 }, { expires: Date.now() + 3600000 },
  { id: '51' }, { returnPath: '//attacker.invalid' }, { client: '' },
]) {
  test('invalid or expired callback receipt fails before provider lookup: ' + JSON.stringify(altered), async () => {
    const f = fixture({ stored: { id: 51, client: 'client', expires: Date.now() + 60000, returnPath: '/setup', ...altered } });
    await assert.rejects(f.oauth.resume(new AbortController().signal), /expired/);
    assert.equal(f.calls.length, 0);
    assert.equal(f.oauth.returnPath(), '/login');
  });
}

test('cancelled PIN polling makes no network request', async () => {
  const f = fixture({ stored: { id: 51, client: 'client', expires: Date.now() + 60000, returnPath: '/login' } });
  const abort = new AbortController(); abort.abort();
  await assert.rejects(f.oauth.resume(abort.signal), /cancelled/);
  assert.equal(f.calls.length, 0);
});

test('failed PIN creation and malformed provider responses never navigate or retain a receipt', async () => {
  for (const post of [async () => { throw Error('network'); }, async () => ({ data: { id: 'unsafe', code: 'x' } })]) {
    const f = fixture({ post });
    await assert.rejects(f.oauth.login('client'));
    assert.equal(f.storage.size, 0);
    assert.equal(f.navigations.length, 0);
  }
});
