'use strict';
const stackGroups=[['library','Library & playback',['plex','sonarr','radarr']],['workflow','Requests & downloads',['seerr','prowlarr','qbittorrent']],['tools','Tools & monitoring',['cleanuparr','tautulli','kuma']]];
function controlRoomShell(){
 const tabs=[['overview','Overview'],['activity','Activity'],['health','Health'],['apps','Apps'],['setup','Setup'],['settings','Settings'],['help','Help / FAQ'],['backups','Backups'],['home','Discover']];
 return `<div class="shell control-room"><div class="workspace"><header class="control-header"><div>${brand()}<span class="eyebrow">HOME MEDIA CONTROL ROOM</span><h1>Media Stack</h1><p>Your library, automation, downloads and monitoring.</p></div><div class="actions"><button class="primary" data-view="apps">Add app +</button><button id="logout" class="linklike">Sign out</button></div></header><nav class="control-tabs" aria-label="Main navigation">${tabs.map(([key,label])=>`<button data-view="${key}" ${(state.view===key||(key==='home'&&watchViews.includes(state.view)))?'aria-current="page"':''}>${label}</button>`).join('')}</nav><main class="content" id="main" tabindex="-1">${state.error?`<div class="banner error" role="alert">${escape(state.error)}</div>`:''}${state.notice?`<div class="banner" role="status">${escape(state.notice)}</div>`:''}${watchViews.includes(state.view)?'<nav class="settings-tabs" aria-label="Media views">'+[['home','Discover'],['requests','Your requests'],['library','Your library']].map(([id,label])=>`<button data-view="${id}" ${state.view===id?'aria-current="page"':''}>${label}</button>`).join('')+'</nav>':''}${content()}</main></div></div>`;
}
function stackOwner(key){
 if(!setupDeployment.available||setupDeployment.status_stale||state.config.integrations[key]?.read_only)return null;
 const owners=(setupDeployment.operations||[]).filter(op=>op.state==='needs-setup'&&op.apps?.includes(key));
 return owners.length===1?owners[0]:null;
}
function stackCard(key){return refinedAppCard(key);}
function stackApplications(all=false){return groupedAppCards(all);}
function stackActionPanel(){return '<section class="stack-actions-status" aria-label="Review app action"><div id="lifecycle-review" role="status"></div></section>';}
function stackAddDraft(draft,key,mode){
 if(!state.catalog[key]||state.config.integrations[key]?.enabled)throw new Error('This app is already configured. Use Manage to change its connection.');
 if(!['install','connect'].includes(mode))throw new Error('Choose install or connect.');
 // Keep unfinished choices, storage and port preferences. Already configured
 // apps must not be submitted as fresh installations a second time.
 const next=structuredClone(draft);
 next.apps=next.apps.filter(app=>!state.config.integrations[app]?.enabled);
 next.choices=Object.fromEntries(Object.entries(next.choices||{}).filter(([app])=>next.apps.includes(app)));
 if(!next.apps.includes(key))next.apps.push(key);
 next.choices[key]={...next.choices[key],mode,url:next.choices[key]?.url||'',port:next.choices[key]?.port||0,quality_profile:mode==='install'?(next.choices[key]?.quality_profile||''):''};
 next.step=0;
 return next;
}
function showStackCatalog(){state.view='apps';render();}
function bindControlRoom(){
 bindPreferences();
 root.querySelectorAll('[data-stack-catalog]').forEach(button=>button.onclick=()=>{if(leaveScreen())showStackCatalog(button.dataset.stackCatalog);});
 root.querySelectorAll('[data-stack-edit]').forEach(button=>button.onclick=()=>{
  if(!leaveScreen())return;
  openConnectionSettings(button.dataset.stackEdit);
 });
 root.querySelectorAll('[data-stack-restart]').forEach(button=>button.onclick=async()=>{
  if(!leaveScreen())return;
  button.disabled=true;const output=document.getElementById('lifecycle-review');
  if(output)output.textContent='Checking the current app state…';
  try{
   const deployment=button.dataset.stackDeployment,key=button.dataset.stackRestart;
   const checked=await api('deployments/'+deployment+'/check','POST',{});
   const app=checked.apps.find(row=>row.app===key);
   const action=app?.actions?.includes('restart')?'restart':app?.actions?.includes('start')?'start':null;
   if(!action)throw new Error(app?.detail||'Open Apps and check this installation before restarting.');
   const review=await api('deployments/'+deployment+'/apps/'+key+'/review','POST',{action});
   if(output?.isConnected)showManagedReview(review,review.name);
  }catch(error){if(output?.isConnected)output.textContent=error.message;announce(error.message);}finally{button.disabled=false;}
 });
}
