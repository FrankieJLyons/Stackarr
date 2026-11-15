'use strict';
let nativeScan=null;
let nativeReview=null;
let nativeSaved=[];
let nativeBusy=false;
function nativeAppSettings(key){
 const app=state.config.integrations[key],name=state.catalog[key].name;
 return '<details class="settings-app" '+(state.focusIntegration===key?'open':'')+'><summary><strong>'+escape(name)+'</strong><span class="pill">Imported · read-only</span></summary><p>Stackarr reads this app’s status. Its settings and startup stay in the original Windows installation.</p><p>'+appLink(browserAppUrl(key))+'</p><p class="hint">Use Find native app settings above to review and refresh the imported snapshot. API keys are stored privately.</p></details>';
}
async function loadNativeImports(){
 nativeSaved=(await api('native-imports')).apps;
}
function nativeSnapshot(snapshot){
 const list=(title,rows,describe)=>rows.length?'<details><summary>'+escape(title)+' · '+rows.length+'</summary><ul>'+rows.map(row=>'<li>'+describe(row)+'</li>').join('')+'</ul></details>':'';
 return '<p class="hint">'+escape(snapshot.browser_address)+' · '+escape(snapshot.version)+'</p>'+
  list('Library folders',snapshot.root_folders,row=>escape(row.path))+
  list('Quality profiles',snapshot.quality_profiles,row=>escape(row.name)+'<br><span class="hint">Allowed: '+(row.qualities.filter(q=>q.allowed).map(q=>escape(q.name)).join(', ')||'none')+'</span>')+
  list('Download clients',snapshot.download_clients,row=>escape(row.name)+' · '+(row.enabled?'enabled':'disabled'))+
  list('Sources',snapshot.sources,row=>escape(row.name)+' · '+(row.enabled?'enabled':'disabled'))+
  list('Linked apps',snapshot.linked_apps,row=>escape(row.name)+' · '+escape(row.sync_level));
}
function nativeImportPanel(){
 const available=setupDeployment.host_checks||setupDeployment.controller==='connected';
 if(!available&&!nativeSaved.length)return '';
 let html='<section class="panel" id="native-import-panel"><h2>Keep your existing Windows apps</h2><p>Import native Sonarr, Radarr, Prowlarr and signed-in Plex without copying private keys. Stackarr keeps their current settings and connects in read-only mode.</p>';
 if(available)html+='<button id="native-scan" '+(nativeBusy?'disabled':'')+'>Find native app settings</button>';
 if(nativeScan){
  html+='<div class="cards">'+nativeScan.apps.map(row=>{
   const name=escape(state.catalog[row.app].name);
   const configured=state.config.integrations[row.app];
   const different=configured.enabled&&!configured.read_only;
   return '<article class="card"><h3>'+name+'</h3>'+(row.state==='verified'?'<p>Native settings verified</p>'+nativeSnapshot(row.snapshot)+(different?'<p>A different connection is already saved. It will be preserved.</p>':'<button data-native-review="'+row.app+'" '+(nativeBusy?'disabled':'')+'>Review '+name+' import</button>'):'<p>'+escape(row.detail)+'</p>')+'</article>';
  }).join('')+'</div>';
 }
 if(nativeReview)html+='<section class="banner" role="region" aria-label="Review native import"><h3>Import '+escape(state.catalog[nativeReview.snapshot.app].name)+'?</h3>'+nativeSnapshot(nativeReview.snapshot)+'<p>'+escape(nativeReview.notice)+'</p><p>No default quality is chosen automatically. Existing profiles may contain qualities you do not want.</p><div class="actions"><button class="primary" id="native-apply" '+(nativeBusy?'disabled':'')+'>Import connection and settings</button><button id="native-cancel" '+(nativeBusy?'disabled':'')+'>Cancel</button></div></section>';
 if(nativeSaved.length)html+='<details><summary>Imported settings · '+nativeSaved.length+' apps</summary>'+nativeSaved.map(row=>'<article><h3>'+escape(state.catalog[row.app].name)+' · read-only</h3>'+nativeSnapshot(row)+'</article>').join('')+'<p class="hint">These are snapshots from import time. Scan and review again to refresh them. App status is collected separately.</p></details>';
 return html+'<p class="hint">This connects to the original Windows app. It does not transfer its database into Docker. Native Plex must already be signed in. qBittorrent login needs its own setup.</p></section>';
}
function bindNativeImports(){
 const action=(selector,fn)=>document.querySelectorAll(selector).forEach(button=>button.onclick=async()=>{
  if(nativeBusy)return;
  if(state.dirty&&!confirm('Discard unsaved form changes before importing native settings?'))return;
  nativeBusy=true;button.disabled=true;
  try{await fn(button);state.error='';}
  catch(error){state.error=error.message;}
  finally{nativeBusy=false;render();document.querySelector('#native-import-panel')?.scrollIntoView({block:'start'});}
 });
 action('#native-scan',async()=>{nativeReview=null;nativeScan=await api('native-imports/scan','POST',{});});
 action('[data-native-review]',async button=>{nativeReview=await api('native-imports/review','POST',{app:button.dataset.nativeReview});});
 action('#native-apply',async()=>{
  const token=nativeReview?.review_token;
  nativeReview=null;
  if(!token)throw new Error('Review this import again.');
  const result=await api('native-imports/apply','POST',{review_token:token});
  await load();
  state.notice=state.catalog[result.app].name+' imported. Its existing settings and startup are preserved. Stackarr access is read-only.';
 });
 action('#native-cancel',async()=>{nativeReview=null;});
}
