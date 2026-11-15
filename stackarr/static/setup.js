'use strict';
let setupDraft = null;
let setupChecks = [];
let setupStorage = null;
let setupDeployment = {available:false,operations:[]};
let setupInstallReview = null;
let setupConnectionReview = null;
let setupInstallTimer = null;
const setupInstallable=new Set(['plex','sonarr','radarr','prowlarr','qbittorrent','seerr','tautulli','kuma','cleanuparr']);
let setupFolders=null;
let setupPortResults=null;
let setupRuntime=null;
let setupInstallPortsReview=null;
let setupDiscovery=null;
const setupDescriptions = {
 seerr:'Let your household discover and request media. Permissions stay in Seerr.',
 plex:'Watch your own movies and TV on your home network.',
 sonarr:'Organize TV series and follow downloads through to import.',
 radarr:'Organize movies and follow downloads through to import.',
 prowlarr:'Manage the sources you choose for Sonarr and Radarr.',
 qbittorrent:'Download files and track progress.',
 tautulli:'See Plex viewing activity and stream details.',
 kuma:'Monitor whether your services are available.',
 cleanuparr:'Optional download filtering and cleanup. Starts in preview mode with protection jobs off; it is not an antivirus.'
};
async function loadSetup(){
 setupDraft=await api('onboarding');
 setupChecks=await api('onboarding/readiness');
 setupStorage=await api('onboarding/storage');
 setupDeployment=await api('deployments');
 await loadNativeImports();
 await loadSetupFolderChoice();
 if(setupDeployment.operations.some(op=>op.state==='ports-blocked'&&op.apps.every(key=>setupDraft.draft.apps.includes(key)))&&setupDeployment.available){try{setupPortResults=(await api('onboarding/check-ports','POST',{})).ports;}catch{/* Keep saved progress when host checks are unavailable. */}}
}
function setupEditor(){
 if(!setupDraft)return heading('Set up your media server.','Loading your saved setupâ€¦');
 const d=setupDraft.draft;
 const installedKeys=new Set(setupDeployment.operations.filter(op=>op.state==='needs-setup').flatMap(op=>op.apps||[]));
 const installed=d.step===2&&installedKeys.size>0&&d.apps.every(k=>d.choices?.[k]?.mode==='connect'||installedKeys.has(k)||state.config.integrations[k].enabled);
 let html=heading(installed?'Finish setup for movie night.':'Set up your media server.',installed?'Follow your next step below. Your progress is saved here.':'Choose what you need. Your progress is saved when you continue.');

 html+=setupReconnectPanel();


 if(setupDeployment.controller==='unavailable')html+='<section class="banner"><strong>Installation connection lost.</strong><p>Progress below is the last status checked with the installation computer. Reopen Stackarr there, then check progress before trying an install or resume again.</p></section>';
 else if(setupDeployment.controller==='busy')html+='<section class="banner"><strong>Installation computer is busy.</strong><p>Progress below is the last checked status. Stackarr will check again shortly.</p></section>';
 else if(!setupDeployment.available&&!installed)html+='<section class="banner"><strong>App installation is not ready in this Docker preview.</strong><p>You can save your choices and connect apps you already have. Installing new apps will need the installation connection; there is no file to download or command to run to finish it here.</p></section>';
 if(!installed)html+='<ol class="steps" aria-label="Setup progress">'+['Choose apps','Choose storage','Review & set up'].map((name,i)=>`<li ${i===d.step?'aria-current="step"':''} class="${i===d.step?'current':''}">${i+1} Â· ${name}</li>`).join('')+'</ol>';
 if(installed)html+='<details class="panel"><summary>Review saved installation choices</summary>';
 if(d.step===0){
  if(setupDeployment.host_checks||setupDeployment.controller==='connected')html+='<section class="panel"><h2>Already have Plex or other apps?</h2><p>Find apps on this computer before installing more. Choose a result to keep that app and its settings. Credentials are added after reviewing your choices.</p><button id="setup-discover">Find existing apps</button><div id="setup-discovery-result" role="status">'+setupDiscoveryPanel()+'</div></section>';
  if(setupDeployment.host_checks||setupDeployment.controller==='connected')html+='<section class="panel"><h2>Check this computer</h2><p>New apps need Docker. This check only reads its status; it does not install software or start Docker.</p><button id="setup-check-runtime">Check Docker</button><div id="setup-runtime-result" role="status">'+runtimeSummary()+'</div></section>';
  html+='<section class="panel" id="setup-apps" tabindex="-1"><h2>What would you like to do?</h2><div class="actions"><button data-preset="plex">Watch my media</button><button class="primary" data-preset="automation">Movies & TV Â· recommended</button><button data-preset="monitoring">Monitoring only</button><button data-preset="custom">Choose my own</button></div><p class="hint">Find movies & follow TV includes Plex for watching and Seerr for requests, plus the apps that find, download and organize your media. Sources may need their own account. You can change every app below.</p></section>';
  html+='<details id="setup-custom-apps" class="panel"><summary>Customize apps or connect existing apps</summary><div class="cards">'+Object.keys(setupDescriptions).map(key=>{
   const choice=d.choices?.[key]||{mode:setupInstallable.has(key)?'install':'connect',url:'',port:0};
   const name=state.catalog[key].name;
   return `<section class="card">${check(name,'setup-'+key,d.apps.includes(key))}<p>${escape(setupDescriptions[key])}</p>${installedKeys.has(key)?'<p class="hint">Already installed by Stackarr. Its existing settings will be kept.</p>':setupInstallable.has(key)?'':'<p class="hint">Connect an existing installation. Guided installation for this app is not available yet.</p>'}<div id="setup-choice-${key}" ${d.apps.includes(key)?'':'hidden'}>${select(name+' setup','setup-mode-'+key,choice.mode,setupInstallable.has(key)?[['install','Install a new app'],['connect','Connect an existing app']]:[['connect','Connect an existing app']])}<div id="setup-address-${key}" ${choice.mode==='connect'?'':'hidden'}>${field(name+' address','setup-url-'+key,choice.url)}<p class="hint">Use its API address, without a password or API key. Existing apps remain independently managed.</p></div></div></section>`;
  }).join('')+'</div></details>';
  html+='<p id="setup-experience-summary" role="status">'+(d.apps.length?d.apps.length+' apps selected. Continue to choose your media folder and quality.':'Choose Movies & TV for finding, downloading and watching in one place.')+'</p>';
  html+=setupPorts(d);
  html+='<p class="hint">Leave an app unchecked to skip it. Credentials and connection verification follow separately in Apps; this draft does not connect or change existing apps.</p>';
 }else if(d.step===1){
  const needsStorage=d.apps.some(k=>['plex','sonarr','radarr','qbittorrent'].includes(k)&&d.choices?.[k]?.mode!=='connect');
  if(needsStorage){
   html+=setupMediaFolder(d);
   html+=storagePreview();
   html+=setupLibraryChoices(d);
  }else html+='<section class="panel"><h2>No media folder needed</h2><p>These apps can use their own storage. Existing apps keep the folders they already use.</p><input type="hidden" id="setup-folder" value="'+escape(d.data_root)+'"><div id="setup-host-result" role="status"></div></section>';
  if(setupDeployment.host_checks)html+='<details class="panel"><summary>Installation checks</summary><p>Stackarr checks storage and ports again before installing.</p><button id="setup-check-host">Check this computer</button></details>';

 }else{
  html+='<section class="panel"><h2>Your choices</h2><ul>'+d.apps.map(k=>`<li>${escape(state.catalog[k].name)} Â· ${d.choices?.[k]?.mode==='connect'?'connect existing: '+escape(d.choices[k].url)+' (not verified)':'new installation'}</li>`).join('')+'</ul><p>Data folder: '+escape(d.data_root||'Not needed for these choices')+'</p>'+setupQualitySummary(d)+'<p>New apps will initially be available on this computer. Your existing apps keep their settings.</p></section>';
 }
 if(d.step===2&&!installed&&d.apps.some(k=>d.choices?.[k]?.mode!=='connect')&&!setupDeployment.available&&!['unavailable','busy'].includes(setupDeployment.controller))html+='<section class="panel"><h2>Saved choices â€” installation still needed</h2><p>This preview cannot install these apps yet. Save and finish later to keep your choices. Nothing has been downloaded or installed.</p></section>';
 if(installed)html+='</details>';
 if(d.step===2&&d.apps.some(k=>d.choices?.[k]?.mode==='connect')){
  html+='<section class="panel"><h2>Connect the apps you already have</h2><p>Save these addresses in Stackarr, then add credentials in Apps. This does not install, adopt or change settings inside existing apps.</p><button id="setup-connect-review">Review existing app connections</button>';
  if(setupConnectionReview){
   html+='<ul>'+setupConnectionReview.changes.map(c=>`<li>${escape(c.name)} Â· ${escape(c.address)}</li>`).join('')+'</ul>'+setupConnectionReview.notices.map(n=>`<p>${escape(n)}</p>`).join('');
   if(setupConnectionReview.changes.length)html+='<button id="setup-connect-apply" class="primary">Save reviewed app addresses</button>';
   else html+='<p>There are no new addresses to save. Use Apps to review configured apps.</p>';
  }
  html+='</section>';
 }



 if(d.step===2&&setupDeployment.available&&!installed&&d.apps.some(k=>d.choices?.[k]?.mode!=='connect')){
  html+='<section class="panel"><h2>Install on this computer</h2><p>Docker must already be installed and running. The installer creates separate app configuration and keeps existing deployments untouched.</p><button id="setup-install-review">Review installation</button>';
  if(setupInstallReview)html+='<div role="status"><p>'+escape(setupInstallReview.notice)+'</p><ul>'+setupInstallReview.apps.map(a=>`<li>${escape(a.name)} Â· local port ${escape(a.port)}</li>`).join('')+'</ul><p>Media folder: '+escape(setupInstallReview.media_folder||'Not needed')+'</p>'+ (setupInstallReview.create_folders?.length?'<p>Create missing folders only: '+setupInstallReview.create_folders.map(escape).join(', ')+'. Existing files stay in place.</p>':'')+(setupInstallReview.library_setup?.length?'<p>Set up the matching TV and movie library folders in the new Sonarr/Radarr apps. No media is added or downloaded.</p>':'')+'<button id="setup-install-apply" class="primary">Download & install these apps</button></div>';
  html+=setupInstallQualitySummary(setupInstallReview||{})+'</section>';
 }
 if(setupDeployment.operations.length)html+='<section class="panel"><h2>'+(setupDeployment.status_stale?'Last known installation progress':'Installation progress')+'</h2>'+(setupDeployment.status_stale&&setupDeployment.last_checked?'<p>Last checked '+escape(new Date(setupDeployment.last_checked*1000).toLocaleString())+'. The current state is unknown until the connection returns.</p>':'')+setupDeployment.operations.map(op=>`<article><h3>${escape(({queued:'Waiting to start',running:'Setting up your apps','needs-setup':'Apps installed â€” finish setup',failed:'Installation needs attention',interrupted:'Installation paused','ports-blocked':'Choose free ports',superseded:'Earlier attempt replaced'})[op.state]||'Checking installation')}</h3><p role="status">${escape(op.message)}</p>${(op.links||[]).map(link=>`<p><a href="${escape(link.url)}" target="_blank" rel="noopener noreferrer">Open ${escape(state.catalog[link.app]?.name||link.app)}</a> Â· ${setupDeployment.status_stale?'last known address':'available on this computer'}</p>`).join('')}${setupDeployment.available&&['failed','interrupted'].includes(op.state)?`<button data-install-resume="${escape(op.id)}">${op.phase==='downloading'?'Retry download':'Resume installation'}</button>`:''}${installPortRecoveryButtons(op)}</article>`).join('')+'<button id="setup-install-refresh">Check progress</button>'+(setupDeployment.available&&setupDeployment.operations.some(op=>['failed','interrupted'].includes(op.state))?'<button id="setup-recheck-docker">Check Docker again</button><div id="setup-progress-runtime" role="status">'+runtimeSummary()+'</div>':'')+'</section>';
 html+=installPortRecoveryPanel()+setupPortRecovery()+`<div class="setup-actions"><span role="status" id="setup-message">Your choices are saved</span><div class="actions"><button id="setup-pause">Save & finish later</button>${d.step&&!installed?'<button id="setup-back">Back</button>':''}${d.step<2?'<button id="setup-next" class="primary">Save & continue â†’</button>':installed?'<button id="setup-complete" class="primary">Open Home â†’</button>':'<button id="setup-done" class="primary">Save choices & open Home</button>'}</div></div><div id="setup-error" class="banner error" role="alert" hidden></div>`;
 return html;
}
function setupTaskGroup(id,label,body,actions){
 if(!body)return '';
 const current=actions.includes(setupDeployment.journey?.next_action?.id);
 return '<details class="panel setup-task-group" id="setup-group-'+id+'"'+(current?' open':'')+'><summary>'+escape(label)+(current?' Â· your next step':'')+'</summary>'+body+'</details>';
}
function setupNextSteps(){
 const installedKeys=new Set(setupDeployment.operations.filter(op=>op.state==='needs-setup').flatMap(op=>op.apps||[]));
 const apps=Object.entries(state.config.integrations).filter(([key,app])=>app.enabled&&installedKeys.has(key)&&setupAppSelected(key));
 return (apps.length?'<details class="panel"><summary>App links and technical setup details</summary><p>Your apps are installed. Follow the checklist above, or open an app directly below.</p><ul>'+apps.map(([key,app])=>{
  const arrLogin=setupDeployment.controller==='connected'?'Use your generated login below. ':'Choose your web login in the app. ';
  const instructions={plex:'Manage this server and its libraries with your Plex account.',seerr:'Request movies and TV in Seerr. Preview app connections to add Sonarr and Radarr without copying keys.',sonarr:arrLogin+'Your TV library folder is ready at /data/media/tv.',radarr:arrLogin+'Your movie library folder is ready at /data/media/movies.',prowlarr:arrLogin+'Choose your sources.',qbittorrent:'Stackarr has saved a generated login for monitoring and app connections.',tautulli:'Review companion setup in Stackarr to connect the owned Docker Plex server and create a generated login.',kuma:'Review companion setup to create a generated login and monitor your owned apps.',cleanuparr:'Review companion setup to connect the owned Arr/downloader apps in dry-run with all automatic jobs disabled.'};
  return `<li>${appLink(browserAppUrl(key))} Â· ${escape(instructions[key]||'Review this applicationâ€™s setup.')}</li>`;
 }).join('')+'</ul><p>Use connection settings to connect these apps to Stackarr. Test the saved connections when you are ready.</p><div class="actions"><button id="setup-settings">Open connection settings</button><button id="test">Test saved connections</button></div></details>':'')+setupTaskGroup('accounts','Sign in and connect your accounts',finishConnectingPanel()+webLoginsPanel()+generatedLoginPanel(),['accounts','finish-connecting'])+setupTaskGroup('sources','Choose where downloads come from',indexerPanel(),['source-setup','source-validation','source-check'])+setupTaskGroup('connections','Connect requests, downloads and your library',wiringPanel()+mediaSetupPanel(),['wiring-preview','test-connections'])+setupTaskGroup('companions','Optional companion apps',companionsPanel(),['companion-review']);
}
function runtimeSummary(){
 if(!setupRuntime)return 'Not checked yet. Connecting existing apps does not require Docker.';
 return '<p><strong>'+({ready:'Docker is ready', 'needs-attention':'Docker needs attention', 'not-checked':'Check Docker on the installation computer'}[setupRuntime.state]||'Check Docker again')+'</strong></p><ul>'+setupRuntime.checks.map(row=>'<li>'+escape(row.detail)+'</li>').join('')+'</ul><p>'+escape(setupRuntime.notice)+'</p>'+(setupRuntime.network_capacity?'<p class="hint">'+escape(setupRuntime.network_capacity.notice)+'</p><p><a href="https://docs.docker.com/engine/network/#subnet-allocation" target="_blank" rel="noopener noreferrer">Docker network capacity guide â†—</a></p>':'')+(setupRuntime.guide?'<p><a href="https://docs.docker.com/desktop/setup/install/windows-install/" target="_blank" rel="noopener noreferrer">Open the Docker installation guide â†—</a></p>':'');
}
function storagePreview(){
 const s=setupStorage;if(!s?.required||!s.valid)return '';
 const names=s.folders.map(f=>escape(f.purpose)).join(', ');
 return '<section class="panel"><h2>Your media folders</h2><p>'+names+'. Stackarr creates missing folders and leaves existing files in place.</p>'+(setupDeployment.folder_browser&&setupDeployment.controller!=='connected'?'<button id="setup-create-folders">Create missing media folders</button>':'<p class="hint">Folders are created when you approve installation.</p>')+'<p id="setup-folder-result" role="status"></p><details><summary>See folder locations</summary><ul>'+s.folders.map(f=>'<li>'+escape(f.purpose)+': '+escape(f.host)+'</li>').join('')+'</ul></details></section>';
}
const setupPortOrder=['plex','qbittorrent','sonarr','radarr','prowlarr','cleanuparr','seerr','tautulli','kuma'];
const setupBasePort=28000;
async function showSetupFolders(rootIndex=null,relative=''){
 const result=await api('onboarding/folders'+(rootIndex===null?'':'?root='+rootIndex+'&relative='+encodeURIComponent(relative)));

 const box=document.getElementById('setup-folder-browser');
 box.innerHTML='<section aria-label="Choose a media folder"><h3>'+escape(result.host_path||'Shared media folders')+'</h3><div class="actions">'+(result.roots?result.roots.map(r=>`<button data-folder-root="${r.id}">${escape(r.name)}</button>`).join(''):'<button id="setup-folder-up">Back</button><button id="setup-folder-select" class="primary">Use this folder</button>')+'</div><ul>'+(result.folders||[]).map(f=>`<li><button data-folder-relative="${escape(f.relative)}">${escape(f.name)}</button></li>`).join('')+'</ul>'+(!result.roots&&!result.folders.length?'<p>No subfolders. You can use this folder.</p>':'')+'<p id="setup-folder-error" role="alert"></p></section>';
 const navigate=async(index,path='')=>{try{await showSetupFolders(index,path);}catch(e){document.getElementById('setup-folder-error').textContent=e.message;}};
 box.querySelectorAll('[data-folder-root]').forEach(b=>b.onclick=()=>navigate(Number(b.dataset.folderRoot)));
 box.querySelectorAll('[data-folder-relative]').forEach(b=>b.onclick=()=>navigate(result.root,b.dataset.folderRelative));
 const up=document.getElementById('setup-folder-up');if(up)up.onclick=()=>result.relative?navigate(result.root,result.relative.split('/').slice(0,-1).join('/')):navigate(null);
 const choose=document.getElementById('setup-folder-select');if(choose)choose.onclick=async()=>{
  document.getElementById('setup-folder').value=result.host_path;
  updateSetupFolderDisplay(result.host_path);state.dirty=true;
  if(setupDeployment.controller==='connected'){
   setupDraft.draft.folder_root=result.root;
   setupDraft.draft.folder_relative=result.relative;
  }
  try{setupDraft=await api('onboarding','PUT',{revision:setupDraft.revision,draft:setupForm()});setupStorage=await api('onboarding/storage');state.dirty=false;render();}catch(e){document.getElementById('setup-folder-error').textContent=e.message;}
 };
}
function setupForm(){
 const d=structuredClone(setupDraft.draft);
 if(d.step===0){
  d.port_mode=document.getElementById('setup-port-mode').value;
  d.apps=Object.keys(setupDescriptions).filter(k=>document.getElementById('setup-'+k).checked);
  d.choices=Object.fromEntries(d.apps.map(k=>[k,{
   ...d.choices?.[k],
   mode:document.getElementById('setup-mode-'+k).value,
   url:document.getElementById('setup-url-'+k).value.trim(),
   browser_url:document.getElementById('setup-url-'+k).value.trim()===d.choices?.[k]?.url?(d.choices[k].browser_url||''):'',
   port:Number(document.getElementById('setup-port-'+k).value||0),
   quality_profile:document.getElementById('setup-mode-'+k).value==='install'?(d.choices?.[k]?.quality_profile||''):''
  }]));
 }
 if(d.step===1){
  d.data_root=document.getElementById('setup-folder').value.trim();if(setupSuggestedFolder?.host_path===d.data_root){d.folder_root=setupSuggestedFolder.root;d.folder_relative=setupSuggestedFolder.relative;}
  for(const key of ['sonarr','radarr']){const quality=document.getElementById('setup-quality-'+key);if(quality)d.choices[key]={...d.choices[key],quality_profile:quality.value==='other'?document.getElementById('setup-quality-other-'+key).value:quality.value};}
 }
 return d;
}
function bindSetup(){
 if(state.view!=='setup'||!setupDraft)return;

 for(const key of ['sonarr','radarr']){const quality=document.getElementById('setup-quality-'+key);if(quality)quality.addEventListener('change',()=>{document.getElementById('setup-quality-other-wrap-'+key).hidden=quality.value!=='other';state.dirty=true;});}
 const action=(id,fn)=>{
  const button=document.getElementById(id);if(!button)return;
  button.onclick=async()=>{
   const controls=[...document.querySelectorAll('.content button')],disabled=controls.map(b=>b.disabled);controls.forEach(b=>b.disabled=true);
   try{await fn();}catch(e){const error=document.getElementById('setup-error');if(error){error.hidden=false;error.textContent=e.message;}announce(e.message);}
   finally{controls.forEach((b,index)=>{b.disabled=disabled[index];});}
  };
 };
 const persist=async step=>{
  setupInstallReview=null;setupConnectionReview=null;
  const d=setupForm();d.step=step;
  setupDraft=await api('onboarding','PUT',{revision:setupDraft.revision,draft:d});
  state.dirty=false;
  setupChecks=await api('onboarding/readiness');
 setupStorage=await api('onboarding/storage');
 setupDeployment=await api('deployments');
 };
 action('setup-check-runtime',async()=>{setupRuntime=await api('onboarding/runtime-check','POST',{});setupDeployment=await api('deployments');renderPreservingContext();});
 action('setup-recheck-docker',async()=>{setupRuntime=await api('onboarding/runtime-check','POST',{});render();});
 action('setup-install-ports-apply',async()=>{await api('deployments/actions/apply','POST',{review_token:setupInstallPortsReview.review_token});setupInstallPortsReview=null;await load();render();});
 document.querySelectorAll('[data-install-port-review]').forEach(button=>{button.onclick=async()=>{button.disabled=true;try{setupInstallPortsReview=await api('deployments/'+button.dataset.installPortReview+'/ports/review','POST',{});render();document.getElementById('setup-install-ports-apply').focus();}catch(e){announce(e.message);const error=document.getElementById('setup-error');error.hidden=false;error.textContent=e.message;button.disabled=false;}};});
 action('setup-connect-review',async()=>{setupConnectionReview=await api('onboarding/connections/review','POST',{});render();});
 action('setup-connect-apply',async()=>{const result=await api('onboarding/connections/apply','POST',{review_token:setupConnectionReview.review_token});state.focusIntegration=setupConnectionReview.changes[0]?.app;setupConnectionReview=null;setupInstallReview=null;await load();state.notice=result.message;state.view='settings';state.settingsSection='connections';render();});
 action('setup-browse-shared',async()=>{const folders=await api('onboarding/folders');await showSetupFolders(folders.roots?.length===1?folders.roots[0].id:null);});
 action('setup-choose-folder',async()=>{if(!setupDeployment.folder_picker&&setupDeployment.folder_browser){await showSetupFolders();return;}announce('Choose your media folder in the Windows folder dialog.');const result=await api('onboarding/choose-folder','POST',{});if(result.cancelled){document.getElementById('setup-host-result').textContent='Folder choice cancelled. Your previous folder is unchanged.';return;}setupSuggestedFolder=null;document.getElementById('setup-folder').value=result.path;if(setupDeployment.controller==='connected'){setupDraft.draft.folder_root=result.root;setupDraft.draft.folder_relative=result.relative;}await persist(setupDraft.draft.step);await loadSetupFolderChoice();render();});
 action('setup-fix-ports',async()=>{await persist(setupDraft.draft.step);await chooseSetupPorts();await loadSetup();render();});
 action('setup-install-review',async()=>{setupInstallReview=null;if(setupDraft.draft.port_mode==='automatic')await chooseSetupPorts();setupPortResults=(await api('onboarding/check-ports','POST',{})).ports;if(setupPortResults.some(row=>row.status!=='available')){render();throw new Error('Choose available ports, then review installation again.');}setupInstallReview=await api('deployments/review','POST',{});render();});
 action('setup-install-apply',async()=>{
  try{await api('deployments/install','POST',{review_token:setupInstallReview.review_token});}
  catch(e){
   setupInstallReview=null;
   try{setupDeployment=await api('deployments');if(!setupDeployment.operations.some(op=>['queued','running'].includes(op.state)))setupPortResults=(await api('onboarding/check-ports','POST',{})).ports;render();}catch{ /* Keep the error from the install request. */ }
   throw e;
  }
  setupInstallReview=null;setupDeployment=await api('deployments');
  announce('Installation queued. You can follow its saved progress here.');render();
 });
 action('setup-install-refresh',async()=>{await load();render();});
 action('setup-add-app',async()=>{
  setupDraft=await api('onboarding','PUT',{revision:setupDraft.revision,
   draft:{...setupDraft.draft,step:0,apps:[],choices:{},port_mode:'automatic'}});
  setupPortResults=null;setupPortNotice='';
  setupInstallReview=null;
  await loadSetup();render();
 });
 action('setup-complete',async()=>{await load();state.view='home';state.notice='';render();});
 action('setup-settings',async()=>{await load();state.view='apps';render();});
 document.querySelectorAll('[data-install-resume]').forEach(button=>{
  button.onclick=async()=>{
   button.disabled=true;
   try{await api('deployments/'+button.dataset.installResume+'/resume','POST',{});setupDeployment=await api('deployments');render();}
   catch(e){announce(e.message);const error=document.getElementById('setup-error');error.hidden=false;error.textContent=e.message;button.disabled=false;}
  };
 });
 clearTimeout(setupInstallTimer);
 const pollInstallation=async()=>{
  if(state.view!=='setup'||state.dirty||(!document.getElementById('setup-install-refresh')&&!['unavailable','busy'].includes(setupDeployment.controller)))return;
  try{setupDeployment=await api('deployments');if(state.view!=='setup'||state.dirty)return;if(!['unavailable','busy'].includes(setupDeployment.controller)&&!setupDeployment.operations.some(op=>['queued','running'].includes(op.state)))await load();if(state.view==='setup'&&!state.dirty)renderPreservingContext();}
  catch(e){announce('Progress temporarily unavailable. Reconnecting; installation progress is saved.');setupInstallTimer=setTimeout(pollInstallation,5000);}
 };
 if(['unavailable','busy'].includes(setupDeployment.controller)||setupDeployment.operations.some(op=>['queued','running'].includes(op.state)))setupInstallTimer=setTimeout(pollInstallation,['unavailable','busy'].includes(setupDeployment.controller)?5000:2000);
 const updateChoices=()=>Object.keys(setupDescriptions).forEach(k=>{
  document.getElementById('setup-choice-'+k).hidden=!document.getElementById('setup-'+k).checked;
  const connecting=document.getElementById('setup-mode-'+k).value==='connect';
  document.getElementById('setup-address-'+k).hidden=!connecting;
  document.getElementById('setup-port-row-'+k).hidden=connecting||!document.getElementById('setup-'+k).checked;
  document.getElementById('setup-port-status').textContent='Ports changed. Check again before installing.';
 });
 if(setupDraft.draft.step===0&&document.getElementById('setup-auto-ports')){
  document.getElementById('setup-auto-ports').onchange=event=>{document.getElementById('setup-port-mode').value=event.target.checked?'automatic':'custom';document.getElementById('setup-ports-advanced').open=!event.target.checked;document.getElementById('setup-port-mode').dispatchEvent(new Event('change'));};
  document.getElementById('setup-port-mode').onchange=()=>{
   const mode=document.getElementById('setup-port-mode').value;
   document.getElementById('setup-auto-ports').checked=mode==='automatic';setupPortResults=null;setupPortNotice='';
   setupPortOrder.forEach((k,i)=>{const input=document.getElementById('setup-port-'+k),label=document.getElementById('setup-port-label-'+k);if(mode!=='custom')input.value=mode==='defaults'?state.catalog[k].port:setupBasePort+1+i;input.hidden=mode!=='custom';label.hidden=mode==='custom';label.textContent=input.value;});
   state.dirty=true;document.getElementById('setup-port-status').textContent='Ports changed. Check again before installing.';
  };
 }
 if(setupDraft.draft.step===0&&document.getElementById('setup-auto-ports'))Object.keys(setupDescriptions).forEach(k=>{
  if(setupDeployment.operations.some(op=>op.state==='needs-setup'&&(op.apps||[]).includes(k))){
   document.getElementById('setup-'+k).disabled=true;
   document.getElementById('setup-mode-'+k).disabled=true;
  }
  document.getElementById('setup-'+k).addEventListener('change',updateChoices);
  document.getElementById('setup-mode-'+k).addEventListener('change',updateChoices);
 });
 document.querySelectorAll('[data-preset]').forEach(button=>button.onclick=()=>{
  state.dirty=true;
  const selected={plex:['plex'],automation:['plex','sonarr','radarr','prowlarr','qbittorrent','seerr'],monitoring:['kuma'],custom:[]}[button.dataset.preset];
  Object.keys(setupDescriptions).forEach(k=>{const box=document.getElementById('setup-'+k);if(!box.disabled)box.checked=selected.includes(k);});
  updateChoices();
  document.getElementById('setup-custom-apps').open=button.dataset.preset==='custom';
  document.getElementById('setup-experience-summary').textContent=selected.length+' apps selected. Continue to choose your media folder and quality.';
  document.getElementById('setup-message').textContent='Choices changed Â· continue to save';
 });
 action('setup-next',async()=>{
  const step=setupDraft.draft.step;
  await persist(step);
  if(step===0&&!setupDraft.draft.apps.length)throw new Error('Choose at least one app, or save and finish later.');
  if(step===0&&setupDraft.draft.port_mode==='automatic'&&setupDraft.draft.apps.some(k=>setupDraft.draft.choices[k].mode==='install')&&setupDeployment.available)await chooseSetupPorts();
  if(step===0&&!setupDeployment.available){const draft=setupDraft.draft,ports=draft.apps.filter(k=>draft.choices[k].mode==='install').map(k=>draft.choices[k].port||state.catalog[k].port);if(new Set(ports).size!==ports.length||ports.some(port=>port<1||port>65535)||ports.includes(Number(location.port||(location.protocol==='https:'?443:80))))throw new Error('Give each new app a different port between 1 and 65535, separate from this Stackarr dashboard.');}
  if(step===0&&setupDeployment.available&&setupDraft.draft.apps.some(k=>setupDraft.draft.choices[k].mode==='install')){setupPortResults=(await api('onboarding/check-ports','POST',{})).ports;if(setupPortResults.some(row=>row.status!=='available')){render();throw new Error('Choose available ports to continue. Existing services are unchanged.');}}
  if(step===1&&setupDeployment.available)await api('onboarding/plan');
  await persist(step+1);await loadSetupFolderChoice();render();
 });
 action('setup-back',async()=>{await persist(setupDraft.draft.step-1);render();});
 action('setup-discover',async()=>{
  await persist(setupDraft.draft.step);
  setupDiscovery=await api('onboarding/discover','POST',{});
  render();
 });
 document.querySelectorAll('[data-discovered-app]').forEach(button=>button.onclick=async()=>{
  button.disabled=true;
  try{
   const result=setupDiscovery?.results[Number(button.dataset.discoveredApp)];
   if(!result||setupDeployment.operations.some(op=>op.state==='needs-setup'&&op.apps.includes(result.app)))return;
   const draft=setupUseDiscovered(setupForm(),result);
   setupDraft=await api('onboarding','PUT',{revision:setupDraft.revision,draft});
   state.dirty=false;setupInstallReview=null;setupConnectionReview=null;
   await loadSetup();render();
   document.getElementById('setup-message').textContent='Existing app selected. Continue to review and add its credentials.';
  }catch(e){announce(e.message);document.getElementById('setup-error').hidden=false;document.getElementById('setup-error').textContent=e.message;}
  finally{if(button.isConnected)button.disabled=false;}
 });
 action('setup-check-host',async()=>{
  await persist(setupDraft.draft.step);
  const result=await api('onboarding/host-check','POST',{});
  const output=document.getElementById('setup-host-result');
  output.innerHTML='<h3>'+ (result.scope==='connection-only'?'No installation needed':result.preflight_passed?'Local preflight passed':'Host check needs attention')+'</h3>'+result.checks.map(c=>`<p><strong>${escape(c.check)} Â· ${c.ok?'passed':'needs attention'}</strong><br>${escape(c.detail)}</p>`).join('')+'<p class="hint">'+escape(result.limitations.join(' '))+'</p>';
  document.getElementById('setup-message').textContent='Draft saved Â· checks apply to these saved choices';
 });
 const folder=document.getElementById('setup-folder');
 if(folder)folder.oninput=()=>{document.getElementById('setup-host-result').textContent='Folder changed. Save and check again.';};
 action('setup-pause',async()=>{await persist(setupDraft.draft.step);await load();state.view='home';state.notice='Your setup draft is saved. Use Setup to return.';render();});
 action('setup-done',async()=>{await persist(setupDraft.draft.step);await load();state.view='home';state.notice='Your setup choices are saved. Use Setup to continue.';render();});
 action('setup-create-folders',async()=>{await persist(setupDraft.draft.step);const result=await api('onboarding/prepare-folders','POST',{revision:setupDraft.revision});document.getElementById('setup-folder-result').textContent=result.message;});
 action('setup-check-ports',async()=>{await persist(0);const result=await api('onboarding/check-ports','POST',{});setupPortResults=result.ports;render();document.getElementById('setup-port-status').textContent=result.ports.map(r=>r.name+' '+r.port+': '+r.status).join(' Â· ')+'. '+result.notice;});
}
