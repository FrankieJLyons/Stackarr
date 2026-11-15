'use strict';
const root=document.querySelector('#root');
const state={csrf:'',config:null,catalog:{},revision:0,credentials:[],status:null,view:'home',step:0,query:'',sort:'title',ascending:true,pages:{},error:'',notice:'',busy:false};
const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icons={home:'⌂',overview:'◫',apps:'▦',activity:'≋',health:'♡',backups:'↺',settings:'⚙'};
const names={home:'Home',requests:'Your requests',library:'Your library',overview:'Server status',apps:'Apps',activity:'Activity',health:'Health',backups:'Backups',settings:'Settings',help:'Help & FAQ',setup:'Setup',onboarding:'Build your stack'};
const time=value=>value?new Date(value*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}):'Not collected';
const announce=text=>{document.querySelector('#announcer').textContent=text;setTimeout(()=>{document.querySelector('#announcer').textContent='';},6500);};
async function api(path,method='GET',data){
 const response=await fetch('/api/'+path,{method,cache:'no-store',headers:{'Content-Type':'application/json','X-CSRF-Token':state.csrf},...(data!==undefined?{body:JSON.stringify(data)}:{})});
 const body=await response.json();
 if(!response.ok){if(response.status===401&&path!=='login')await boot();throw new Error(Array.isArray(body.detail)?body.detail.map(e=>`${e.field}: ${e.message}`).join('; '):body.detail||'Request failed');}
 return body;
}
function brand(){return '<div class="brand">'+brandMark()+'stackarr</div>';}
function auth(setup){
 clearHome();
 clearQualityRules();
 clearPresets();
 clearCleanupPresets();
 clearMediaSetup();
 stopSchedule();
 clearTimeout(setupApprovalTimer);
 if(setup&&!launcherApproved){if(localLauncher)launcherApproval();else dockerWelcome();return;}
 root.innerHTML=`<main class="auth" id="main"><section class="auth-story">${brand()}<p class="eyebrow">YOUR MEDIA, TOGETHER</p><h1>A little less managing.<br>A lot more watching.</h1><p>Your applications, downloads and streams. One calm place to see how everything is doing.</p></section><section class="auth-form"><form id="auth-form"><p class="eyebrow">${setup?'WELCOME TO STACKARR':'YOUR CONTROL CENTER'}</p><h2>${setup?'Make yourself at home.':'Welcome back.'}</h2><p>${setup?'Choose a password to protect this Stackarr control panel. This stays on your computer; no Stackarr online account or email is needed.':'Enter your Stackarr password to open this control panel. This is separate from your Plex sign-in.'}</p><div id="auth-error" role="alert"></div><label for="password">${setup?'Create a password':'Password'}</label><div class="password-field"><input id="password" type="password" required minlength="12" maxlength="256" aria-describedby="password-help" autocomplete="${setup?'new-password':'current-password'}"><button id="show-password" class="password-eye" type="button" aria-label="Show password" aria-pressed="false">${eyeIcon()}</button></div><p id="password-help" class="hint">${setup?'Use at least 12 characters. A few memorable words work well. Save it in your password manager.':'Use the password you chose when setting up Stackarr.'}</p><button class="primary" type="submit">${setup?'Continue to setup →':'Sign in →'}</button><p class="hint">Private by default. Your credentials stay on your server.<br>Stackarr 0.1.0 · Public beta</p></form></section></main>`;
 document.querySelector('#show-password').onclick=e=>{const button=e.currentTarget,input=document.querySelector('#password'),visible=input.type==='password';input.type=visible?'text':'password';button.setAttribute('aria-label',visible?'Hide password':'Show password');button.setAttribute('aria-pressed',String(visible));button.innerHTML=eyeIcon(visible);};
 const form=document.querySelector('#auth-form');
 form.onsubmit=async e=>{e.preventDefault();if(form.dataset.submitting==='true')return;const button=form.querySelector('button[type=submit]');form.dataset.submitting='true';button.disabled=true;try{if(setup&&!await checkSetupApproval(form))return;const password=form.querySelector('#password').value;if(setup){await api('setup','POST',{password});auth(false);document.querySelector('#auth-error').textContent='Your Stackarr password is saved. Signing you in…';}state.csrf=(await api('login','POST',{password})).csrf;await load();state.view=initialView();render();schedule();}catch(error){document.querySelector('#auth-error').textContent=error.message;}finally{form.dataset.submitting='false';button.disabled=setup&&!launcherApproved;}};
 if(setup)watchSetupApproval(form);
}
function initialView(){
 const apps=state.config.integrations;
 if(!Object.values(apps).some(app=>app.enabled))return 'setup';
 return 'overview';
}
async function load(){const data=await api('config');state.config=data.config;state.savedConfig=structuredClone(data.config);state.catalog=data.catalog;state.revision=data.revision;state.credentials=data.credentials_saved;state.network=data.network;state.notificationConfigured=data.notification_configured;state.status=await api('status');state.refreshError='';await loadSetup();try{state.storageOverview=await api('overview/storage');state.storageChecked=Date.now();}catch{state.storageOverview={available:false,message:'Storage capacity is temporarily unavailable.'};}theme();}
function theme(){applyAppearance();}
let generatedLoginTimer;
function hideGeneratedLogin(){clearTimeout(generatedLoginTimer);const output=document.querySelector("#generated-login-output");if(output){output.replaceChildren();output.hidden=true;}}
document.addEventListener("visibilitychange",()=>{if(document.hidden)hideGeneratedLogin();});
function render(){
 hideGeneratedLogin();
 state.dirty=false;state.appDirty=false;state.indexerDirty=false;
 root.innerHTML=controlRoomShell();
 document.querySelectorAll('[data-view]').forEach(button=>button.onclick=()=>{if(!leaveScreen())return;state.view=button.dataset.view;state.notice='';state.error='';render();document.querySelector('#main').focus();});
 document.querySelector('#logout').onclick=async()=>{if(!leaveScreen())return;try{await api('logout','POST',{});auth(false);}catch(e){announce(e.message);}};
 bind();
 refreshErrorBanner();
 if(['settings','apps','setup','onboarding'].includes(state.view)){root.querySelectorAll('input,select,textarea').forEach(el=>{if(!el.id.startsWith('generated-login-')&&!el.readOnly&&el.dataset.setupControl!=='navigation'){const mark=()=>{state.dirty=true;if(el.id.startsWith('indexer-'))state.indexerDirty=true;else state.appDirty=true;};el.addEventListener('input',mark);el.addEventListener('change',mark);}});}
}
// Background installation updates can rebuild the screen without losing the
// reader's place. Status collection below uses smaller, independent regions.
function contextSelector(element,scope=root){
 if(!element||!scope.contains(element))return null;
 if(element.id)return '#'+CSS.escape(element.id);
 const parts=[];
 while(element&&element!==scope){
  if(element.id){parts.unshift('#'+CSS.escape(element.id));break;}
  const siblings=Array.from(element.parentElement?.children||[]).filter(sibling=>sibling.tagName===element.tagName);
  parts.unshift(element.localName+':nth-of-type('+(siblings.indexOf(element)+1)+')');element=element.parentElement;
 }
 return parts.join(' > ');
}
function detailsKey(element,scope){
 if(element.id)return 'id:'+element.id;
 const owner=element.closest('[data-refresh-key]');
 if(owner)return owner.dataset.refreshKey+':'+Array.from(owner.querySelectorAll('details')).indexOf(element);
 const label=element.querySelector('summary')?.textContent.trim()||'';
 const peers=Array.from(scope.querySelectorAll('details')).filter(detail=>detail.querySelector('summary')?.textContent.trim()===label);
 return label+':'+peers.indexOf(element);
}
function captureContext(scope=root){
 const active=scope.contains(document.activeElement)?document.activeElement:null;
 return {x:window.scrollX,y:window.scrollY,
  details:new Map(Array.from(scope.querySelectorAll('details')).map(element=>[detailsKey(element,scope),element.open])),
  fields:Array.from(scope.querySelectorAll('input[id],select[id],textarea[id]')).filter(element=>!element.readOnly&&!['password','file'].includes(element.type)&&!element.id.startsWith('generated-login-')).map(element=>({id:element.id,value:element.value,checked:element.checked})),
  scroll:Array.from(scope.querySelectorAll('*')).filter(element=>element.scrollTop||element.scrollLeft).map(element=>({selector:contextSelector(element,scope),x:element.scrollLeft,y:element.scrollTop})),
  focus:active?{selector:contextSelector(active,scope),start:active.selectionStart,end:active.selectionEnd,direction:active.selectionDirection}:null};
}
function restoreContext(context,scope=root,{fields=false,focus=false}={}){
 scope.querySelectorAll('details').forEach(element=>{const key=detailsKey(element,scope);if(context.details.has(key))element.open=context.details.get(key);});
 if(fields)context.fields.forEach(field=>{const element=scope.querySelector('#'+CSS.escape(field.id));if(element){element.value=field.value;if(field.checked!==undefined)element.checked=field.checked;}});
 if(focus&&context.focus?.selector){let element=scope.querySelector(context.focus.selector);if(element?.disabled){element=element.closest('.pager');if(element)element.tabIndex=-1;}if(element){element.focus({preventScroll:true});if(context.focus.start!==null&&context.focus.start!==undefined&&element.setSelectionRange)element.setSelectionRange(context.focus.start,context.focus.end,context.focus.direction);}}
 context.scroll.forEach(position=>{const element=scope.querySelector(position.selector);if(element){element.scrollLeft=position.x;element.scrollTop=position.y;}});
 window.scrollTo(context.x,context.y);
}
function renderPreservingContext(){
 if(state.dirty)return;
 const context=captureContext(),dirty={dirty:state.dirty,appDirty:state.appDirty,indexerDirty:state.indexerDirty};
 render();restoreContext(context,root,{fields:true,focus:true});Object.assign(state,dirty);
}
function leaveScreen(){if(!state.dirty)return true;if(!window.confirm('You have unsaved changes. Leave this screen and discard them?'))return false;state.config=structuredClone(state.savedConfig);state.dirty=false;theme();return true;}
window.addEventListener('beforeunload',event=>{if(state.dirty){event.preventDefault();event.returnValue='';}});
function content(){if(watchViews.includes(state.view))return homeScreen();if(state.view==='backups')return backupsScreen();if(state.view==='setup')return setupScreen();if(state.view==='apps')return appCatalogScreen();if(state.view==='help')return helpScreen();if(state.view==='settings')return settingsScreen();if(state.view==='settings'||state.view==='onboarding')return settings();if(state.view==='activity')return activity();if(state.view==='health')return health();return overview();}
const integrations=()=>state.status?.integrations||[];
function heading(title,description,button=''){return `<div class="heading"><div><p class="eyebrow">YOUR WORKSPACE</p><h1>${title}</h1><p>${description}</p></div>${button}</div>`;}
function refreshButton(){return '<div class="actions"><button data-view="setup">Resume setup</button><button id="refresh">↻ Refresh status</button></div>';}
function overview(){
 const apps=integrations(),monitored=apps.filter(a=>a.state!=='link-only'),ready=monitored.filter(a=>a.state==='ready'&&!a.stale).length;
 const complete=monitored.length&&monitored.every(a=>a.state==='ready'&&!a.stale);
 const metric=key=>{const m=state.status.summaries?.[key];return !m||m.count===null?'—':`${m.count}${m.state==='partial'?' + ?':''}`;};
 const detail=key=>{const m=state.status.summaries?.[key];return !m||m.state==='not-configured'?'No source configured':m.state==='complete'?m.sources.join(', '):'Waiting for '+m.missing.join(', ');};
 return `<section class="stack-health" id="overview-summary" aria-label="Overall health"><div><p class="eyebrow">LIVE SYSTEM HEALTH</p><h2>${!apps.length?'Build your media stack.':complete?'Everything is connected.':!monitored.length?'Your apps are ready to open.':'Your stack needs attention.'}</h2><p>${!apps.length?'Connect your existing apps or install something new.':!monitored.length?'Link-only apps are ready to open. Detailed monitoring is not enabled.':`${ready} of ${monitored.length} monitored apps have fresh data. ${ready<monitored.length?'Check the affected app below or open Health for details.':'Your library, automation, downloads and monitoring, together.'}`}</p></div><div class="stack-health-ring ${complete?'all-ready':''}"><div><strong>${ready}/${monitored.length}</strong><span>connected</span></div></div></section><div class="section-head"><h2>Right now</h2><div class="actions"><button data-settings-section="appearance" data-open-widget-settings>Choose cards</button><button id="refresh">↻ Refresh status</button></div></div>`+
 `<div class="stats" id="overview-stats">${overviewStats()}</div>`+
 `<div id="overview-apps">${stackApplications()}</div>`+stackActionPanel();
}
function card(a){return stackCard(a.id);}
function activity(){return heading('The journey to your library.','Downloads, imports and streams — with their original states kept distinct.',refreshButton())+tables(['downloads','queue','streams','requests','sources']);}
function health(){return heading('A little peace of mind.','Connection issues and application health, without automatic destructive actions.',refreshButton())+`<div class="cards" id="health-apps">${integrations().map(card).join('')}</div><div class="section-head"><h2>Application details</h2></div>`+tables(['health','blocklist','monitoring'])+'<section class="panel"><h2>Notification delivery</h2><p>Tests use your saved HTTPS destination. Messages include only app and state, with a delivery reference.</p><div class="actions"><button id="notification-test">Send test notification</button><button id="notification-status">Refresh delivery status</button></div><pre id="notification-output"></pre></section><section class="panel"><h2>Recent operations</h2><p>Connection checks continue when you close this page. Interrupted checks resume after a restart.</p><button id="jobs">Refresh operations</button><div id="jobs-output" aria-live="polite"></div></section>'+operationHistoryPanel()+'<section class="panel"><h2>Audit trail</h2><p>Settings changes, connection transitions and maintenance results. Media titles and credentials are excluded.</p><button id="audit">Load audit trail</button><pre id="audit-output"></pre></section>';}
function tables(keys){return `<div class="toolbar"><label for="filter">Filter rows</label><input id="filter" type="search" value="${escape(state.query)}" placeholder="Find a title, app or state…"></div><div id="tables">${tableBodies(keys)}</div>`;}
function tableBodies(keys){return keys.map(key=>{
 const relevant=integrations().filter(a=>a.capabilities?.includes(key));
 if(!relevant.length)return '';
 const missing=relevant.filter(a=>a.state!=='ready'||a.stale);
 let rows=integrations().flatMap(a=>(a.tables?.[key]||[]).map(r=>({...r,app:a.name,url:a.url,stale:a.stale||a.state!=='ready'}))).filter(r=>JSON.stringify(r).toLowerCase().includes(state.query.toLowerCase()));
 rows.sort((a,b)=>String(a[state.sort]||'').localeCompare(String(b[state.sort]||''))*(state.ascending?1:-1));
 const size=state.config.dashboard.page_size,pages=Math.max(1,Math.ceil(rows.length/size)),page=Math.min(state.pages[key]||1,pages);state.pages[key]=page;
 return `<section class="panel"><h2>${key[0].toUpperCase()+key.slice(1)}</h2>${missing.length?`<p class="hint">Incomplete data: ${missing.map(a=>escape(a.name)).join(', ')}. Last-known rows may be stale.</p>`:''}<div class="table-scroll"><table><thead><tr>${[['app','Application'],['title','Title / item'],['state','State'],['detail','Details']].map(([field,label])=>`<th scope="col" aria-sort="${state.sort===field?(state.ascending?'ascending':'descending'):'none'}"><button data-sort="${field}">${label} ${state.sort===field?(state.ascending?'↑':'↓'):''}</button></th>`).join('')}<th scope="col">Action</th></tr></thead><tbody>${rows.slice((page-1)*size,page*size).map(r=>`<tr><td>${escape(r.app)}</td><td>${escape(r.title)}</td><td>${escape(r.state)}${r.stale?' · stale':''}</td><td>${escape(r.detail)}</td><td>${appLink(r.url?r.url+(key==='queue'?'/activity/queue':''):'')}</td></tr>`).join('')||`<tr><td colspan="5">${missing.length?'Data unavailable or still collecting. Check Health for details.':'No reported rows for this view.'}</td></tr>`}</tbody></table></div><div class="pager"><span>${rows.length} rows · Page ${page} of ${pages}</span><button data-page="${key}" data-direction="-1" ${page===1?'disabled':''}>Previous</button><button data-page="${key}" data-direction="1" ${page===pages?'disabled':''}>Next</button></div></section>`;
 }).join('');}
function field(label,id,value,type='text',extra=''){return `<div class="field"><label for="${id}">${label}</label><input id="${id}" type="${type}" value="${escape(value)}" ${extra}></div>`;}
function select(label,id,value,options){return `<div class="field"><label for="${id}">${label}</label><select id="${id}">${options.map(([key,text])=>`<option value="${key}" ${key===value?'selected':''}>${text}</option>`).join('')}</select></div>`;}
function check(label,id,value){return `<label for="${id}"><input id="${id}" type="checkbox" ${value?'checked':''}>${label}</label>`;}
function appSettings(key){const app=state.config.integrations[key],name=state.catalog[key].name;if(app.read_only)return nativeAppSettings(key);return `<details class="settings-app" ${state.focusIntegration===key?'open':''}><summary><img class="app-icon" src="${key==='seerr'?'/static/favicon.svg':'/static/icons/'+key+'.png'}" alt=""><strong>${name}</strong><span class="pill">${app.read_only?'Imported · read-only':app.enabled?'Enabled':'Not configured'}</span></summary><div class="form-grid"><div>${check('Enable '+name,key+'-enabled',app.enabled)}</div><div>${check('Show on Overview',key+'-visible',app.visible)}</div><input type="hidden" id="${key}-mode" value="${escape(app.mode)}">${field('Host port for new installation',key+'-port',app.port||state.catalog[key].port,'number','min="1" max="65535"')}${field('Server address (including port)',key+'-url',app.url,'url','placeholder="https://app.example:8989"')}${field('Browser address (if different)',key+'-browser',app.browser_url,'url')}<details class="full"><summary>Advanced connection routing</summary>${field('Address other apps can reach (optional)',key+'-peer',app.peer_url||'','url')}<p class="hint">Used for app-to-app connections. Apps installed together use their private Docker names.</p></details>${field('API key / token',key+'-key','','password',`autocomplete="new-password" placeholder="${state.credentials.includes(key)?'Saved securely · leave blank to keep':'Enter API key'}"`)}${key==='qbittorrent'?field('qBittorrent username',key+'-user','','text','autocomplete="off"')+field('qBittorrent password',key+'-password','','password','autocomplete="new-password"'):''}<div class="full hint">${key==='seerr'?'Finish Seerr’s Plex sign-in and library setup, then use Finish connecting for an app Stackarr installed. Preview app connections to add its Arr services. Existing Seerr installs use their API key. Permissions and approvals stay in Seerr.':key==='cleanuparr'?'Safe companion setup keeps dry-run on and automatic jobs off. Stackarr reads safety status and never enables deletion.':key==='kuma'?'Use a Kuma API key for its Prometheus metrics endpoint.':key==='plex'?'Complete Plex sign-in and server claim in Plex first.':'Credentials remain on your server. Blank fields preserve saved credentials.'} These connection settings do not reinstall or restart the app. Blank credentials keep saved values.</div><div class="full">${check('Remove saved credentials when saving',key+'-clear',false)}</div></div></details>`;}
function appsScreen(){return appCatalogScreen();}
function finishConnectingPanel(){
 if(!setupDeployment.available)return '';
 const remoteIds=(setupDeployment.finish_connecting||[]).filter(id=>state.view!=='setup'||setupDeployment.operations.some(op=>op.id===id&&(op.apps||[]).some(setupAppSelected)));
 const installs=setupDeployment.operations.filter(op=>op.state==='needs-setup'&&(op.apps||[]).some(setupAppSelected)&&(remoteIds.includes(op.id)||(op.apps||[]).some(key=>setupAppSelected(key)&&['plex','seerr'].includes(key)&&state.config.integrations[key]?.enabled&&!state.credentials.includes(key))));
 const results=(state.finishResults?.apps||Object.values(setupDeployment.connection_progress||{}).flat()).filter(app=>setupAppSelected(app.app)&&(state.config.integrations[app.app]?.enabled||remoteIds.length));
 if(!installs.length&&!results.length)return accountSetupResult();
 const links=op=>(remoteIds.includes(op.id)?(op.links||[]):
  op.apps.filter(key=>['plex','seerr'].includes(key)&&state.config.integrations[key]?.enabled&&!state.credentials.includes(key))
   .map(key=>({app:key,url:browserAppUrl(key)}))).filter(link=>link.url&&setupAppSelected(link.app));
 return '<section class="panel" id="setup-accounts" tabindex="-1"><h2>Finish connecting your apps</h2><p>Connect ready apps now. Each app saves its own progress; unfinished sign-ins can be completed later.</p>'+accountSetupSteps(installs,links)+installs.map(op=>'<div class="actions">'+links(op).filter(link=>!['plex','seerr'].includes(link.app)).map(link=>`<a href="${escape(link.url)}" target="_blank" rel="noopener noreferrer">Open ${escape(state.catalog[link.app].name)} ↗</a>`).join('')+`<button data-finish-install="${escape(op.id)}">Finish connecting</button></div>`).join('')+'<div role="status">'+(results.length?'<ul>'+results.map(app=>`<li><strong>${escape(app.name)}</strong>: ${escape(app.detail)}</li>`).join('')+'</ul>':'')+'</div></section>';
}
function installedAppsPanel(){
 const installed=setupDeployment.operations.filter(op=>op.state==='needs-setup');
 if(!installed.length)return '';
 return '<section class="panel"><h2>Start, stop & recover</h2><p>Check an installation to start, stop, restart or repair one owned app. Remove app keeps its settings, login, media and backups; Repair brings it back. Repair and removal save a verified safety backup first. If Docker is unavailable, open Docker Desktop and refresh this page.</p>'+installed.map((op,i)=>`<article><h3>${op.apps.map(key=>escape(state.catalog[key]?.name||key)).join(' · ')}</h3><button data-check-install="${escape(op.id)}">Check installation ${installed.length-i}</button><div id="install-check-${escape(op.id)}" role="status"></div></article>`).join('')+'<div id="lifecycle-review" role="status"></div><h3>App action history</h3><button id="lifecycle-refresh">Refresh app actions</button><div id="lifecycle-history" role="status">'+lifecycleHistory()+'</div></section>';
}
function updatesPanel(){
 if(!(setupDeployment.operations||[]).some(op=>op.state==='needs-setup'))return '';
 const rows=state.updateRows;
 return '<section class="panel"><h2>Updates & rollback</h2><p>Update one owned app at a time. Stackarr saves an encrypted configuration snapshot, checks authenticated health and restores the previous image/settings if the update fails. Media and downloads stay in place.</p><button id="updates-refresh">Check packaged updates</button>'+(rows?'<p class="hint">Pinned candidates reviewed '+escape(rows.reviewed_on)+'. This is a packaged catalog; newer vendor releases need a refreshed Stackarr package.</p>'+rows.apps.map(row=>`<p><strong>${escape(row.name)}</strong> · ${row.available?'Candidate '+escape(row.target_version):'Using the packaged candidate'} ${row.available?`<button data-update-review="update" data-update-deployment="${escape(row.deployment)}" data-update-app="${escape(row.app)}">Review update ${escape(row.name)}</button>`:''}</p>`).join('')+'<h3>Update history & recovery</h3>'+rows.history.map(row=>`<p><strong>${escape(row.name)} · ${escape(row.state)}</strong> · ${escape(row.phase)} · ${escape(new Date(row.updated*1000).toLocaleString())} ${['succeeded','needs-recovery'].includes(row.state)?`<button data-update-review="${row.state==='needs-recovery'?'update-recover':'rollback'}" data-update-id="${escape(row.id)}" data-update-deployment="${escape(row.deployment)}" data-update-app="${escape(row.app)}">${row.state==='needs-recovery'?'Recover interrupted update':'Review rollback'} ${escape(row.name)}</button>`:''}</p>`).join(''):'')+'</section>';
}
function settings(){const c=state.config,wizard=state.view==='onboarding';
 let body=heading(wizard?'Build your stack.':'Make it yours.',wizard?'Start small. You can change every choice later in Settings.':'One configuration, shared by your dashboard and installer.');
 body+=helpPanel('settings')+helpPanel('network');
 if(!wizard)body+=stackarrUpdatePanel();
 if(wizard)body+='<div class="steps">'+['1 · Choose apps','2 · Storage & preferences','3 · Review & connect'].map((s,i)=>`<span class="${i===state.step?'current':''}">${s}</span>`).join('')+'</div>';
 if(wizard&&state.step===0)body+='<section><div class="section-head"><h2>Your integrations</h2><span>Any combination. Any server.</span></div>'+c.dashboard.order.map(appSettings).join('')+'</section>';
 if(!wizard||state.step===1)body+=`<section class="panel"><h2>Storage & mounts</h2><p>For newly installed apps, use one shared data folder containing <code>media</code> and <code>downloads</code>. Every app sees it as <code>/data</code>. Existing apps keep their current paths.</p><div class="form-grid">${field('Absolute host data folder','data-root',c.storage.data_root)}${field('Minimum free space (GiB)','free-space',c.storage.minimum_free_gb,'number','min="1"')}${field('Container user ID','uid',c.storage.uid,'number','min="1"')}${field('Container group ID','gid',c.storage.gid,'number','min="1"')}</div><p class="hint">The local preflight checks storage and ports on the Docker host. This browser cannot inspect NAS or host permissions.</p></section><section class="panel"><h2>Dashboard</h2><div class="form-grid">${select('Appearance','appearance',c.dashboard.appearance,[['dark','Control room dark'],['light','Soft light'],['system','Follow device']])}${field('Refresh interval (seconds)','refresh-seconds',c.dashboard.refresh_seconds,'number','min="10" max="3600"')}${field('Mark data stale after (seconds)','stale-seconds',c.dashboard.stale_seconds,'number','min="20"')}${field('Rows per page','page-size',c.dashboard.page_size,'number','min="5" max="100"')}${field('Application order (IDs, comma separated)','order',c.dashboard.order.join(', '))}</div><p class="hint">Sonarr always precedes Radarr. Layout adapts automatically to your screen.</p></section><section class="panel"><h2>Maintenance</h2><div class="form-grid"><div>${check('Daily redacted configuration backups','backups',c.maintenance.backups_enabled)}</div>${field('Backups to retain','retention',c.maintenance.backup_retention,'number','min="1" max="90"')}<div>${check('Server-side webhook notifications','notifications',c.maintenance.notifications_enabled)}</div>${field('HTTPS webhook address','webhook','','password',`autocomplete="new-password" placeholder="${state.notificationConfigured?'Saved · re-enter to change':'https://…'}"`)}</div><p class="hint">Notifications report integration state changes even when this page is closed. Failed deliveries appear in the audit trail. Backups exclude credentials; re-enter them after restoring.</p><p class="hint">Updates are manual. Use Apps to start, stop or restart owned apps, and Backups for reviewed Docker app snapshots. Updates and removal remain manual. Partial downloads are always preserved by Stackarr.</p></section><section class="panel"><h2>Access & security</h2><p>Authentication is required. Current address: <strong>${escape(state.network.origin)}</strong></p><p class="hint">${state.network.lan_origin?'Home-network address: <strong>'+escape(state.network.lan_origin)+'</strong>. Sign in with your Stackarr owner password. Each computer must trust the gateway certificate.':'Home-network access is not configured. On the installation computer, reopen Start Stackarr and choose Home network &amp; recovery to prepare and review secure access.'}</p><p class="hint">Startup before Windows sign-in has not been certified. Keep the server and Docker running. Certificate trust, network access and startup are separate checks.</p></section>`;
 if(wizard&&state.step===2)body+=`<section class="panel"><h2>Ready when you are.</h2><p>${Object.entries(c.integrations).filter(([,a])=>a.enabled).map(([k,a])=>`${escape(state.catalog[k].name)} · ${a.mode==='install'?'new installation':'existing app'}`).join('<br>')||'No apps selected. You can still save and add apps later.'}</p><p>Saving configures monitoring. New installations require the reviewed Compose plan to be applied on your host. Stackarr never changes existing app settings automatically.</p><p>Plex sign-in, indexer selection and app authentication remain guided human steps.</p></section>`;
 body+=`<div class="sticky-actions"><span class="hint">${wizard?'Your stack, your choices.':'Credentials are masked and excluded from exports.'}</span><div class="actions">${wizard&&state.step>0?'<button id="back">Back</button>':''}${wizard&&state.step<2?'<button class="primary" id="next">Continue →</button>':'<button class="primary" id="save">Save settings</button>'}</div></div>`;
 if(!wizard)body+=webLoginsPanel()+generatedLoginPanel()+indexerPanel()+wiringPanel()+'<div class="section-head"><h2>Configuration tools</h2></div><section class="panel"><div class="actions"><button id="test">Test saved connections</button><button id="export">Export configuration</button><button id="plan">Download install plan</button><button id="backup">Back up now</button><button id="support">Download support bundle</button></div><p class="hint">Connection wiring uses the target application schema and test endpoint, preserves existing entries, and records each result in the audit trail. Export contains server addresses and paths, but no credentials. Support bundles omit addresses, paths and media names too.</p><label for="import">Import a configuration for review (saved credentials remain unchanged)</label><input id="import" type="file" accept="application/json,.json"><p class="hint">Imported settings are staged for review. Use Save settings to apply them.</p></section>';
 return body;
}
function generatedLoginPanel(){
 const apps=[...(setupDeployment.web_login_apps||[]),...(setupDeployment.companion_login_apps||[])].filter(key=>state.config.integrations[key]?.enabled&&setupAppSelected(key));
 if(setupAppSelected('qbittorrent')&&state.credentials.includes('qbittorrent')&&setupDeployment.operations.some(op=>op.state==='needs-setup'))apps.push('qbittorrent');
 if(!setupDeployment.available||!apps.length)return '';
 return '<section class="panel"><details><summary>Your installed app logins</summary><p>Enter your Stackarr owner password to view one generated login for 60 seconds. It is hidden when you leave this page or switch tabs.</p>'+select('App login','generated-login-app',apps[0],apps.map(key=>[key,state.catalog[key].name]))+field('Stackarr owner password','generated-login-owner','','password','autocomplete="current-password"')+'<button id="generated-login-show">Show generated login</button><button id="generated-login-hide">Hide login</button><div id="generated-login-output" hidden></div></details></section>';
}
function wiringPanel(){
 const enabled=key=>state.config.integrations[key]?.enabled&&setupAppSelected(key);
 if(!(enabled('sonarr')||enabled('radarr'))||!(enabled('qbittorrent')||enabled('prowlarr')||enabled('seerr')||enabled('plex')))return '';
 const preview=state.wiringPreview,result=state.wiringResult;
 let body='<section class="panel"><h2>Connect your apps together</h2><p>Connect downloads, sources and Seerr requests. Stackarr checks successful imports and scans the matching Plex libraries automatically; Seerr checks for newly available titles. Keep Stackarr running for automatic discovery. You can close this browser window. Plex must finish matching before a title is ready to watch. Only enabled apps with saved credentials are included.</p><button id="wiring-preview">Preview app connections</button><div id="wiring-output" aria-live="polite">';
 if(preview){
  body+='<h3>Review these changes</h3>';
  if(preview.changes.length)body+='<ul>'+preview.changes.map(c=>`<li><strong>${escape(state.catalog[c.target]?.name||c.target)}</strong>: ${c.kind==='Plex availability schedule'?'update':'add'} ${escape(c.connection)} as a ${escape(c.kind)}.${c.detail?'<br>'+escape(c.detail):''}</li>`).join('')+'</ul><p>Connections are tested before saving, and schedule changes are checked afterward. Existing connections and custom schedules are preserved. Automatic removal of completed or failed downloads stays off; Prowlarr uses add-only synchronization.</p>';
  else body+='<p>No new connection changes are ready. Check any notices below.</p>';
  body+=preview.notices.map(n=>`<p>${escape(n)}</p>`).join('');
  if(preview.changes.length)body+='<button id="wiring-apply" class="primary">Apply reviewed changes</button>';
 }
 if(result)body+='<h3>Connection results</h3><ul>'+result.results.map(r=>`<li><strong>${escape(state.catalog[r.target]?.name||r.target)}</strong>: ${escape(r.state)}</li>`).join('')+'</ul><p>You can preview again to check for anything still missing.</p>';
 return body+'</div></section>';
}
function backupsScreen(){
 return heading('A way back.','Back up your Docker app settings and databases. Media stays in its existing folders.')+backupSchedulePanel()+dockerBackupsPanel()+helpPanel('backups')+'<section class="panel"><h2>Redacted Stackarr settings</h2><p>These separate settings drafts exclude credentials and app databases.</p><div class="actions"><button id="backup">Back up now</button><button id="load-backups">Refresh backup list</button></div><p class="hint">Checksums detect changed files. Preview a draft, review Settings, then save when ready.</p></section>'+(state.backupRows||[]).map(row=>`<section class="panel"><h2>${escape(row.file)}</h2><p>${escape(row.message)}</p><p>${escape(row.contents)}</p><p class="hint">Restore test: ${escape(row.restore_test)}</p><button data-preview-backup="${escape(row.file)}" ${row.verified?'':'disabled'}>Preview restored settings</button></section>`).join('');
}
function dockerBackupsPanel(){
 const installs=(setupDeployment.operations||[]).filter(op=>op.state==='needs-setup');
 if(!installs.length)return '';
 const saved=(state.dockerBackups||[]).map(row=>{
  const kind=({'scheduled':'Scheduled snapshot','before-restore':'Before-restore safety copy','before-update':'Update recovery snapshot','before-rollback':'Rollback safety snapshot','before-repair':'Before-repair safety copy','before-remove':'Before-removal safety copy','before-maintenance-recovery':'Before-recovery safety copy'})[row.kind]||'Saved snapshot';
  const action=['before-update','before-rollback'].includes(row.kind)?'<span class="hint">Use Apps → Updates & rollback to recover the matching image and data.</span>':`<button data-docker-restore="${escape(row.id)}" data-deployment="${escape(row.deployment)}">Review restore</button>`;
  return `<p>${row.apps.map(key=>escape(state.catalog[key]?.name||key)).join(' · ')} · ${escape(new Date(row.created*1000).toLocaleString())} · ${kind} · ${row.off_disk?'Verified copy on another disk':'Local snapshot'}${row.local_available===false?' · Local copy missing; restore uses the separate disk':''} ${action}</p>`;
 }).join('');
 return '<section class="panel"><h2>Docker app backups</h2><p>Encrypted snapshots include app databases, logins and settings. Running apps stop briefly, then restart. Media and download files are excluded and stay untouched. Use Automatic backups above to keep verified copies on another disk. Keep your recovery key separately. Media files need their own backup.</p>'+installs.map(op=>`<article><h3>${op.apps.map(key=>escape(state.catalog[key]?.name||key)).join(' · ')}</h3><button data-docker-backup="${escape(op.id)}">Review app backup</button></article>`).join('')+'<button id="docker-backups-refresh">Refresh Docker backups</button><div id="docker-backup-list">'+saved+'</div><div id="lifecycle-review" role="status"></div><h3>Maintenance results</h3><button id="lifecycle-refresh">Refresh actions</button><div id="lifecycle-history" role="status">'+lifecycleHistory()+'</div></section>';
}
function readForm(){let c=structuredClone(state.config);const value=id=>document.getElementById(id)?.value,checked=id=>document.getElementById(id)?.checked;let credentials={};for(const key of c.dashboard.order){if(value(key+'-mode')===undefined)continue;const a=c.integrations[key];a.enabled=checked(key+'-enabled');a.visible=checked(key+'-visible');a.mode=value(key+'-mode');a.port=Number(value(key+'-port'));a.url=value(key+'-url').trim();a.browser_url=value(key+'-browser').trim();a.peer_url=value(key+'-peer').trim();if(checked(key+'-clear'))credentials[key]=null;else if(value(key+'-key')||value(key+'-password'))credentials[key]={api_key:value(key+'-key')||'',username:value(key+'-user')||'',password:value(key+'-password')||''};}c=readSettingsFields(c);return {config:c,credentials};}
let stagedCredentials={};
function download(name,data){const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
function on(id,action){const el=document.getElementById(id);if(el)el.onclick=async()=>{el.disabled=true;try{await action();}catch(e){state.error=e.message;const main=document.querySelector('#main');if(main){let banner=main.querySelector('[data-action-error]');if(!banner){banner=document.createElement('div');banner.dataset.actionError='';banner.className='banner error';banner.setAttribute('role','alert');main.prepend(banner);}banner.textContent=e.message;}announce(e.message);}finally{el.disabled=false;}};}
function bind(){
 bindControlRoom();
 bindHome();
 bindSetup();
 bindNativeImports();
 bindQualityRules();
 bindPresets();
 bindCleanupPresets();
 bindMediaSetup();
 bindAccountSetup();
 bindSetupExtras();
 bindBackupPlan();
 bindStackarrUpdates();
 document.querySelectorAll('[data-finish-install]').forEach(button=>button.onclick=async()=>{
  if(state.dirty){announce('Save your changes before finishing connections.');return;}
  button.disabled=true;button.textContent='Checking your apps…';
  try{state.finishResults=await api('deployments/'+button.dataset.finishInstall+'/finish-connecting','POST',{});await load();render();announce('Connection check finished. Review the results.');}
  catch(e){const output=button.closest('.panel')?.querySelector('[role="status"]');if(output)output.textContent=e.message;announce(e.message);button.textContent='Finish connecting';button.disabled=false;}
 });
 clearTimeout(lifecycleTimer);
 on('lifecycle-refresh',refreshLifecycle);
 on('updates-refresh',async()=>{state.updateRows=await api('updates');render();});
 document.querySelectorAll('[data-update-review]').forEach(button=>button.onclick=async()=>{
  button.disabled=true;
  try{if(state.dirty)throw new Error('Save your settings before reviewing an update.');const review=await api('deployments/'+button.dataset.updateDeployment+'/update-review','POST',{app:button.dataset.updateApp,action:button.dataset.updateReview,...(button.dataset.updateId?{update:button.dataset.updateId}:{})});showManagedReview(review,review.name);}
  catch(e){document.getElementById('lifecycle-review').textContent=e.message;announce(e.message);}finally{button.disabled=false;}
 });
 if(['overview','health','apps','backups'].includes(state.view)&&(setupDeployment.actions||[]).some(row=>['queued','running'].includes(row.state)))lifecycleTimer=setTimeout(refreshLifecycle,1000);
 if(['health','settings'].includes(state.view))bindLifecycleReviews(root);
 on('docker-backups-refresh',async()=>{state.dockerBackups=(await api('app-backups')).backups;render();});
 document.querySelectorAll('[data-docker-backup],[data-docker-restore]').forEach(button=>button.onclick=async()=>{
  button.disabled=true;
  try{const restore=button.dataset.dockerRestore;const review=await api('deployments/'+(restore?button.dataset.deployment:button.dataset.dockerBackup)+'/backup-review','POST',{action:restore?'restore':'backup',...(restore?{backup:restore}:{})});showManagedReview(review,review.apps.join(' · '));}
  catch(e){announce(e.message);document.getElementById('lifecycle-review').textContent=e.message;}finally{button.disabled=false;}
 });
 on('generated-login-hide',async()=>hideGeneratedLogin());
 const loginChoice=document.getElementById('generated-login-app');if(loginChoice)loginChoice.onchange=hideGeneratedLogin;
 on('generated-login-show',async()=>{
  hideGeneratedLogin();
  const field=document.querySelector('#generated-login-owner'),password=field.value;field.value='';
  const key=document.getElementById('generated-login-app').value;
  const result=await api(key==='qbittorrent'?'deployments/qbittorrent/login':'apps/'+key+'/login','POST',{password});
  const output=document.querySelector('#generated-login-output');if(!output)return;
  const username=document.createElement('p');username.textContent='Username: '+result.username;
  const label=document.createElement('label');label.htmlFor='generated-login-password';label.textContent='Generated '+state.catalog[key].name+' password';
  const input=document.createElement('input');input.id='generated-login-password';input.readOnly=true;input.type='text';input.value=result.password;input.autocomplete='off';
  const copy=document.createElement('button');copy.textContent='Copy password';copy.onclick=async()=>{await navigator.clipboard.writeText(input.value);announce('Password copied.');};
  output.replaceChildren(username,label,input,copy);output.hidden=false;
  generatedLoginTimer=setTimeout(hideGeneratedLogin,60000);announce('Generated login shown for 60 seconds.');
 });
 on('refresh',async()=>{state.storageChecked=0;await api('refresh','POST',{});announce('Collection started. Each integration updates independently.');setTimeout(poll,800);});
 on('test',async()=>{await api('refresh','POST',{});state.view='health';state.notice='Testing saved connections. Results appear as each request completes.';render();setTimeout(poll,800);});
 on('wiring-preview',async()=>{if(state.dirty)throw new Error('Save your changes before reviewing app connections.');state.wiringResult=null;state.wiringPreview=await api('wiring/preview');state.wiringReview=state.wiringPreview.review_token;setupDeployment=await api('deployments');renderPreservingContext();announce(`${state.wiringPreview.changes.length} connection changes are ready for review.`);});
 on('wiring-apply',async()=>{
  if(state.dirty)throw new Error('Save your changes, then review connections again.');
  if(!state.wiringReview)throw new Error('Preview the connections before applying them.');
  const token=state.wiringReview;state.wiringReview=null;
  const button=document.querySelector('#wiring-apply');if(button)button.disabled=true;
  state.wiringResult=await api('wiring/apply','POST',{review_token:token});state.wiringPreview=null;setupDeployment=await api('deployments');render();
  const failed=state.wiringResult.results.some(r=>r.state.startsWith('failed'));
  announce(failed?'Some connections need attention. Review the results below.':'Connection setup finished. Review the results below.');
 });
 document.querySelectorAll('[data-check-install]').forEach(button=>button.onclick=async()=>{
  const output=document.getElementById('install-check-'+button.dataset.checkInstall);button.disabled=true;output.textContent='Checking installed containers…';
  try{const result=await api('deployments/'+button.dataset.checkInstall+'/check','POST',{});output.innerHTML='<p>Checked '+escape(new Date(result.checked_at*1000).toLocaleString())+'</p><ul>'+result.apps.map(app=>`<li><strong>${escape(app.name)} · ${escape(app.state)}</strong>: ${escape(app.detail)}${(app.actions||(app.state==='stopped'?['start']:['running','unhealthy'].includes(app.state)?['stop','restart']:[])).map(action=>` <button data-lifecycle-app="${escape(app.app)}" data-lifecycle-deployment="${escape(button.dataset.checkInstall)}" data-lifecycle-action="${action}" ${app.recovery?`data-lifecycle-operation="${escape(app.recovery)}"`:''}>Review ${action==='repair-recover'?'maintenance recovery':action} ${escape(app.name)}</button>`).join('')}</li>`).join('')+'</ul><p class="hint">'+escape(result.notice)+'</p>';bindLifecycleReviews(output);}
  catch(e){output.textContent=e.message;announce(e.message);}finally{button.disabled=false;}
 });
 on('next',()=>{const f=readForm();state.config=f.config;Object.assign(stagedCredentials,f.credentials);state.step++;render();});
 on('back',()=>{const f=readForm();state.config=f.config;Object.assign(stagedCredentials,f.credentials);state.step--;render();});
 on('save',async()=>{const f=readForm();const result=await api('config','PUT',{revision:state.revision,config:f.config,credentials:{...stagedCredentials,...f.credentials}});stagedCredentials={};state.error='';state.notice=result.message;await load();if(state.view==='onboarding')state.view='overview';render();schedule();await api('refresh','POST',{});});
 on('export',async()=>download('stackarr-config.json',await api('export')));
 on('support',async()=>download('stackarr-support.json',await api('support')));
 on('plan',async()=>download('stackarr-install-plan.json',await api('plan')));
 on('backup',async()=>{await api('backup','POST',{});announce('Redacted configuration backup created on your server.');if(state.view==='backups'){state.backupRows=await api('backups');render();}});
 on('load-backups',async()=>{state.backupRows=await api('backups');render();});
 document.querySelectorAll('[data-preview-backup]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{const result=await api('backups/'+button.dataset.previewBackup+'/preview','POST',{});state.config=result.config;state.view='settings';state.notice=result.message;render();state.dirty=true;}catch(e){announce(e.message);button.disabled=false;}});
 on('jobs',loadJobs);
 on('notification-status',loadNotifications);
 on('notification-test',async()=>{const result=await api('notifications/test','POST',{});announce(result.message);await loadNotifications();});
 on('audit',async()=>{document.querySelector('#audit-output').textContent=(await api('audit')).map(r=>`${new Date(r.time*1000).toLocaleString()}  ${r.app}  ${r.event}`).join('\n')||'No events yet.';});
 const imported=document.getElementById('import');if(imported)imported.onchange=async()=>{try{const file=imported.files[0];if(!file||file.size>131072)throw new Error('Choose a configuration under 128 KiB.');const result=await api('config/validate','POST',{config:JSON.parse(await file.text())});state.config=result.config;state.notice=result.message;render();state.dirty=true;}catch(e){announce(e.message);}};
 const filter=document.getElementById('filter');if(filter)filter.oninput=()=>{state.query=filter.value;state.pages={};refreshTables();};bindTable();
}
let lifecycleTimer;
function lifecycleHistory(){return '<div class="table-scroll"><table class="action-history"><thead><tr><th>Time</th><th>Status</th><th>Action / result</th></tr></thead><tbody>'+(setupDeployment.actions||[]).map(row=>`<tr><td>${escape(new Date(row.updated*1000).toLocaleString())}</td><td>${escape(row.state)}</td><td>${escape(row.message)}</td></tr>`).join('')+'</tbody></table></div>'+((setupDeployment.actions||[]).length?'':'<p>No app actions recorded.</p>');}
async function refreshLifecycle(){
 clearTimeout(lifecycleTimer);
 try{setupDeployment=await api('deployments');const output=document.getElementById('lifecycle-history');if(output)output.innerHTML=lifecycleHistory();
  state.actionSeen=state.actionSeen||{};
  for(const row of setupDeployment.actions||[]){if(state.actionSeen[row.id]&&state.actionSeen[row.id]!==row.state&& !['queued','running'].includes(row.state))announce(row.message);state.actionSeen[row.id]=row.state;}
  if((setupDeployment.actions||[]).some(row=>['queued','running'].includes(row.state)))lifecycleTimer=setTimeout(refreshLifecycle,2000);
 }catch(e){announce('App actions could not be refreshed. Retrying…');lifecycleTimer=setTimeout(refreshLifecycle,5000);}
}

function bindLifecycleReviews(container){
 container.querySelectorAll('[data-lifecycle-app]').forEach(button=>button.onclick=async()=>{
  button.disabled=true;const output=document.getElementById('lifecycle-review');
  try{const review=await api('deployments/'+button.dataset.lifecycleDeployment+'/apps/'+button.dataset.lifecycleApp+'/review','POST',{action:button.dataset.lifecycleAction,...(button.dataset.lifecycleOperation?{operation:button.dataset.lifecycleOperation}:{})});if(!output.isConnected)return;
   showManagedReview(review,review.name);
  }catch(e){if(output.isConnected)output.textContent=e.message;announce(e.message);}finally{button.disabled=false;}
 });
}
function showManagedReview(review,name,target='lifecycle-review'){
 const output=document.getElementById(target);
 output.innerHTML='<h3>Review '+escape(review.action)+' · '+escape(name)+'</h3>'+(review.target_version?'<p>'+escape(review.current_version)+' → '+escape(review.target_version)+'</p>':'')+'<p>'+escape(review.notice)+'</p><div class="actions"><button id="lifecycle-apply" class="primary">'+escape(({backup:'Create backup',restore:'Restore snapshot',start:'Start app',stop:'Stop app',restart:'Restart app',repair:'Repair app',remove:'Remove app, keep settings','repair-recover':'Recover maintenance',update:'Update app',rollback:'Roll back app','update-recover':'Recover app',companions:'Set up companions'})[review.action])+'</button><button id="lifecycle-cancel">Cancel</button></div>';
 document.getElementById('lifecycle-cancel').onclick=()=>output.replaceChildren();
 document.getElementById('lifecycle-apply').onclick=async event=>{event.target.disabled=true;try{const submitted=await api('deployments/actions/apply','POST',{review_token:review.review_token});if(submitted.id){state.actionSeen=state.actionSeen||{};state.actionSeen[submitted.id]='queued';}output.replaceChildren();announce(review.action==='companions'?'Companion setup queued. Follow its status in Setup or Health.':'App action queued. Its result will appear in Health.');const previous=document.getElementById('install-check-'+review.deployment);if(previous)previous.textContent='Check this installation again for current status.';await refreshLifecycle();}catch(e){output.textContent=e.message;announce(e.message);}};
 output.scrollIntoView({block:'nearest'});document.getElementById('lifecycle-apply').focus();
}
async function loadNotifications(){
 const rows=await api('notifications'),output=document.querySelector('#notification-output');if(!output)return;
 output.textContent=rows.map(row=>`${state.catalog[row.app]?.name||row.app}: ${row.state} · ${row.delivery} · ${row.attempts}/3 attempts${row.delivery==='pending'?' · next check '+new Date(row.next_attempt*1000).toLocaleTimeString():''}`).join('\n')||'No deliveries yet. Enable notifications in Settings to use a webhook.';
}
async function loadJobs(){
 const rows=await api('jobs'),output=document.querySelector('#jobs-output');if(!output)return;
 output.innerHTML=rows.map(row=>`<article><h3>Connection check · ${escape(row.state)}</h3><p>${escape(row.message)}</p><p class="hint">${escape(new Date(row.updated*1000).toLocaleString())} · Attempt ${row.attempts} · Reference ${escape(row.id)}</p>${row.state==='queued'?`<button data-cancel-job="${escape(row.id)}">Cancel waiting check</button>`:''}</article>`).join('')||'<p>No operations yet. Use Refresh status to check your apps.</p>';
 output.querySelectorAll('[data-cancel-job]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{await api('jobs/'+button.dataset.cancelJob+'/cancel','POST',{});await loadJobs();}catch(e){announce(e.message);button.disabled=false;}});
}
function refreshTables(){
 const tables=document.getElementById('tables');if(!tables)return;
 const context=captureContext(tables);
 tables.innerHTML=tableBodies(state.view==='health'?['health','blocklist','monitoring']:['downloads','queue','streams','requests','sources']);
 bindTable();restoreContext(context,tables,{focus:true});
}
function bindTable(){document.querySelectorAll('[data-sort]').forEach(b=>b.onclick=()=>{state.ascending=state.sort===b.dataset.sort?!state.ascending:true;state.sort=b.dataset.sort;refreshTables();});document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>{state.pages[b.dataset.page]+=Number(b.dataset.direction);refreshTables();});}
function refreshErrorBanner(){
 const main=document.getElementById('main');if(!main||!root.querySelector('.shell'))return;
 let banner=document.getElementById('status-refresh-error');
 if(!state.refreshError){banner?.remove();return;}
 if(!banner){banner=document.createElement('div');banner.id='status-refresh-error';banner.className='banner error';banner.setAttribute('role','status');main.prepend(banner);}
 banner.textContent=state.refreshError;
}
function refreshStatusRegions(){
 const x=window.scrollX,y=window.scrollY;
 refreshErrorBanner();
 const selectors=({overview:['#overview-summary','#overview-stats','#overview-apps'],activity:['#tables'],health:['#health-apps','#tables']})[state.view];
 if(!selectors||!root.querySelector('.shell'))return;
 const template=document.createElement('template');template.innerHTML=content();
 selectors.forEach(selector=>{
  const current=root.querySelector(selector),next=template.content.querySelector(selector);if(!current||!next)return;
  const selection=window.getSelection();
  // Leave controls and selected text mounted until the reader moves away.
  if(current.contains(document.activeElement)||(selection&&!selection.isCollapsed&&(current.contains(selection.anchorNode)||current.contains(selection.focusNode))))return;
  const context=captureContext(current);current.replaceChildren(...next.childNodes);restoreContext(context,current);
 });
 bindTable();bindControlRoom();
 window.scrollTo(x,y);
}
let timer,pollPromise,scheduleGeneration=0;
function stopSchedule(){clearTimeout(timer);scheduleGeneration++;}
async function poll(){
 if(state.stackarrRemovalPending||!root.querySelector('.shell'))return;
 if(pollPromise)return pollPromise;
 pollPromise=(async()=>{try{state.status=await api('status');state.refreshError='';if((state.config.dashboard.overview_widgets||defaultWidgets).includes('storage')&&Date.now()-(state.storageChecked||0)>60000){try{state.storageOverview=await api('overview/storage');state.storageChecked=Date.now();}catch{state.storageOverview={available:false,message:'Storage capacity is temporarily unavailable.'};}}}catch(e){state.refreshError='Status refresh failed. Displayed data may be stale. '+e.message;}refreshStatusRegions();})();
 try{await pollPromise;}finally{pollPromise=null;}
}
function schedule(){
 stopSchedule();if(state.stackarrRemovalPending||!root.querySelector('.shell'))return;
 const generation=scheduleGeneration,seconds=Number(state.config.dashboard.refresh_seconds);
 timer=setTimeout(async()=>{await poll();if(generation===scheduleGeneration)schedule();},(Number.isFinite(seconds)?Math.max(10,seconds):30)*1000);
}
let bootGeneration=0;
async function boot(){const generation=++bootGeneration;try{try{state.publicAppearance=await api('appearance');}catch{}theme();await receiveSetupHandoff();const session=await api('session');if(generation!==bootGeneration)return;localLauncher=!!session.local_launcher;launcherApproved=!!session.setup_approved;if(!session.authenticated){auth(session.setup_required);return;}state.csrf=session.csrf;await load();state.view=initialView();if(generation!==bootGeneration)return;render();schedule();}catch(e){if(generation!==bootGeneration)return;root.innerHTML='<main class="auth-form" id="main"><div><h1>Stackarr is unavailable.</h1><p>'+escape(e.message)+'</p><button id="retry">Try again</button></div></main>';document.querySelector('#retry').onclick=boot;}}
boot();
