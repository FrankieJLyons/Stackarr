'use strict';
let presetState={catalog:null,app:'sonarr',busy:false,error:''};
function clearPresets(){presetState={catalog:null,app:'sonarr',busy:false,error:''};}
function presetBlocker(key){
 const app=state.config.integrations[key];
 if(!app?.enabled)return 'Connect '+(state.catalog[key]?.name||key)+' first.';
 if(app.read_only)return 'This connection is read-only. Settings can be reviewed in the app.';
 if(!state.credentials.includes(key))return 'Save the app credentials in App connections first.';
 return '';
}
function recommendedSettingsPanel(){
 const p=presetState,c=p.catalog,block=presetBlocker(p.app);
 return `<section class="panel" id="recommended-settings"><div class="section-head"><div><p class="eyebrow">START HERE</p><h2>Recommended app settings</h2></div><span class="pill">${c?'Recipe '+escape(c.version):'Local recipes'}</span></div><p>Pick a starting point, preview the exact changes, then apply. Your existing settings stay in place until you confirm a preview.</p>
 <label for="preset-app">Choose a library app</label><select id="preset-app" data-setup-control="navigation" ${p.busy?'disabled':''}><option value="sonarr" ${p.app==='sonarr'?'selected':''}>TV shows · Sonarr</option><option value="radarr" ${p.app==='radarr'?'selected':''}>Movies · Radarr</option></select>
 ${block?'<p class="banner">'+escape(block)+' <button data-preset-connect="'+p.app+'">App connections</button></p>':''}
 ${p.error?'<p class="banner error" role="alert">'+escape(p.error)+'</p>':''}
 ${!c?'<p>Load the versioned recipes to choose a profile.</p><button id="presets-load">Load recommended profiles</button>':`<div class="preset-grid">${c.presets.map(row=>`<article class="preset-card ${row.recommended?'preset-recommended':''}">${row.recommended?'<span class="pill good">Recommended starting point</span>':'<span class="pill">Optional</span>'}<h3>${escape(row.name)}</h3><p>${escape(row.description)}</p><p class="hint">Automatic upgrades off · ${escape(row.tier)} only</p><button data-quality-preset="${escape(row.id)}" ${block||p.busy?'disabled':''}>Preview for ${p.app==='sonarr'?'Sonarr':'Radarr'}</button></article>`).join('')}</div><div class="actions"><button data-quality-load="${p.app}" ${block?'disabled':''}>Current rules & restore</button></div><p class="hint">${escape(c.scope)}</p><details><summary>What changes, and what stays yours?</summary><ul>${c.tradeoffs.map(row=>'<li>'+escape(row)+'</li>').join('')}</ul><p>These are Stackarr starting points, not full TRaSH Guide profiles or an automatic guide-sync service. Resolution alone does not guarantee picture quality or a small file. Anime, language preferences and HDR playback may need custom rules.</p><p>Sources: ${c.sources.map(row=>'<a href="'+escape(row.url)+'" target="_blank" rel="noopener noreferrer">'+escape(row.label)+'</a>').join(' · ')}</p></details>`}
 </section>${qualityState.data?qualityRulesPanel():''}${typeof cleanupPresetsPanel==='function'?cleanupPresetsPanel():''}<section class="panel"><h2>Finish the rest of your stack</h2><p>Apply supported safeguards here, or open the relevant setup tool. Settings marked “In the app” are guidance; Stackarr does not apply them automatically.</p>
 <div class="preset-followups"><article><h3>qBittorrent · Media download safeguards</h3><p>Keep your filename exclusions, skip scripts and executables, optionally skip archives, and disable automatic external programs. Review and undo are available.</p><button data-preset-tool="protection" ${presetBlocker('qbittorrent')?'disabled':''}>Preview safeguards</button>${presetBlocker('qbittorrent')?'<p class="hint">'+escape(presetBlocker('qbittorrent'))+'</p>':''}<p class="hint">Seeding targets, speed limits, network interfaces and authentication stay yours.</p></article>
 <article><h3>Downloads → TV & movies → Plex</h3><p>Check the shared folders and review completed imports against an existing Plex library. This does not move existing media.</p><button data-preset-media>Review library connections</button></article>
 </div><details><summary>Settings to review in your other apps</summary><div class="preset-followups">${recommendedManualSettings()}</div></details></section>`;
}
function recommendedManualSettings(){
 const rows=[
 ['prowlarr','Preserve per-app source choices','Use Add and Remove Only when you want Sonarr and Radarr to retain their own indexer settings. Full Sync deliberately replaces settings for Prowlarr-managed indexers.','Settings → Apps → Sync Level','https://wiki.servarr.com/prowlarr/settings'],
 ['plex','Keep unavailable library entries','Consider turning automatic emptying of library trash off, especially with removable or network storage. Leave expensive preview-thumbnail generation off until you need it.','Settings → Library','https://support.plex.tv/articles/200289526-library/'],
 ['seerr','Start with requests needing approval','Give new users Request permission; choose limits for your storage and connection. Grant Auto Approve and 4K access deliberately. Direct Seerr requests use the profiles chosen in Seerr.','Settings → Users; Settings → Services','https://docs.seerr.dev/using-seerr/settings/users/'],
 ['tautulli','Statistics without playback actions','Connect Plex for viewing statistics first. Add notifications and scripts only when you need them.','Review Plex connection and notifications',''],
 ['kuma','Monitor the apps you actually use','Add local availability monitors and test a notification. Choose an interval that suits the server; a login page responding does not prove downloads work.','Review monitors and notification settings','']
 ];
 return rows.map(([key,title,text,path,source])=>`<article><span class="pill">In the app</span><h3>${escape(state.catalog[key]?.name||key)} · ${escape(title)}</h3><p>${escape(text)}</p><p class="hint">${escape(path)}</p><div class="actions">${state.config.integrations[key]?.enabled?appLink(browserAppUrl(key)):'<button data-preset-connect="'+key+'">Connect app</button>'}${source?'<a href="'+escape(source)+'" target="_blank" rel="noopener noreferrer">Official guidance ↗</a>':''}</div></article>`).join('');
}
function bindPresets(){
 const p=presetState;
 const refresh=()=>{if(p===presetState)render();};
 const action=(selector,fn)=>document.querySelectorAll(selector).forEach(button=>button.onclick=async()=>{
  if(p.busy)return;
  if(state.dirty){p.error='Save your connection changes before previewing a preset.';refresh();return;}
  p.busy=true;button.disabled=true;p.error='';document.getElementById('preset-app')?.setAttribute('disabled','');
  try{await fn(button);}catch(error){p.error=error.message;}finally{p.busy=false;refresh();document.querySelector('#quality-rules')?.scrollIntoView({block:'start'});}
 });
 action('#presets-load',async()=>{p.catalog=await api('quality-presets');});
 action('[data-quality-preset]',async button=>{
  const recipe=p.catalog?.presets.find(row=>row.id===button.dataset.qualityPreset);
  if(!recipe)throw new Error('Reload the recommended profiles.');
  qualityState.review=null;
  const data=await api('quality-rules/'+p.app);
  const policy=structuredClone(recipe.policy);
  const review=await api('quality-rules/review','POST',{app:p.app,revision:data.revision,policy,scope:'future'});
  qualityState={app:p.app,data,draft:policy,matches:[],query:'',preset:recipe.name,review,result:null,busy:false,error:''};
 });
 const app=document.getElementById('preset-app');if(app)app.onchange=()=>{p.app=app.value;qualityState.review=null;clearQualityRules();refresh();};
 document.querySelectorAll('[data-preset-connect]').forEach(button=>button.onclick=()=>{if(leaveScreen())openConnectionSettings(button.dataset.presetConnect);});
 document.querySelectorAll('[data-preset-media]').forEach(button=>button.onclick=()=>{if(!leaveScreen())return;state.settingsSection='media';render();document.querySelector('#media-setup')?.scrollIntoView({block:'start'});});
 document.querySelectorAll('[data-preset-tool]').forEach(button=>button.onclick=()=>{if(!leaveScreen())return;state.settingsSection='media';render();document.getElementById('protection-review')?.click();document.querySelector('#media-setup')?.scrollIntoView({block:'start'});});
}
