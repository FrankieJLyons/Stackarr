'use strict';
let setupSuggestedFolder=null;
let setupFolderProblem='';
let setupPortNotice='';
async function loadSetupFolderChoice(){
 setupSuggestedFolder=null;setupFolderProblem='';
 if(setupDraft.draft.step!==1||!setupDraft.draft.apps.some(k=>['plex','sonarr','radarr','qbittorrent'].includes(k)&&setupDraft.draft.choices?.[k]?.mode!=='connect')||!setupDeployment.folder_browser)return;
 try{
  const roots=await api('onboarding/folders');
  if(roots.roots?.length===1){const folder=await api('onboarding/folders?root='+roots.roots[0].id);if(!setupDraft.draft.data_root||setupDraft.draft.data_root===folder.host_path)setupSuggestedFolder=folder;}
 }catch{setupFolderProblem='The previously shared folder is unavailable. Choose another folder; existing app folders stay unchanged.';}
}
function setupFolderLabel(path){
 if(!path)return 'Choose your media folder';
 const trimmed=path.replace(/[\\/]+$/,'');
 if(!trimmed)return 'Root folder';
 if(/^[A-Za-z]:$/.test(trimmed))return trimmed+' drive';
 return trimmed.split(/[\\/]/).pop();
}
function setupFolderPathDetails(path,summary,id=''){
 return '<details class="setup-folder-details"'+(id?' id="'+escape(id)+'-details"':'')+(path?'':' hidden')+'><summary>'+escape(summary)+'</summary><p class="setup-library-path"'+(id?' id="'+escape(id)+'"':'')+'>'+escape(path)+'</p></details>';
}
function updateSetupFolderDisplay(path){
 const label=document.getElementById('setup-selected-folder'),exact=document.getElementById('setup-selected-folder-path'),details=document.getElementById('setup-selected-folder-path-details');
 if(label)label.textContent=setupFolderLabel(path);
 if(exact)exact.textContent=path;
 if(details)details.hidden=!path;
}
function setupMediaFolder(d){
 const path=d.data_root||setupSuggestedFolder?.host_path||'';
 return '<section class="panel" id="setup-storage"><h2>Where will your media live?</h2><p>One folder for your movies, TV and downloads. New apps use matching subfolders; existing files stay in place.</p><p><strong id="setup-selected-folder">'+escape(setupFolderLabel(path))+'</strong></p>'+setupFolderPathDetails(path,'See folder location','setup-selected-folder-path')+'<input type="hidden" id="setup-folder" value="'+escape(path)+'">'+(path?'<p class="hint">Continue to use this folder, or choose another.</p>':'')+(setupFolderProblem?'<p role="alert">'+escape(setupFolderProblem)+'</p>':'')+(setupDeployment.folder_picker||setupDeployment.folder_browser?'<button id="setup-choose-folder">'+(path?'Choose another folder…':'Choose a folder…')+'</button>':'<p>Open Stackarr on the installation computer to choose a folder.</p>')+(setupDeployment.folder_browser?'<details><summary>Choose a subfolder in shared storage</summary><button id="setup-browse-shared">Browse shared folders</button></details>':'')+'<div id="setup-folder-browser"></div><p id="setup-host-result" role="status"></p></section>';
}
const setupQualityLabels={'HD-1080p':'1080p','Ultra-HD':'4K / UHD','SD':'SD','HD-720p':'720p'};
function setupLibraryChoices(d){
 const installed=key=>d.apps.includes(key)&&d.choices?.[key]?.mode!=='connect';
 const libraries=[['radarr','Movies','media/movies'],['sonarr','TV','media/tv']].filter(([key])=>installed(key)||installed('plex'));
 if(!libraries.length)return '';
 return '<section class="panel"><h2>Movies & TV</h2><p>Keep one Movies folder and one TV folder. Quality choices do not split or move your files.</p>'+libraries.map(([key,name,path])=>{
  const base=d.data_root||setupSuggestedFolder?.host_path||'';
  const separator=/^[A-Za-z]:|^\\\\/.test(base)?'\\':'/';
  const folder=setupStorage?.folders?.find(row=>row.app==='/data/'+path)?.host||(base?base.replace(/[\\/]+$/,'')+separator+path.replaceAll('/',separator):'');
  const profile=d.choices?.[key]?.quality_profile||'HD-1080p';
  const primary=['SD','HD-720p'].includes(profile)?'other':profile;
  return '<article class="panel"><h3>'+name+'</h3><p>'+(folder?'Saved in your '+escape(name)+' folder.':'Choose a media folder above to see this location.')+'</p>'+setupFolderPathDetails(folder,'See '+name+' folder location')+(installed(key)?select(name+' request quality','setup-quality-'+key,primary,[['HD-1080p','1080p (recommended)'],['Ultra-HD','4K / UHD'],['other','Other']])+'<div id="setup-quality-other-wrap-'+key+'" '+(primary==='other'?'':'hidden')+'>'+select(name+' other quality','setup-quality-other-'+key,primary==='other'?profile:'SD',[['SD','SD · smaller files'],['HD-720p','720p · HD']])+'</div>':'<p class="hint">Plex plays the media in this folder. Add '+(key==='radarr'?'Radarr':'Sonarr')+' to choose quality for new requests.</p>')+'</article>';
 }).join('')+'<p class="hint">Seerr uses these profiles for new requests after you review its app connections. When adding directly in Sonarr or Radarr, choose the same profile there. 4K needs more storage and compatible playback.</p></section>';
}
function setupQualitySummary(d){
 const rows=['radarr','sonarr'].filter(key=>d.apps.includes(key)&&d.choices?.[key]?.mode!=='connect'&&d.choices?.[key]?.quality_profile);
 return rows.length?'<p>Request quality: '+rows.map(key=>(key==='radarr'?'Movies':'TV')+' · '+escape(setupQualityLabels[d.choices[key].quality_profile])).join(' · ')+'</p>':'';
}
function setupInstallQualitySummary(review){
 return review.quality_setup?.length?'<p>Request quality: '+review.quality_setup.map(row=>(row.app==='radarr'?'Movies':'TV')+' · '+escape(row.quality)+' ('+escape(row.profile)+')').join(' · ')+'. Used when you connect Seerr.</p>':'';
}
function setupPorts(d){
 const mode=d.port_mode||'automatic',current=Number(location.port||(location.protocol==='https:'?443:80));
 return '<section class="panel" id="setup-ports-panel"><h2>App addresses</h2><p>Stackarr can choose available ports for new apps. Existing apps keep their addresses.</p>'+check('Choose available ports for me (recommended)','setup-auto-ports',mode==='automatic')+'<details id="setup-ports-advanced" '+(mode!=='automatic'?'open':'')+'><summary>Advanced port settings</summary>'+select('Port selection','setup-port-mode',mode,[['automatic','Choose available ports'],['defaults','App defaults'],['sequential','Stackarr sequence · 28000–28009'],['custom','Choose my own ports']])+'<div class="table-scroll"><table class="setup-port-table"><caption>Stackarr and the new apps you have selected</caption><thead><tr><th scope="col">App</th><th scope="col">Web port</th></tr></thead><tbody><tr class="stackarr-port-row"><th scope="row">Stackarr <small>This dashboard</small></th><td><span class="port-number">'+current+'</span></td></tr>'+setupPortOrder.map((key,index)=>{
  const port=d.choices?.[key]?.port||(mode==='sequential'?setupBasePort+1+index:state.catalog[key].port);
  return `<tr id="setup-port-row-${key}" ${d.apps.includes(key)&&d.choices?.[key]?.mode!=='connect'?'':'hidden'}><th scope="row">${escape(state.catalog[key].name)}</th><td><span id="setup-port-label-${key}" class="port-number" ${mode==='custom'?'hidden':''}>${port}</span><input id="setup-port-${key}" aria-label="${escape(state.catalog[key].name)} port" type="number" min="1" max="65535" value="${port}" ${mode==='custom'?'':'hidden'}></td></tr>`;
 }).join('')+'</tbody></table></div>'+(setupDeployment.available?'<button id="setup-check-ports">Check for conflicts</button>':'')+'<p id="setup-port-status" role="status">'+(setupDeployment.available?'Ports are checked again when you review and approve installation.':'Port checks need a connection to the installation computer.')+'</p></details></section>';
}
function setupPortRecovery(){
 const conflicts=(setupPortResults||[]).filter(row=>row.status!=='available');
 if(!conflicts.length&&!setupPortNotice)return '';
 return '<section class="panel" role="status"><h2>'+(conflicts.length?'Choose free ports':'App addresses ready')+'</h2>'+(conflicts.length?'<p>Another app or Windows is using these ports. Stackarr leaves it running and can choose alternatives.</p><ul>'+conflicts.map(row=>'<li>'+escape(row.name)+' · '+row.port+' · '+escape({duplicate:'selected more than once',reserved:'reserved for Stackarr',unavailable:'in use or unavailable'}[row.status]||row.status)+'</li>').join('')+'</ul><button id="setup-fix-ports" class="primary">Use available ports</button>':'<p>'+escape(setupPortNotice)+'</p>')+'</section>';
}
function installPortRecoveryButtons(op){
 if(!setupDeployment.available||!['failed','interrupted'].includes(op.state)||!(op.diagnostic==='startup-port-conflict'||op.phase==='starting'||op.port_recovery))return '';
 return `<button data-install-port-review="${escape(op.id)}">Review available ports</button>`;
}
function installPortRecoveryPanel(){
 const review=setupInstallPortsReview;if(!review)return '';
 return '<section class="panel" role="status"><h2>Review new app addresses</h2><p>'+escape(review.notice)+'</p><ul>'+review.changes.map(row=>'<li>'+escape(row.name)+' · '+row.previous+' → '+row.port+'</li>').join('')+'</ul><button id="setup-install-ports-apply" class="primary">Apply new ports & resume</button></section>';
}
async function chooseSetupPorts(){
 const result=await api('onboarding/suggest-ports','POST',{}),draft=structuredClone(setupDraft.draft);
 const changed=result.suggestions.filter(row=>row.port!==row.previous);
 for(const row of result.suggestions){draft.choices[row.app]={...draft.choices[row.app],port:row.port};const input=document.getElementById('setup-port-'+row.app),label=document.getElementById('setup-port-label-'+row.app);if(input)input.value=row.port;if(label)label.textContent=row.port;}
 if(draft.port_mode!=='automatic')draft.port_mode='custom';
 const mode=document.getElementById('setup-port-mode');if(mode)mode.value=draft.port_mode;
 setupDraft=await api('onboarding','PUT',{revision:setupDraft.revision,draft});
 setupPortResults=null;setupInstallReview=null;
 setupPortNotice=changed.length?changed.map(row=>row.name+': '+row.previous+' → '+row.port).join(' · ')+'. Review these addresses before installing.':'Available ports selected. You do not need to enter port numbers.';
}
