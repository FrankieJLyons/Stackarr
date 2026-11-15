'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const test=require('node:test');
function fixture(){
 const context=vm.createContext({structuredClone});
 vm.runInContext(`var state={config:{integrations:{sonarr:{enabled:true},radarr:{enabled:true},qbittorrent:{enabled:false}}},credentials:['sonarr','radarr'],catalog:{sonarr:{name:'Sonarr'}}};var qualityState={data:null};var escape=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');var appLink=()=>'',browserAppUrl=()=>'';`,context);
 vm.runInContext(fs.readFileSync('stackarr/static/presets.js','utf8'),context);
 vm.runInContext(`presetState.catalog={version:'test',scope:'New requests only',tradeoffs:[],sources:[],presets:[{id:'hd',name:'<test>',description:'<unsafe>',tier:'1080p',recommended:true}]};`,context);
 return context;
}
test('recommendations escape content and explain the apply boundary',()=>{
 const c=fixture(),html=c.recommendedSettingsPanel();
 assert.match(html,/&lt;test&gt;/);assert.doesNotMatch(html,/<unsafe>/);
 assert.match(html,/Preview for Sonarr/);assert.doesNotMatch(html,/quality-apply/);
 assert.match(html,/guidance; Stackarr does not apply them automatically/);
 assert.match(html,/Connect qbittorrent first/);
});
test('missing credentials and read-only apps have disabled preset controls',()=>{
 const c=fixture();vm.runInContext('state.config.integrations.sonarr.read_only=true',c);
 assert.match(c.recommendedSettingsPanel(),/data-quality-preset="hd" disabled/);
 assert.match(c.recommendedSettingsPanel(),/connection is read-only/);
 vm.runInContext('state.config.integrations.sonarr.read_only=false;state.credentials=[]',c);
 assert.match(c.recommendedSettingsPanel(),/Save the app credentials/);
 assert.match(c.recommendedSettingsPanel(),/data-quality-preset="hd" disabled/);
});
test('preset requests lock app selection until the response is handled',async()=>{
 const c=fixture(),button={dataset:{qualityPreset:'hd'}},select={setAttribute(k){this[k]=true;}},handlers={};
 c.document={querySelectorAll:s=>s==='[data-quality-preset]'?[button]:[],getElementById:id=>id==='preset-app'?select:null,querySelector:()=>null};
 c.api=async(path)=>{assert.equal(select.disabled,true);if(path==='quality-rules/sonarr')return {revision:0};return {app:'sonarr'};};c.render=()=>{};
 vm.runInContext('presetState.catalog.presets[0].policy={enabled:true}',c);
 c.bindPresets();await button.onclick();
 assert.equal(select.disabled,true);
 assert.equal(vm.runInContext('qualityState.app',c),'sonarr');
 assert.equal(vm.runInContext('qualityState.preset',c),'<test>');
});
