'use strict';
const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const test=require('node:test');

function fixture(){
 const timers=[];
 const context=vm.createContext({document:{addEventListener(){},getElementById(){return null;},hidden:false},
  setTimeout:(fn,delay)=>{timers.push({fn,delay});return timers.length;},clearTimeout(){},
  state:{view:'home'},Date,encodeURIComponent});
 vm.runInContext(fs.readFileSync('stackarr/static/home.js','utf8'),context);
 vm.runInContext('repaintHome=()=>{};',context);
 const controls=vm.runInContext('({homeState,loadHome,clearHome,scheduleHome})',context);
 return {context,timers,...controls,setApi(api){context.fakeApi=api;vm.runInContext('api=fakeApi;',context);}};
}

test('one pending refresh prevents duplicate work',async()=>{
 const f=fixture();let resolve,calls=0;
 f.setApi(()=>{calls++;return new Promise(done=>resolve=done);});
 const first=f.loadHome();await f.loadHome();assert.equal(calls,1);
 resolve({checked_at:1});await first;
 assert.equal(f.homeState.data.checked_at,1);assert.equal(f.homeState.loading,false);
});

test('sign-out discards a late catalog response and its request names',async()=>{
 const f=fixture();let resolve;
 f.setApi(()=>new Promise(done=>resolve=done));
 const pending=f.loadHome();f.clearHome();resolve({items:['private title']});await pending;
 assert.equal(f.homeState.data,null);assert.equal(f.homeState.loading,false);assert.equal(f.homeState.query,'');
});

test('a failed refresh retains the previous snapshot and recovers without inventing empty results',async()=>{
 const f=fixture();f.homeState.data={checked_at:100,requests:{items:['existing request']}};
 f.setApi(async()=>{throw new Error('Offline');});await f.loadHome();
 assert.equal(f.homeState.data.checked_at,100);assert.equal(f.homeState.error,'Offline');
 f.setApi(async()=>({checked_at:200}));await f.loadHome();
 assert.equal(f.homeState.error,'');assert.equal(f.homeState.data.checked_at,200);
});

test('refreshing requests does not mark the cached library snapshot as newly checked',async()=>{
 const f=fixture();f.homeState.data={checked_at:100};f.context.state.view='requests';
 f.setApi(async path=>{assert.equal(path,'home/requests?page=1');return {checked_at:200,items:[]};});
 await f.loadHome({requests:true});
 assert.equal(f.homeState.requests.checked_at,200);assert.equal(f.homeState.data.checked_at,100);
});

test('title polling pauses for hidden pages, management screens and active searches',()=>{
 const f=fixture();f.scheduleHome();assert.equal(f.timers.at(-1).delay,30000);
 f.context.document.hidden=true;f.scheduleHome();assert.equal(f.timers.length,1);
 f.context.document.hidden=false;f.context.state.view='apps';f.scheduleHome();assert.equal(f.timers.length,1);
 f.context.state.view='home';f.homeState.results={items:[]};f.scheduleHome();assert.equal(f.timers.length,1);
});

test('a previous search cannot disable request or library polling after navigation',()=>{
 const f=fixture();f.homeState.results={items:['cached search']};
 f.context.state.view='requests';f.scheduleHome();assert.equal(f.timers.length,1);
 f.context.state.view='library';f.scheduleHome();assert.equal(f.timers.length,2);
 assert.equal(f.timers.at(-1).delay,30000);
});

test('new searches clear old cards before the response so titles cannot be requested under the wrong query',async()=>{
 const f=fixture();let resolve;f.homeState.results={items:['previous movie'],pages:2};f.homeState.query='A TV show';
 f.setApi(()=>new Promise(done=>resolve=done));const pending=f.loadHome({search:true});
 assert.equal(f.homeState.loading,true);assert.equal(f.homeState.results.items.length,0);
 resolve({items:['correct show'],pages:1});await pending;
 assert.equal(f.homeState.results.items[0],'correct show');
});


test('manual refresh follows the current view despite cached search results',()=>{
 const f=fixture();f.homeState.results={items:['old search']};
 const options=()=>vm.runInContext('homeRefreshOptions()',f.context);
 f.context.state.view='requests';assert.equal(options().search,false);assert.equal(options().requests,true);
 f.context.state.view='library';assert.equal(options().search,false);assert.equal(options().requests,false);
 f.context.state.view='home';assert.equal(options().search,true);
});

test('quality controls use only offered choices and cannot promise a profile for an existing show',()=>{
 const f=fixture();f.context.escape=value=>String(value).replaceAll('<','&lt;');
 f.context.item={can_request:true,quality_options:[{value:'opaque-choice',label:'1080p',default:true}]};
 const html=vm.runInContext('homeQualityChoice(item)',f.context);
 assert.match(html,/Download quality/);assert.match(html,/opaque-choice/);assert.match(html,/your default/);
 f.context.item={can_request:true,quality_options:[],quality_notice:'Reconnect first'};
 assert.match(vm.runInContext('homeQualityChoice(item)',f.context),/Continue setup/);
 f.context.item={can_request:true,existing_series:true,quality_notice:'Existing quality settings'};
 assert.doesNotMatch(vm.runInContext('homeQualityChoice(item)',f.context),/<select/);
});


test('startup opens setup for a new stack and the control room for configured apps',()=>{
 const source=fs.readFileSync('stackarr/static/app.js','utf8');
 const fn=source.slice(source.indexOf('function initialView(){'),source.indexOf('async function load(){'));
 const context=vm.createContext({state:{config:{integrations:{}},credentials:[]}});
 vm.runInContext(fn,context);
 assert.equal(vm.runInContext('initialView()',context),'setup');
 context.state.config.integrations={seerr:{enabled:true}};
 assert.equal(vm.runInContext('initialView()',context),'overview');
 context.state.credentials=['seerr'];assert.equal(vm.runInContext('initialView()',context),'overview');
 context.state.config.integrations={plex:{enabled:true}};assert.equal(vm.runInContext('initialView()',context),'overview');
 context.state.config.integrations={kuma:{enabled:true}};assert.equal(vm.runInContext('initialView()',context),'overview');
});
