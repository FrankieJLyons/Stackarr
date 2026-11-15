'use strict';
const cleanupRecipeNames={observe:'Observe first',media:'Media safeguards',recover:'Recover stuck downloads',completed:'Clean completed downloads'};
function cleanupSettingLabel(key){
 const names={dryRun:'Simulate changes (dry-run)',enabled:'Scheduled checks enabled',cronExpression:'Schedule',useAdvancedScheduling:'Custom schedule enabled',processNoContentId:'Include downloads without a library ID',downloadingMetadataMaxStrikes:'Metadata-timeout removal threshold','failedImport.maxStrikes':'Failed-import checks before action','failedImport.ignorePrivate':'Skip private torrents on failed import','failedImport.deletePrivate':'Delete private torrents on failed import','failedImport.skipIfNotFoundInClient':'Skip downloads missing from the client','failedImport.forceImport':'Force blocked imports','failedImport.patternMode':'Failed-import filter mode','errored.maxStrikes':'Error checks before action','errored.ignorePrivate':'Skip private errored torrents','errored.deletePrivate':'Delete private errored torrents',connectivityCheckEnabled:'Check for internet outages',connectivityCheckUrls:'Outage-check addresses',searchEnabled:'Replacement searches',proactiveSearchEnabled:'Search for missing media',excluded_file_names_enabled:'Filename exclusions enabled',excluded_file_names:'Filename exclusion list',autorun_enabled:'Run a program after download',autorun_on_torrent_added_enabled:'Run a program when a torrent is added'};
 return names[key]||key.replaceAll('.',' · ').replaceAll('_',' ').replace(/([a-z])([A-Z])/g,'$1 $2').replace(/^./,c=>c.toUpperCase());
}
function cleanupSectionLabel(key){return {general:'Operating mode',queue_cleaner:'Queue checks',download_cleaner:'Completed downloads',stall:'Stalled-download rule',seed:'Completed-download rule',qbit:'Filename safeguards',blacklist_sync:'Exclusion-list sync',malware_blocker:'Cleanuparr file filtering',seeker:'Replacement searches'}[key]||key;}
let cleanupState;
function clearCleanupPresets(){cleanupState={data:null,preset:'observe',archives:true,url:'',category:'',ratio:2,hours:72,files:false,review:null,result:null,busy:false,error:''};}
clearCleanupPresets();
function cleanupPresetsPanel(){
 const c=cleanupState,block=presetBlocker('cleanuparr'),d=c.data,r=c.review;
 let html=`<section class="panel" id="cleanup-presets"><div class="section-head"><div><p class="eyebrow">TORRENTS & MEDIA</p><h2>Cleanuparr presets</h2></div>${d?'<span class="pill">'+escape(d.dry_run?'Dry-run enabled':'Live mode · review carefully')+'</span>':''}</div><p>Start with Observe first, inspect the results in Cleanuparr, then choose whether to enable live cleanup. Applying a preset always puts Cleanuparr into dry-run.</p>`;
 if(block)html+='<p class="banner">'+escape(block)+' <button data-preset-connect="cleanuparr">App connections</button></p>';
 if(c.error)html+='<p class="banner error" role="alert">'+escape(c.error)+'</p>';
 html+=`<div class="actions"><button id="cleanup-check" ${block||c.busy?'disabled':''}>${d?'Check settings again':'Check Cleanuparr'}</button>${state.config.integrations.cleanuparr?.enabled?appLink(browserAppUrl('cleanuparr')):''}</div>`;
 if(!d)return html+'</section>';
 html+=`<p class="hint">Cleanuparr ${escape(d.version)} · Recipe ${escape(d.recipe_version)}</p><label for="cleanup-recipe">Choose a preset</label><select id="cleanup-recipe" data-setup-control="navigation" ${c.busy?'disabled':''}>${d.presets.map(row=>'<option value="'+escape(row.id)+'" '+(c.preset===row.id?'selected':'')+'>'+escape(row.name)+(row.recommended?' · recommended default':'')+'</option>').join('')}</select><p>${escape(d.presets.find(row=>row.id===c.preset)?.description||'')}</p>`;
 if(c.preset==='observe')html+='<p class="hint">Checks run every 15 minutes in dry-run. Failed imports and client errors use six checks; existing stall/slow rule definitions stay in place. Other jobs are paused. Observe first cannot enable live deletion.</p>';
 if(c.preset==='media')html+=`<label><input type="checkbox" id="cleanup-archives" data-setup-control="navigation" ${c.archives?'checked':''}> Also exclude archives and disk images</label><p class="hint">qBittorrent enforces these exclusions for new torrents immediately after apply. Its external program hooks are disabled. Cleanuparr jobs stay paused. Filename filtering is not antivirus.</p>`;
 if(c.preset==='recover'&&d.recovery_blocker)html+='<p class="banner">'+escape(d.recovery_blocker)+'</p>';
 if(c.preset==='recover')html+=`<label for="cleanup-url">HTTPS internet-check URL</label><input id="cleanup-url" type="url" data-setup-control="navigation" maxlength="1000" value="${escape(c.url)}" placeholder="Use an address you trust"><p class="hint">Cleanuparr contacts this address to check for an outage. Leave blank to retain its existing check addresses. Recovery needs a check address, a matching library connection, and no other active stall/slow rules.</p><p>Every 15 minutes: six failed-import/error checks; twelve stalled-download checks with progress resets, for public torrents up to 95% complete. Slow-only and metadata-timeout removal stay off. Replacement searches and other cleanup jobs stay off.</p>`;
 if(c.preset==='completed'){
  const choices=d.imported_categories;
  html+=choices.length?`<label for="cleanup-category">Verified post-import category</label><select id="cleanup-category" data-setup-control="navigation"><option value="">Choose a category</option>${choices.map((row,index)=>'<option value="'+index+'" '+(String(index)===c.category?'selected':'')+'>'+escape(row.category)+' · '+escape(row.app)+'</option>').join('')}</select><div class="form-grid"><div><label for="cleanup-ratio">Minimum completed ratio</label><input id="cleanup-ratio" data-setup-control="navigation" type="number" min="1" max="1000" step="0.1" value="${c.ratio}"></div><div><label for="cleanup-hours">Minimum seeding hours</label><input id="cleanup-hours" data-setup-control="navigation" type="number" min="1" max="87600" value="${c.hours}"></div></div><label><input id="cleanup-files" data-setup-control="navigation" type="checkbox" ${c.files?'checked':''}> Also delete source download files when live cleanup is enabled</label><p class="hint">Files are kept by default. Both ratio and minimum time must be met; no maximum-time override. These starting values are editable. Only public torrents in the verified category are eligible. No orphan, unlinked or dead-torrent cleanup is enabled.</p>`:'<p class="banner">'+escape(d.completed_blocker)+'</p><p class="hint">In Sonarr/Radarr: Settings → Download Clients → qBittorrent → Show Advanced → Post-Import Category. Choose a separate category and create it in qBittorrent, then check again.</p>';
 }
 html+=`<div class="actions"><button id="cleanup-preview" ${block||c.busy||(c.preset==='recover'&&d.recovery_blocker)||(c.preset==='completed'&&(!d.imported_categories.length||c.category===''))?'disabled':''}>Preview preset</button></div><p class="hint">${escape(d.notice)}</p>`;
 if(r){
  html+=`<section class="banner" aria-label="Cleanuparr preset preview"><h3>${r.kind==='live'?'Confirm live cleanup':r.kind==='restore'?'Restore settings in dry-run':'Review '+escape(cleanupRecipeNames[r.preset])}</h3><p>${r.kind==='live'?escape(r.live_warning):'Cleanuparr will remain in app-wide dry-run. No immediate cleanup job is started.'}</p>${r.media_notice?'<p>'+escape(r.media_notice)+'</p>':''}<ul>${(r.scope||[]).map(item=>'<li>'+escape(item)+'</li>').join('')}</ul><div class="quality-table"><table><thead><tr><th>App / section</th><th>Change</th></tr></thead><tbody>${r.changes.map(row=>'<tr><td>'+escape(row.app==='qbittorrent'?'qBittorrent':'Cleanuparr')+' · '+escape(cleanupSectionLabel(row.section))+'</td><td>'+escape(row.action)+'<ul>'+row.settings.map(s=>'<li>'+escape(cleanupSettingLabel(s.setting))+': '+escape(s.before)+' → '+escape(s.after)+'</li>').join('')+'</ul></td></tr>').join('')}</tbody></table></div>`;
  if(r.kind==='live')html+='<label><input id="cleanup-live-ack" type="checkbox" data-setup-control="navigation"> I understand that live cleanup may permanently delete existing eligible downloads or files, and restoring settings cannot recover them.</label><label for="cleanup-live-text">Type ENABLE LIVE DELETION to confirm</label><input id="cleanup-live-text" data-setup-control="navigation" autocomplete="off" spellcheck="false"><p class="hint">This enables the reviewed scheduled job; it can affect eligible downloads already in the client. No private-torrent deletion or replacement search is enabled by these recipes.</p>';
  html+=`<div class="actions"><button class="primary" id="cleanup-apply" ${r.kind==='live'?'disabled':''}>${r.kind==='live'?'Enable live cleanup':r.kind==='restore'?'Restore in dry-run':'Apply in dry-run'}</button><button id="cleanup-cancel">Cancel preview</button></div></section>`;
 }
 if(c.result)html+='<p class="banner" role="status">'+escape(c.result.message)+'</p>';
 if(d.history.length)html+='<details><summary>Saved Cleanuparr changes & recovery</summary>'+d.history.map(row=>'<div class="cleanup-history"><p>'+escape(cleanupRecipeNames[row.preset]||row.preset)+' · '+escape(row.kind)+' · '+escape(row.state)+' · '+escape(new Date(row.created*1000).toLocaleString())+'</p><div class="actions"><button data-cleanup-restore="'+escape(row.id)+'">Preview restore in dry-run</button>'+(row.kind==='preset'&&row.state==='applied'&&['recover','completed'].includes(row.preset)?'<button data-cleanup-live="'+escape(row.id)+'">Review live cleanup…</button>':'')+'</div></div>').join('')+'</details>';
 return html+'</section>';
}
function bindCleanupPresets(){
 const c=cleanupState;
 const refresh=()=>{if(c!==cleanupState)return;render();document.querySelector('#cleanup-presets')?.scrollIntoView({block:'start'});};
 const action=(selector,fn)=>document.querySelectorAll(selector).forEach(button=>button.onclick=async()=>{
  if(c.busy)return;if(state.dirty){c.error='Save your connection changes first.';refresh();return;}
  c.busy=true;button.disabled=true;c.error='';document.getElementById('cleanup-recipe')?.setAttribute('disabled','');
  try{await fn(button);}catch(error){c.error=error.message;}finally{c.busy=false;refresh();}
 });
 const load=async()=>{c.data=await api('cleanuparr-presets');if(c.category!==''&&!c.data.imported_categories[Number(c.category)])c.category='';};
 const cancel=()=>{c.review=null;c.result=null;document.getElementById('cleanup-apply')?.setAttribute('disabled','');};
 action('#cleanup-check',async()=>{cancel();await load();});
 const recipe=document.getElementById('cleanup-recipe');if(recipe)recipe.onchange=()=>{if(c.busy)return;c.preset=recipe.value;cancel();refresh();};
 for(const [id,key,type] of [['cleanup-archives','archives','checked'],['cleanup-url','url','value'],['cleanup-category','category','value'],['cleanup-ratio','ratio','number'],['cleanup-hours','hours','number'],['cleanup-files','files','checked']]){
  const el=document.getElementById(id);if(el)el.oninput=()=>{if(c.busy)return;c[key]=type==='number'?Number(el.value):el[type];cancel();if(id==='cleanup-category')refresh();};
 }
 action('#cleanup-preview',async()=>{cancel();const selected=c.data.imported_categories[Number(c.category)];c.review=await api('cleanuparr-presets/review','POST',{preset:c.preset,block_archives:c.archives,connectivity_url:c.url,client_id:c.preset==='completed'?selected?.client_id||'':'',category:c.preset==='completed'?selected?.category||'':'',ratio:c.ratio,seed_hours:c.hours,delete_source_files:c.files});});
 action('#cleanup-cancel',async()=>{cancel();});
 action('[data-cleanup-live]',async button=>{cancel();c.review=await api('cleanuparr-presets/live/review','POST',{run_id:button.dataset.cleanupLive});});
 action('[data-cleanup-restore]',async button=>{cancel();c.review=await api('cleanuparr-presets/restore/review','POST',{run_id:button.dataset.cleanupRestore});});
 for(const id of ['cleanup-live-ack','cleanup-live-text']){const el=document.getElementById(id);if(el)el.oninput=()=>{document.getElementById('cleanup-apply').disabled=!document.getElementById('cleanup-live-ack').checked||document.getElementById('cleanup-live-text').value!=='ENABLE LIVE DELETION';};}
 action('#cleanup-apply',async()=>{
  const r=c.review;if(!r)throw new Error('Preview this action again.');
  const body={review_token:r.review_token};
  if(r.kind==='live'){
   if(!document.getElementById('cleanup-live-ack')?.checked||document.getElementById('cleanup-live-text')?.value!=='ENABLE LIVE DELETION')throw new Error('Confirm the live-deletion warning and type the exact confirmation.');
   Object.assign(body,{confirmation:'ENABLE LIVE DELETION',acknowledge_irreversible:true});
  }
  c.review=null;c.result=await api('cleanuparr-presets/'+(r.kind==='live'?'live/':'')+'apply','POST',body);await load();
 });
}
