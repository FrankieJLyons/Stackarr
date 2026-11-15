'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const test=require('node:test');
const vm=require('node:vm');

function fixture(){
 const context=vm.createContext({structuredClone});
 vm.runInContext(`
  var state={config:{dashboard:{order:['plex','sonarr','radarr','qbittorrent']},integrations:{plex:{enabled:true},sonarr:{enabled:true},radarr:{enabled:false},qbittorrent:{enabled:false}}},catalog:{plex:{name:'Plex'},sonarr:{name:'Sonarr'},radarr:{name:'Radarr'},qbittorrent:{name:'qBittorrent'}}};
  var setupDeployment={available:true,operations:[{id:'owned',state:'needs-setup',apps:['sonarr']}],actions:[]};
  var integrations=()=>[{id:'sonarr',state:'ready',stale:false}];
  var escape=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  var browserAppUrl=()=>'', appLink=()=>'<span>Open app</span>', time=()=>'';
 `,context);
 vm.runInContext(fs.readFileSync('stackarr/static/preferences.js','utf8'),context);
 vm.runInContext(fs.readFileSync('stackarr/static/control_room.js','utf8'),context);
 return context;
}

test('only one current owned deployment offers restart; imports and unavailable controllers never do',()=>{
 const ctx=fixture();
 assert.match(vm.runInContext("stackCard('sonarr')",ctx),/data-stack-restart="sonarr"/);
 assert.doesNotMatch(vm.runInContext("stackCard('plex')",ctx),/data-stack-restart/);
 for(const change of ["setupDeployment.status_stale=true", "setupDeployment.available=false", "state.config.integrations.sonarr.read_only=true", "setupDeployment.operations.push({...setupDeployment.operations[0],id:'duplicate'})"]){
  const f=fixture();vm.runInContext(change,f);
  assert.doesNotMatch(vm.runInContext("stackCard('sonarr')",f),/data-stack-restart/);
 }
});

test('adding an app preserves unfinished choices and storage while excluding existing apps from new installation',()=>{
 const ctx=fixture();
 ctx.draft={step:2,data_root:'H:/Media',folder_root:1,folder_relative:'Media',port_mode:'automatic',apps:['sonarr','qbittorrent'],choices:{sonarr:{mode:'install'},qbittorrent:{mode:'install',port:28002}}};
 const next=vm.runInContext("stackAddDraft(draft,'radarr','install')",ctx);
 assert.deepEqual(Array.from(next.apps),['qbittorrent','radarr']);
 assert.equal(next.choices.qbittorrent.port,28002);
 assert.equal(next.data_root,'H:/Media');
 assert.equal(next.folder_root,1);
 assert.equal(next.folder_relative,'Media');
 assert.equal(next.step,0);
 assert.equal(ctx.draft.step,2);
 assert.equal(ctx.draft.apps.length,2);
 assert.throws(()=>vm.runInContext("stackAddDraft(draft,'sonarr','install')",ctx),/already configured/);
});

test('connecting an app clears installation quality and groups keep the original control room order',()=>{
 const ctx=fixture();
 ctx.draft={step:1,apps:['radarr'],choices:{radarr:{mode:'install',quality_profile:'Ultra-HD',url:'http://host:7878'}}};
 const next=vm.runInContext("stackAddDraft(draft,'radarr','connect')",ctx);
 assert.equal(next.choices.radarr.quality_profile,'');
 assert.equal(next.choices.radarr.url,'http://host:7878');
 vm.runInContext('state.config.integrations.qbittorrent.enabled=true',ctx);
 const html=vm.runInContext('stackApplications()',ctx);
 assert.ok(html.indexOf('>Library &amp; playback<')<html.indexOf('>Requests &amp; downloads<'));
 assert.doesNotMatch(html,/<h3>Radarr<\/h3>/);
 vm.runInContext('state.config.integrations.sonarr.visible=false',ctx);
 assert.doesNotMatch(vm.runInContext('stackApplications()',ctx),/<h3>Sonarr<\/h3>/);
});

test('quick restart checks ownership and runtime, then reviews start for a stopped app without applying',async()=>{
 for(const [actions,expected] of [[['restart','stop'],'restart'],[['start'],'start'],[[],null]]){
  const ctx=fixture(),calls=[],reviews=[];
  const button={dataset:{stackDeployment:'owned',stackRestart:'sonarr'},disabled:false};
  const output={isConnected:true,textContent:''};
  Object.assign(ctx,{root:{querySelectorAll:selector=>selector==='[data-stack-restart]'?[button]:[]},
   document:{getElementById:id=>id==='lifecycle-review'?output:null},leaveScreen:()=>true,announce:()=>{},
   api:async(path,method,body)=>{calls.push({path,method,body});return path.endsWith('/check')?{apps:[{app:'sonarr',actions,detail:'Ownership changed'}]}:{action:body.action,name:'Sonarr'};},
   showManagedReview:review=>reviews.push(review)});
  ctx.bindControlRoom();await button.onclick();
  assert.equal(calls[0].path,'deployments/owned/check');
  assert.equal(calls.length,expected?2:1);
  if(expected)assert.equal(reviews[0].action,expected);
  else assert.match(output.textContent,/Ownership changed/);
  assert.equal(button.disabled,false);
  assert.ok(calls.every(call=>!call.path.includes('/apply')));
 }
});

test('partial settings forms preserve fields from other sections',()=>{
 const ctx=fixture();
 const controls={appearance:{value:'light'},accent:{value:'purple'},'refresh-seconds':{value:'60'}};
 ctx.document={getElementById:id=>controls[id]};
 ctx.config={dashboard:{appearance:'dark',accent:'blue',refresh_seconds:30,page_size:10,overview_widgets:['downloads']},storage:{data_root:'H:/Media',uid:1000},maintenance:{backups_enabled:true,backup_retention:7}};
 const result=vm.runInContext('readSettingsFields(structuredClone(config))',ctx);
 assert.equal(result.dashboard.accent,'purple');
 assert.equal(result.dashboard.appearance,'light');
 assert.equal(result.dashboard.refresh_seconds,60);
 assert.equal(result.dashboard.page_size,10);
 assert.equal(result.storage.data_root,'H:/Media');
 assert.equal(result.maintenance.backups_enabled,true);
 assert.equal(result.maintenance.backup_retention,7);
});

test('setup blockers name a real prerequisite without preventing a standalone library app',()=>{
 const ctx=fixture();
 ctx.state=vm.runInContext('state',ctx);
 ctx.state.credentials=[];
 ctx.row={state:'needs-action',action:{id:'source-setup'},apps:['prowlarr']};
 assert.match(vm.runInContext('setupActionBlock(row)',ctx),/Connect Prowlarr/);
 ctx.row={state:'needs-action',action:{id:'accounts',app:'sonarr'},apps:['sonarr']};
 assert.equal(vm.runInContext('setupActionBlock(row)',ctx),'');
});

test('status labels distinguish expired credentials from stale data and unknown metrics stay unknown',()=>{
 const ctx=fixture();
 ctx.status={state:'unavailable',error_code:'authentication',stale:true,collected_at:null};
 assert.equal(vm.runInContext('connectionState(status).label',ctx),'Sign-in needed');
 ctx.status={state:'ready',stale:true,collected_at:1};
 assert.equal(vm.runInContext('connectionState(status).label',ctx),'Stale');
 assert.equal(vm.runInContext("widgetData('downloads').value",ctx),'—');
 ctx.rows=[{id:'qbittorrent',name:'qBittorrent',state:'ready',stale:false,capabilities:['downloads'],tables:{downloads:[{state:'downloading'},{state:'seeding'}]}}];
 vm.runInContext('integrations=()=>rows',ctx);
 assert.equal(vm.runInContext("widgetData('downloads').value",ctx),'1');
});
