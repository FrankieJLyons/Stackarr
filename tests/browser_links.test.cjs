const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('LAN browser links never fall back to another computer’s localhost', () => {
  const state = {network: {mode:'home-network', app_links:{plex:'https://plex.home.arpa'}},
    config:{integrations:{plex:{url:'http://localhost:32400'}, sonarr:{browser_url:'http://localhost:8989'}}}};
  const context = vm.createContext({state, escape:value=>String(value)});
  vm.runInContext(fs.readFileSync('stackarr/static/browser_links.js','utf8'), context);
  assert.equal(context.browserAppUrl('plex'),'https://plex.home.arpa');
  assert.equal(context.browserAppUrl('sonarr'),'');
  assert.doesNotMatch(context.appLink(context.browserAppUrl('sonarr')), /href=/);
  state.network.mode='this-computer';
  assert.equal(context.browserAppUrl('sonarr'),'http://localhost:8989');
});
