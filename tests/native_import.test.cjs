const assert=require('node:assert/strict');
const test=require('node:test');
const fs=require('node:fs');
const vm=require('node:vm');
const script=fs.readFileSync('stackarr/static/native_import.js','utf8');
function context(){
 const ctx=vm.createContext({setupDeployment:{host_checks:true},state:{config:{integrations:{sonarr:{enabled:false}}},catalog:{sonarr:{name:'Sonarr'}}},
  escape:value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')});
 vm.runInContext(script,ctx);
 return ctx;
}
const snapshot={app:'sonarr',version:'4.0',browser_address:'http://localhost:8989',root_folders:[{path:'D:/<private>'}],
 quality_profiles:[{name:'<custom>',qualities:[{name:'SDTV',allowed:true},{name:'CAM',allowed:false}]}],download_clients:[],sources:[],linked_apps:[]};
test('native settings preview escapes text and shows actual allowed qualities',()=>{
 const html=context().nativeSnapshot(snapshot);
 assert.match(html,/&lt;private&gt;|&lt;custom&gt;/);
 assert.match(html,/Allowed: SDTV/);
 assert.doesNotMatch(html,/<custom>|<private>|CAM/);
});
test('review explains read-only import and separate original installation',()=>{
 const ctx=context();ctx.fixture=snapshot;
 vm.runInContext('nativeReview={snapshot:fixture,notice:"Keep original settings"};',ctx);
 const html=ctx.nativeImportPanel();
 assert.match(html,/Import connection and settings/);
 assert.match(html,/read-only/);
 assert.match(html,/does not transfer its database into Docker/);
 assert.match(html,/No default quality is chosen automatically/);
});
test('a different saved app has no import button',()=>{
 const ctx=context();ctx.fixture=snapshot;
 vm.runInContext('nativeScan={apps:[{app:"sonarr",state:"verified",snapshot:fixture}]};state.config.integrations.sonarr.enabled=true;',ctx);
 const html=ctx.nativeImportPanel();
 assert.doesNotMatch(html,/data-native-review=/);
 assert.match(html,/different connection/);
});
