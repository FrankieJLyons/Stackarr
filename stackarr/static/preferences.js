'use strict';
const overviewWidgets=[['downloads','Active downloads'],['streams','Plex activity'],['sonarr-queue','Sonarr queue'],['radarr-queue','Radarr queue'],['blocklist','Blocked releases'],['sources','Content sources'],['storage','Media storage'],['apps','Connected apps'],['queue','Combined queue'],['health','App health notices'],['requests','Requests'],['monitors','Availability monitors']];
const defaultWidgets=['downloads','streams','sonarr-queue','radarr-queue','blocklist','sources','storage','apps'];
function applyAppearance(){
 const prefs=state.config?.dashboard||state.publicAppearance||{appearance:'dark',accent:'blue'};
 document.documentElement.dataset.accent=prefs.accent||'blue';const icon=document.querySelector('link[rel=icon]');if(icon)icon.href='/api/appearance/icon.svg';
 document.documentElement.dataset.theme=prefs.appearance==='system'?(matchMedia('(prefers-color-scheme:light)').matches?'light':'dark'):(prefs.appearance||'dark');
}
function appRole(key){return {plex:'Media player',seerr:'Requests',sonarr:'TV library',radarr:'Movie library',prowlarr:'Content sources',qbittorrent:'Download client',cleanuparr:'Download cleanup',tautulli:'Viewing statistics',kuma:'Availability monitoring'}[key]||'Integration';}
function brandMark(){return '<svg class="brand-mark" viewBox="0 0 48 48" aria-hidden="true"><rect width="48" height="48" rx="14"/><path d="m12 16 12-6 12 6-12 6zm0 8 12 6 12-6m-24 8 12 6 12-6"/></svg>';}
function eyeIcon(visible=false){return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>'+(visible?'<path d="m3 3 18 18"/>':'')+'</svg>';}
function settingsScreen(){
 const c=state.config,section=state.settingsSection||'appearance';
 let body=heading('Settings','Choose how Stackarr looks and connects to your apps.');
 const nativeMarkup=section==='connections'?nativeImportPanel():'';
 body+='<nav class="settings-tabs" aria-label="Settings sections">'+[['appearance','Appearance'],['recommended','Recommended settings'],['connections','App connections'],['media','Media & quality'],['maintenance','Maintenance'],['access','Access']].map(([id,label])=>`<button data-settings-section="${id}" ${id===section?'aria-current="page"':''}>${label}</button>`).join('')+'</nav>';
 if(section==='recommended')body+=recommendedSettingsPanel();
 if(section==='appearance')body+=`<section class="panel"><h2>Colour & appearance</h2><div class="form-grid">${select('App colour','accent',c.dashboard.accent||'blue',[['blue','Blue · Media Stack default'],['red','Red'],['yellow','Yellow'],['green','Green'],['orange','Orange'],['purple','Purple']])}${select('Appearance','appearance',c.dashboard.appearance,[['dark','Dark'],['light','Light'],['system','Follow device']])}</div><p class="hint">Preview changes here, then save. Your choice also applies to the sign-in screen.</p><div class="theme-preview"><strong>Media Stack</strong><span class="pill">Your selected colour</span><button class="primary" type="button" data-theme-sample>Button preview</button></div></section><section class="panel"><h2>Right now cards</h2><p>Choose which details appear on Overview. Cards for apps in your stack appear on Overview. Unavailable data is shown with an explanation.</p><div class="widget-options">${overviewWidgets.map(([id,label])=>check(label,'widget-'+id,(c.dashboard.overview_widgets||defaultWidgets).includes(id))).join('')}</div></section><section class="panel"><h2>Updates on this page</h2><div class="form-grid">${field('Refresh interval (seconds)','refresh-seconds',c.dashboard.refresh_seconds,'number','min="10" max="3600"')}${field('Mark data stale after (seconds)','stale-seconds',c.dashboard.stale_seconds,'number','min="20"')}${field('Rows per page','page-size',c.dashboard.page_size,'number','min="5" max="100"')}</div></section>`;
 if(section==='connections')body+=(nativeMarkup?'<details class="panel"><summary>Find existing Windows apps</summary>'+nativeMarkup+'</details>':'')+'<section aria-label="App connections">'+c.dashboard.order.filter(key=>c.integrations[key].enabled||state.focusIntegration===key).map(appSettings).join('')+'</section>'+webLoginsPanel()+generatedLoginPanel()+'<section class="panel"><h2>Connection checks</h2><button id="test">Test saved connections</button></section>';
 if(section==='media')body+=mediaSetupPanel()+qualityRulesPanel()+`<section class="panel"><h2>Media storage</h2>${field('Shared media folder','data-root',c.storage.data_root)}<details><summary>Advanced storage preferences</summary><div class="form-grid">${field('Minimum free space (GiB)','free-space',c.storage.minimum_free_gb,'number','min="1"')}${field('Container user ID','uid',c.storage.uid,'number','min="1"')}${field('Container group ID','gid',c.storage.gid,'number','min="1"')}</div></details><p class="hint">Changing this preference does not move existing media or change app mounts.</p></section>`;
 if(section==='maintenance')body+=installedAppsPanel()+updatesPanel()+stackarrUpdatePanel()+`<section class="panel"><h2>Notifications & settings backups</h2>${check('Daily redacted configuration backups','backups',c.maintenance.backups_enabled)}${field('Backups to retain','retention',c.maintenance.backup_retention,'number','min="1" max="90"')}${check('Enable webhook notifications','notifications',c.maintenance.notifications_enabled)}${field('HTTPS webhook address','webhook','','password','autocomplete="new-password"')}<p class="hint">Blank webhook fields keep the saved address. App and media backups are managed in Backups.</p></section><section class="panel"><h2>Configuration tools</h2><div class="actions"><button id="export">Export configuration</button><button id="backup">Back up settings now</button><button id="support">Download support bundle</button></div><label for="import">Import settings for review</label><input id="import" type="file" accept=".json"></section>`;
 if(section==='access')body+='<section class="panel"><h2>Your addresses</h2><p>On this computer: '+escape(state.network?.origin||location.origin)+'</p><p>'+escape(state.network?.lan_origin?'Home network: '+state.network.lan_origin:'Open Start Stackarr → Home network & recovery to prepare local HTTPS access.')+'</p><button data-help-topic="network">Home-network help</button></section>';
 return body+(section==='recommended'?'':'<div class="setup-actions"><span class="hint">Save changes to keep these preferences.</span><button class="primary" id="save">Save settings</button></div>');
}
function readSettingsFields(c){
 const value=id=>document.getElementById(id)?.value;
 const number=(id,target,key)=>{if(value(id)!==undefined)target[key]=Number(value(id));};
 if(value('appearance')!==undefined)c.dashboard.appearance=value('appearance');
 if(value('accent')!==undefined)c.dashboard.accent=value('accent');
 if(document.getElementById('widget-apps'))c.dashboard.overview_widgets=overviewWidgets.filter(([id])=>document.getElementById('widget-'+id).checked).map(([id])=>id);
 number('refresh-seconds',c.dashboard,'refresh_seconds');number('stale-seconds',c.dashboard,'stale_seconds');number('page-size',c.dashboard,'page_size');
 if(value('data-root')!==undefined)c.storage.data_root=value('data-root');
 number('free-space',c.storage,'minimum_free_gb');number('uid',c.storage,'uid');number('gid',c.storage,'gid');
 if(value('order')!==undefined)c.dashboard.order=value('order').split(',').map(s=>s.trim());
 for(const [id,key] of [['backups','backups_enabled'],['notifications','notifications_enabled']]){const el=document.getElementById(id);if(el)c.maintenance[key]=el.checked;}
 number('retention',c.maintenance,'backup_retention');if(value('webhook')!==undefined)c.maintenance.notification_url=value('webhook');
 return c;
}
function helpScreen(){return heading('Help & FAQ','Answers and guidance for your media stack.')+Object.keys(helpTopics).map(key=>`<section id="help-${key}">${helpPanel(key)}</section>`).join('');}
function workflowAdvice(){
 const enabled=key=>state.config.integrations[key]?.enabled||setupDraft?.draft.apps.includes(key);
 if((enabled('sonarr')||enabled('radarr'))&&(!enabled('qbittorrent')||!enabled('prowlarr')))return '<aside class="workflow-note"><strong>Planning automatic downloads?</strong><p>TV and movie apps can manage an existing library on their own. To download automatically, connect a download client and content sources in those apps. Existing download clients and sources configured inside your TV or movie apps can stay there. Stackarr can install and connect qBittorrent and Prowlarr when you need them.</p></aside>';
 return '';
}
function setupActionBlock(row){
 if(!row.action||row.state==='done')return '';
 const enabled=key=>state.config.integrations[key]?.enabled;
 if(['source-setup','source-check','source-validation'].includes(row.action.id)&&(!enabled('prowlarr')||!state.credentials.includes('prowlarr')))return 'Connect Prowlarr before checking or adding sources here.';
 if(['wiring-preview','companion-review'].includes(row.action.id)&&!setupDeployment.available)return 'Reconnect to the installation computer first.';
 if(row.action.id==='wiring-preview'){
  const missing=(row.apps||[]).filter(key=>!enabled(key)||!state.credentials.includes(key));
  if(missing.length)return 'Connect '+missing.map(key=>state.catalog[key]?.name||key).join(', ')+' before reviewing these connections.';
 }
 return '';
}
function setupChecklist(){
 const journey=setupDeployment.journey;
 if(!journey||journey.draft_revision!==setupDraft.revision)return '<section class="panel"><h2>Start with your apps</h2><p>Choose the apps you need. A small stack is fine.</p><button data-setup-task="plan">Choose apps</button></section>';
 return `<section class="panel setup-roadmap"><div class="section-head"><h2>Your setup checklist</h2><span>${journey.summary.done} of ${journey.summary.total} checked</span></div><ol>${journey.checkpoints.map((row,index)=>{
  const blocker=setupActionBlock(row);
  return `<li data-checkpoint="${escape(row.id)}"><span class="task-number" aria-hidden="true">${row.state==='done'?'✓':index+1}</span><div class="task-description"><strong>${escape(row.title)}</strong><p>${escape(row.detail)}</p>${blocker?'<p class="task-blocker" id="block-'+escape(row.id)+'">'+escape(blocker)+'</p>':''}</div><div class="task-controls"><span class="pill ${row.state==='done'?'good':''}">${escape(setupCheckpointLabels[row.state]||'Not checked')}</span>${row.action&&row.state!=='done'?`<button data-setup-checkpoint="${escape(row.id)}" ${blocker?'disabled aria-describedby="block-'+escape(row.id)+'"':''}>${escape(row.action.label)}</button>`:''}</div></li>`;
 }).join('')}</ol></section>`;
}
function setupScreen(){
 if(!setupDraft)return heading('Setup','Loading saved progress…');
 const task=state.setupTask||'';
 if(task==='plan')return '<div class="task-workspace"><button data-setup-task="">← Back to checklist</button>'+setupEditor()+'</div>';
 let body=heading('Setup','Work through what your selected apps need. Optional apps stay optional.')+setupChecklist()+workflowAdvice();
 if(task){
  const panels={accounts:accountTaskPanel,sources:indexerPanel,connections:()=>wiringPanel()+mediaSetupPanel(),companions:companionsPanel,verification:setupVerificationPanel,reconnect:setupReconnectPanel,progress:installationProgressPanel};
  body+='<section class="task-workspace" id="setup-task-workspace"><div class="section-head"><h2>Current task</h2><button data-setup-task="">Close task</button></div>'+ (panels[task]?.()||'<p>This tool is not available for your current app selection. Review your apps or their connection settings first.</p>')+'</section>';
 }
 const tools=[['accounts','Accounts'],['sources','Content sources'],['connections','App connections'],['companions','Companion apps'],['progress','Installation progress']];
 return body+'<div class="setup-actions"><button data-setup-task="plan">Review app choices</button><button id="setup-install-refresh">Check progress</button></div><details class="panel setup-tool-picker"><summary>Open a setup tool</summary><p>Use these to revisit a completed task without changing your app choices.</p><div class="actions">'+tools.map(([id,label])=>'<div><button data-setup-task="'+id+'" '+(setupToolBlock(id)?'disabled':'')+'>'+label+'</button>'+(setupToolBlock(id)?'<p class="hint">'+escape(setupToolBlock(id))+'</p>':'')+'</div>').join('')+'</div></details><div id="setup-error" role="alert" hidden></div>';
}
function installationProgressPanel(){return '<section class="panel"><h2>Installation progress</h2>'+(setupDeployment.operations||[]).map(op=>'<article><h3>'+op.apps.map(key=>escape(state.catalog[key]?.name||key)).join(', ')+'</h3><p>'+escape(op.message)+'</p>'+(['failed','interrupted'].includes(op.state)&&setupDeployment.available?'<button data-install-resume="'+escape(op.id)+'">Resume installation</button>':'')+'</article>').join('')+'</section>';}
async function openSetupCheckpoint(row){
 state.setupAllApps=false;const action=row?.action;if(!action||setupActionBlock(row))return;
 if(state.dirty){announce('Save your current changes before opening another setup task.');return;}
 const planning={'choose-apps':0,'choose-storage':1,'check-runtime':0,'review-install':2};
 if(Object.hasOwn(planning,action.id)){
  state.setupTask='plan';await setupJourneyStep(planning[action.id]);render();
  focusSetupTarget(document.getElementById(action.target));
  if(['check-runtime','review-install'].includes(action.id))await runSetupAction(document.getElementById(action.target));
  return;
 }
 if(action.id==='accounts'&&!['plex','seerr'].includes(action.app)){openConnectionSettings(action.app);return;}
 if(action.id==='test-connections'){await api('refresh','POST',{});announce('Connection checks started.');state.view='health';render();return;}
 state.appReconnect=['plex','seerr'].includes(action.app)?action.app:null;
 state.setupTask=['accounts','finish-connecting'].includes(action.id)?'accounts':['source-setup','source-validation','source-check'].includes(action.id)?'sources':action.id==='wiring-preview'?'connections':action.id==='companion-review'?'companions':action.id==='verification'?'verification':action.id==='reconnect-installation'?'reconnect':'progress';
 render();focusSetupTarget(document.getElementById('setup-task-workspace'));
 let target;
 if(action.id==='source-setup')target=document.getElementById('indexer-load-providers');
 if(['wiring-preview','source-check'].includes(action.id))target=document.getElementById(action.target);
 if(action.id==='companion-review')target=[...document.querySelectorAll('[data-companions-review]')].find(b=>!action.installation||b.dataset.companionsReview===action.installation);
 if(action.id==='finish-connecting'&&state.credentials.includes(action.app))target=[...document.querySelectorAll('[data-finish-install]')].find(b=>!action.installation||b.dataset.finishInstall===action.installation);
 if(target)await runSetupAction(target);
}
function openConnectionSettings(key){state.view='settings';state.settingsSection='connections';state.focusIntegration=key;render();const detail=document.getElementById(key+'-enabled')?.closest('details')||document.querySelector('.settings-app[open]');detail?.scrollIntoView({block:'nearest'});detail?.querySelector('summary')?.focus();}
function bindPreferences(){
 root.querySelectorAll('[data-app-setup]').forEach(b=>b.onclick=()=>{if(leaveScreen())openAppSetup(b.dataset.appSetup);});
 root.querySelectorAll('[data-reconnect-app]').forEach(b=>b.onclick=()=>{if(!leaveScreen())return;state.view='setup';state.setupTask='accounts';state.appReconnect=b.dataset.reconnectApp;render();focusSetupTarget(document.getElementById('app-reconnect'));});
 root.querySelectorAll('[data-retry-connections]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await api('refresh','POST',{});announce('Connection checks started.');await poll();}catch(e){announce(e.message);}finally{b.disabled=false;}});
 root.querySelectorAll('[data-open-widget-settings]').forEach(b=>b.onclick=()=>{if(!leaveScreen())return;state.view='settings';state.settingsSection='appearance';render();});
 root.querySelectorAll('[data-settings-section]:not([data-open-widget-settings])').forEach(button=>button.onclick=async()=>{if(!leaveScreen())return;state.settingsSection=button.dataset.settingsSection;if(state.settingsSection==='recommended'&&!presetState.catalog){try{presetState.catalog=await api('quality-presets');presetState.error='';}catch(error){presetState.error=error.message;}}render();});
 for(const id of ['accent','appearance']){const el=document.getElementById(id);if(el)el.addEventListener('change',()=>{document.documentElement.dataset.accent=document.getElementById('accent').value;const mode=document.getElementById('appearance').value;document.documentElement.dataset.theme=mode==='system'?(matchMedia('(prefers-color-scheme:light)').matches?'light':'dark'):mode;});}
 root.querySelectorAll('[data-help-topic]').forEach(button=>button.onclick=()=>{if(!leaveScreen())return;state.view='help';render();const panel=document.getElementById('help-'+button.dataset.helpTopic)?.querySelector('details');if(panel){panel.open=true;focusSetupTarget(panel);}});
 root.querySelectorAll('[data-setup-task]').forEach(button=>button.onclick=()=>{if(!leaveScreen())return;state.setupAllApps=!!button.closest('.setup-tool-picker');state.setupTask=button.dataset.setupTask;state.view='setup';render();});
 root.querySelectorAll('[data-setup-checkpoint]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{await openSetupCheckpoint(setupDeployment.journey?.checkpoints.find(row=>row.id===button.dataset.setupCheckpoint));}catch(e){announce(e.message);}finally{if(button.isConnected)button.disabled=false;}});
}

function connectionState(status){
 if(status?.state==='link-only')return {label:'Link only',good:false};
 if(status?.state==='ready'&&!status.stale)return {label:'Connected',good:true};
 if(status?.error_code==='authentication')return {label:'Sign-in needed',good:false};
 if(!status||status.state==='pending')return {label:'Checking',good:false};
 return {label:status.collected_at&&status.stale?'Stale':'Unavailable',good:false};
}
function connectionDetails(key,status){
 if(status?.state==='ready'&&!status.stale&&!status.error)return '';
 const problem=status?.error_code==='authentication'?'The app rejected Stackarr’s saved credentials. Review the connection or reconnect its account.':status?.error||'Waiting for a successful connection check.';
 return `<details class="connection-details"><summary>Connection details</summary><p>${escape(problem)}</p><dl><div><dt>Last attempt</dt><dd>${escape(time(status?.attempted_at))}</dd></div><div><dt>Last successful check</dt><dd>${escape(time(status?.collected_at))}</dd></div></dl><div class="actions"><button data-stack-edit="${escape(key)}">Review connection</button>${['plex','seerr'].includes(key)?`<button data-reconnect-app="${key}">Reconnect ${escape(state.catalog[key].name)}</button>`:''}<button data-retry-connections>Retry connections</button></div></details>`;
}
function refinedAppCard(key){
 const app=state.config.integrations[key],status=integrations().find(row=>row.id===key),owner=stackOwner(key);
 const name=state.catalog[key]?.name||key,presentation=connectionState(status);
 const external=app.read_only||!(setupDeployment.operations||[]).some(op=>op.state==='needs-setup'&&op.apps?.includes(key));
 return `<article class="stack-service" data-refresh-key="stack-${escape(key)}"><div class="stack-service-main"><img class="app-icon" src="${key==='seerr'?'/static/favicon.svg':'/static/icons/'+key+'.png'}" alt=""><div><h3>${escape(name)}</h3><span class="app-role">${escape(appRole(key))}</span></div>${appLink(status?.url||browserAppUrl(key))}</div><div class="connection-status"><span class="stack-state ${presentation.good?'is-online':''}">${escape(presentation.label)}</span>${external?'<span class="pill">External connection</span>':''}</div>${connectionDetails(key,status)}<div class="stack-service-actions">${owner?`<button data-stack-restart="${escape(key)}" data-stack-deployment="${escape(owner.id)}" aria-label="Restart ${escape(name)}">↻ Restart</button>`:''}<button data-stack-edit="${escape(key)}" aria-label="Manage ${escape(name)}">Settings</button></div></article>`;
}
function groupedAppCards(all=false){
 return stackGroups.map(([id,label,keys])=>{
  const selected=state.config.dashboard.order.filter(key=>keys.includes(key)&&state.config.integrations[key]?.enabled&&(all||state.config.integrations[key].visible!==false));
  return selected.length?`<section class="stack-service-section" aria-labelledby="stack-group-${id}"><div class="section-head"><h2 id="stack-group-${id}">${escape(label)}</h2></div><div class="stack-services">${selected.map(stackCard).join('')}</div></section>`:'';
 }).join('')||'<div class="empty"><h2>Your stack starts with an app</h2><p>Open Apps to install something new or connect one you already use.</p></div>';
}
function appCatalogScreen(){
 return heading('Apps','Install a supported app or configure one already in your stack.')+'<div class="app-catalog-list">'+state.config.dashboard.order.filter(key=>setupInstallable.has(key)).map(key=>{
  const configured=state.config.integrations[key].enabled;
  return `<article class="app-catalog-row"><img class="app-icon" src="${key==='seerr'?'/static/favicon.svg':'/static/icons/'+key+'.png'}" alt=""><div><h2>${escape(state.catalog[key].name)} <span class="pill">${configured?'Configured':'Available to install'}</span></h2><span class="app-role">${escape(appRole(key))}</span><p>${escape(setupDescriptions[key])}</p></div><button ${configured?'data-stack-edit':'data-app-setup'}="${escape(key)}">${configured?'Connection settings':'Set up '+escape(state.catalog[key].name)}</button></article>`;
 }).join('')+'</div>';
}
function openAppSetup(key){
 if(!setupInstallable.has(key)||state.config.integrations[key]?.enabled)return;
 const name=state.catalog[key].name,dialog=document.createElement('dialog');dialog.className='stack-dialog';dialog.setAttribute('aria-labelledby','app-setup-title');
 dialog.innerHTML=`<div class="section-head"><h2 id="app-setup-title">Set up ${escape(name)}</h2><button data-close-app aria-label="Close app setup">×</button></div><p>${escape(setupDescriptions[key])}</p>${select('How would you like to add '+name+'?','app-setup-mode','install',[['install','Install a new '+name+' app'],['connect','Connect my existing '+name+' app']])}<div id="app-existing-address" hidden>${field(name+' address','app-setup-url','','url','placeholder="http://server:port"')}</div><p class="hint" id="app-setup-requirements">${['sonarr','radarr'].includes(key)?'This app can manage an existing library. Automatic downloads also need a download client and content sources.':key==='tautulli'?'Viewing statistics require a Plex server.':key==='cleanuparr'?'Guided cleanup connections require a download client and Sonarr or Radarr. Cleanup starts in dry-run mode.':key==='seerr'?'Requests need a supported media server. Automated movie and TV requests also need Radarr or Sonarr.':'Only this selected app is added. Other apps keep their settings.'}</p><div class="actions"><button id="app-setup-continue" class="primary">Continue to setup</button><button data-close-app>Cancel</button></div><p id="app-setup-error" role="alert"></p>`;
 let pending=false;const trigger=document.activeElement;
 dialog.addEventListener('cancel',event=>{if(pending)event.preventDefault();});
 dialog.addEventListener('close',()=>{dialog.remove();if(trigger?.isConnected)trigger.focus();});
 dialog.querySelectorAll('[data-close-app]').forEach(b=>b.onclick=()=>dialog.close());
 dialog.querySelector('#app-setup-mode').onchange=e=>{dialog.querySelector('#app-existing-address').hidden=e.target.value!=='connect';};
 dialog.querySelector('#app-setup-continue').onclick=async()=>{
  pending=true;dialog.querySelectorAll('button').forEach(b=>b.disabled=true);
  try{
   const mode=dialog.querySelector('#app-setup-mode').value,url=dialog.querySelector('#app-setup-url').value.trim();
   if(mode==='connect'&&!url)throw new Error('Enter the address of your existing app.');
   const saved=await api('onboarding'),draft=stackAddDraft(saved.draft,key,mode);
   if(mode==='connect')draft.choices[key]={...draft.choices[key],url,browser_url:url};
   setupDraft=await api('onboarding','PUT',{revision:saved.revision,draft});
   setupInstallReview=null;setupConnectionReview=null;setupPortResults=null;setupDiscovery=null;
   await loadSetup();state.view='setup';state.setupTask='plan';state.setupAllApps=false;state.error='';state.notice='';
   dialog.close();render();const choices=document.getElementById('setup-custom-apps');if(choices)choices.open=true;focusSetupTarget(document.getElementById('setup-mode-'+key));
  }catch(error){dialog.querySelector('#app-setup-error').textContent=error.message;dialog.querySelectorAll('button').forEach(b=>b.disabled=false);}finally{pending=false;}
 };
 root.append(dialog);dialog.showModal();dialog.querySelector('#app-setup-mode').focus();
}
function widgetData(id){
 if(id==='apps'){const rows=integrations().filter(a=>a.state!=='link-only'),ready=rows.filter(a=>a.state==='ready'&&!a.stale).length;return {value:ready+' / '+rows.length,note:'with fresh data'};}
 if(id==='storage'){const row=state.storageOverview;return row?.available?{value:row.free_gb+' GB',note:'free of '+row.total_gb+' GB · shared media drive'}:{value:'—',note:row?.message||'Storage capacity has not been checked.'};}
 const specs={downloads:['downloads'],streams:['streams'],queue:['queue'],'sonarr-queue':['queue','sonarr'],'radarr-queue':['queue','radarr'],sources:['sources','prowlarr'],blocklist:['blocklist'],health:['health'],requests:['requests','seerr'],monitors:['monitoring','kuma']};
 const [table,app]=specs[id]||[];
 let rows=integrations().filter(a=>(a.capabilities||[]).includes(table)&&(!app||a.id===app));
 if(id==='streams'&&rows.some(a=>a.id==='plex'))rows=rows.filter(a=>a.id==='plex');
 const fresh=rows.filter(a=>a.state==='ready'&&!a.stale),count=fresh.reduce((sum,a)=>sum+(a.tables?.[table]||[]).filter(row=>id==='downloads'?row.state==='downloading':id==='sources'?row.state==='enabled':id==='health'?/warn|error|unhealthy|failed|unsafe/i.test(row.state||''):true).length,0);
 return {value:fresh.length?count+(fresh.length<rows.length?' + ?':''):'—',note:!rows.length?'No source configured':fresh.length<rows.length?'Waiting for '+rows.filter(a=>!fresh.includes(a)).map(a=>a.name).join(', '):'Reported by '+rows.map(a=>a.name).join(', ')};
}
function overviewStats(){return (state.config.dashboard.overview_widgets||defaultWidgets).filter(id=>['apps','storage'].includes(id)||widgetData(id).note!=='No source configured').map(id=>{const metric=widgetData(id),label=overviewWidgets.find(([key])=>key===id)?.[1]||id;return `<div class="stat" data-widget="${escape(id)}"><span>${escape(label)}</span><strong>${escape(metric.value)}</strong><small>${escape(metric.note)}</small></div>`;}).join('');}
function operationHistoryPanel(){return '<section class="panel"><div class="section-head"><h2>App action history</h2><button id="lifecycle-refresh">Refresh actions</button></div><div id="lifecycle-history">'+lifecycleHistory()+'</div></section>';}
function accountTaskPanel(){
 const key=state.appReconnect;
 if(!key)return finishConnectingPanel()+webLoginsPanel()+generatedLoginPanel();
 const name=state.catalog[key].name,owned=(setupDeployment.operations||[]).filter(op=>op.state==='needs-setup'&&op.apps?.includes(key));
 return '<section class="panel" id="app-reconnect"><h2>Reconnect '+escape(name)+'</h2><p>Open '+escape(name)+' and complete its account sign-in on the correct server. Your Stackarr password stays the same.</p>'+appLink(browserAppUrl(key))+(key==='plex'?'<p>Then check Plex sign-in below. Review the proposed connection and library changes before saving them.</p>'+owned.map(op=>'<button data-accounts-review="'+escape(op.id)+'">Check Plex sign-in & continue</button>').join('')+accountSetupReview()+'<p id="account-setup-error" role="alert">'+escape(state.accountError||'')+'</p>':'<p>After signing in, review the saved connection credentials.</p><button data-stack-edit="seerr">Review Seerr connection</button>')+'</section>';
}

function setupToolBlock(id){
 const enabled=key=>state.config.integrations[key]?.enabled;
 if(id==='sources'&&(!enabled('prowlarr')||!state.credentials.includes('prowlarr')))return 'Connect Prowlarr first.';
 if(id==='accounts'&&!enabled('plex')&&!enabled('seerr')&&!(setupDeployment.login_setup||[]).length)return 'Connect an app with account setup first.';
 if(id==='connections'&&!enabled('sonarr')&&!enabled('radarr'))return 'Add a TV or movie library app first.';
 if(id==='companions'&&(!setupDeployment.available||!(setupDeployment.operations||[]).some(op=>(op.apps||[]).some(key=>['tautulli','kuma','cleanuparr'].includes(key)))))return 'Install a companion app and connect the installation computer first.';
 if(id==='progress'&&!(setupDeployment.operations||[]).length)return 'No installation has started.';
 return '';
}
