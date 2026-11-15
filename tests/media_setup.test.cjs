const assert=require('node:assert/strict');
const test=require('node:test');
const fs=require('node:fs');
const vm=require('node:vm');
function fixture(native=false){
 const context=vm.createContext({Date,escape:value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'),state:{config:{integrations:{plex:{enabled:true},qbittorrent:{enabled:true},sonarr:{enabled:true,read_only:native}}}}});
 vm.runInContext(fs.readFileSync('stackarr/static/media_setup.js','utf8'),context);
 return context;
}
test('protection explains filename limits and archives tradeoff',()=>{
 const html=fixture().mediaSetupPanel();
 assert.match(html,/cannot guarantee/);assert.match(html,/legitimate zipped/);assert.match(html,/Existing downloads keep/);
 assert.match(html,/Check & preview protection/);
});
test('native media apps cannot be selected for writes',()=>{
 const html=fixture(true).mediaSetupPanel();
 assert.match(html,/data-mapping-review="sonarr" disabled/);assert.match(html,/read-only/);
});
test('mapping review escapes library names and shows the actual route',()=>{
 const ctx=fixture();
 vm.runInContext(`mediaSetup.mapping={app:'sonarr',library:{name:'<bad>',path:'/plex/TV'},root:'/data/media/tv',staging:'/data/downloads/sonarr',notice:'New requests only',refresh:'Notify Plex',enable_category_paths:true};`,ctx);
 const html=ctx.mediaSetupPanel();
 assert.match(html,/&lt;bad&gt;/);assert.doesNotMatch(html,/<bad>/);
 assert.match(html,/\/data\/downloads\/sonarr/);assert.match(html,/\/plex\/TV/);
 assert.match(html,/all qBittorrent categories/);assert.match(html,/Use this library for new requests/);
 ctx.clearMediaSetup();assert.doesNotMatch(ctx.mediaSetupPanel(),/id="mapping-apply"/);
});
