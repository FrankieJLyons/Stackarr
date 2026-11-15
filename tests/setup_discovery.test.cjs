const assert=require('node:assert/strict');
const test=require('node:test');
const fs=require('node:fs');
const vm=require('node:vm');
const context=vm.createContext({structuredClone});
vm.runInContext(fs.readFileSync('stackarr/static/setup_discovery.js','utf8'),context);
const use=context.setupUseDiscovered;

test('choosing an existing app preserves unrelated choices and clears install-only quality',()=>{
 const draft={apps:['sonarr','radarr'],choices:{sonarr:{mode:'install',quality_profile:'SD'},radarr:{mode:'install',quality_profile:'HD-1080p'}},data_root:'/data'};
 const result=use(draft,{app:'sonarr',state:'credentials-required',address:'http://host.docker.internal:18989',browser_address:'http://127.0.0.1:18989'});
 assert.equal(draft.choices.sonarr.mode,'install');
 assert.equal(result.choices.sonarr.mode,'connect');
 assert.equal(result.choices.sonarr.quality_profile,'');
 assert.equal(result.choices.sonarr.browser_url,'http://127.0.0.1:18989');
 assert.equal(result.choices.radarr.quality_profile,'HD-1080p');
 assert.equal(result.apps.length,2);
});
test('discovery can select a previously unselected app but cannot use an unrecognized response',()=>{
 const result=use({apps:[],choices:{}},{app:'plex',state:'compatible-api',address:'http://127.0.0.1:42400'});
 assert.equal(result.apps[0],'plex');
 assert.throws(()=>use({apps:[],choices:{}},{app:'plex',state:'unverified'}),/manually/);
});

test('the discovery summary hides failed duplicate probes and escapes displayed addresses',()=>{
 const ctx=vm.createContext({setupDiscovery:{message:'Hints',results:[
  {app:'sonarr',state:'credentials-required',address:'<untrusted>',source:'docker-published-port'},
  {app:'sonarr',state:'not-detected',address:'default'},
  {app:'radarr',state:'not-detected',address:'default'}]},
  setupDeployment:{operations:[]},state:{catalog:{sonarr:{name:'Sonarr'},radarr:{name:'Radarr'}}},
  escape:value=>String(value).replaceAll('<','&lt;').replaceAll('>','&gt;')});
 vm.runInContext(fs.readFileSync('stackarr/static/setup_discovery.js','utf8'),ctx);
 const html=ctx.setupDiscoveryPanel();
 assert.match(html,/&lt;untrusted&gt;/);
 assert.doesNotMatch(html,/<untrusted>|not detected/);
 assert.match(html,/No confirmed connection found for Radarr/);
 assert.equal((html.match(/data-discovered-app=/g)||[]).length,1);
});
