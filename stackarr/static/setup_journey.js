'use strict';

const setupCheckpointLabels={done:'Checked', 'needs-action':'Needs a step', 'in-progress':'In progress', unknown:'Not verified', stale:'Check again'};

function setupAppSelected(key){return state.setupAllApps||state.view!=='setup'||!setupDraft||setupDraft.draft.apps.includes(key);}

function setupJourneyPanel(){
 const journey=setupDeployment.journey;
 if(!journey||journey.draft_revision!==setupDraft.revision)return '';
 const next=journey.next_action;
 const current=journey.checkpoints.find(row=>row.id===next?.checkpoint_id);
 return '<section class="panel setup-journey" id="setup-journey-panel" aria-labelledby="setup-journey-title">'+
  '<p class="eyebrow">YOUR SETUP PROGRESS</p><h2 id="setup-journey-title">'+escape(current?.title||'Review your setup')+'</h2>'+
  '<p id="setup-journey-detail">'+escape(current?.detail||'Your saved choices and checks are listed below.')+'</p>'+
  (next?'<button class="primary" id="setup-journey-next">'+escape(next.label)+'</button>':'')+
  '<details id="setup-journey-checklist"><summary>See setup checklist · '+journey.summary.done+' of '+journey.summary.total+' checked</summary>'+
  '<ol class="setup-checklist">'+journey.checkpoints.map(row=>'<li data-checkpoint="'+escape(row.id)+'"'+(row.id===next?.checkpoint_id?' aria-current="step"':'')+'><div><strong>'+escape(row.title)+'</strong><span class="pill" data-checkpoint-state="'+escape(row.state)+'">'+escape(setupCheckpointLabels[row.state]||'Not verified')+'</span></div><p>'+escape(row.detail)+'</p></li>').join('')+'</ol></details>'+
  '<p class="hint">Connection checks confirm that apps respond. Finding a copy, importing it and playing it need their own checks.</p></section>';
}

function setupVerificationPanel(){
 const row=setupDeployment.journey?.checkpoints.find(item=>item.id==='verification');
 if(!row)return '';
 const selected=new Set(setupDeployment.journey.selected_apps);
 const plex=state.config.integrations.plex;
 const seerr=state.config.integrations.seerr;
 const watching=selected.has('plex')&&plex?.enabled;
 const requesting=selected.has('seerr')&&seerr?.enabled;
 const requestWorkflow=selected.has('seerr');
 const importing=selected.has('sonarr')||selected.has('radarr');
 return '<section class="panel" id="setup-verification" tabindex="-1"><h2>Try your viewing journey</h2><p>'+escape(row.detail)+'</p><ol>'+
  (requestWorkflow?'<li>Open Home, search for a movie or show, choose its download quality and request it. For TV, choose the seasons you want.</li>':importing?'<li>Use a permitted sample to try the search, download and import flow for the movie or TV apps you selected.</li>':'<li>Add a sample you already own to your selected media folder and check that it appears in Plex.</li>')+
  (importing?'<li>Open Your requests to follow progress. Once the title is available, open it and choose Open in Plex.</li>':'')+
  (watching?'<li>Play the sample in Plex, then try your usual TV or phone with audio and subtitles.</li>':'')+
  '</ol><p class="hint">This preview does not automatically certify playback, home-network access or restart behavior. These checks remain unverified here.</p><div class="actions">'+
  (requesting?'<button class="primary" data-view="home">Find your first movie or show →</button><button data-view="requests">Your requests</button>':'')+
  (watching?appLink(browserAppUrl('plex')):'')+'</div></section>';
}

function setupReconnectPanel(){
 if(setupDeployment.available||!setupDraft.draft.apps.some(key=>setupDraft.draft.choices?.[key]?.mode!=='connect'))return '';
 return '<section class="panel" id="setup-reconnect" tabindex="-1"><h2>Reconnect to the installation computer</h2><p>Open Start Stackarr on the computer where you want to install your apps. Keep Docker Desktop running there, then return here and check the connection.</p><p>Your saved choices and any existing apps stay in place. This page cannot install apps without the private installation connection.</p><button id="setup-journey-reconnect">Check installation connection</button></section>';
}

function focusSetupTarget(element){
 if(!element)return false;
 for(let parent=element.parentElement;parent;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;
 element.scrollIntoView({block:'nearest'});
 if(!element.matches('button,input,select,a,[tabindex]'))element.setAttribute('tabindex','-1');
 element.focus({preventScroll:true});
 return true;
}

async function setupJourneyStep(step){
 if(setupDraft.draft.step===step)return;
 setupDraft=await api('onboarding','PUT',{revision:setupDraft.revision,draft:{...setupDraft.draft,step}});
 await loadSetup();render();
}

async function runSetupAction(target){
 if(!target?.isConnected||target.disabled){announce('This check is already running. Wait for its result.');return;}
 focusSetupTarget(target);
 if(typeof target.onclick==='function')await target.onclick();
 else target.click();
}

function bindSetupJourney(){
 const reconnect=document.getElementById('setup-journey-reconnect');
 if(reconnect)reconnect.onclick=async()=>{reconnect.disabled=true;try{await load();renderPreservingContext();focusSetupTarget(document.getElementById(setupDeployment.available?'setup-journey-panel':'setup-reconnect'));}catch(error){announce(error.message);}finally{if(reconnect.isConnected)reconnect.disabled=false;}};
 const button=document.getElementById('setup-journey-next');
 if(!button)return;
 button.onclick=async()=>{
  const action=setupDeployment.journey?.next_action;
  if(!action)return;
  if(state.dirty){announce('Save your current choices before continuing the checklist.');focusSetupTarget(document.getElementById('setup-next')||document.getElementById('setup-pause'));return;}
  button.disabled=true;
  try{
   if(action.id==='choose-apps'){await setupJourneyStep(0);focusSetupTarget(document.getElementById('setup-apps'));return;}
   if(action.id==='choose-storage'){await setupJourneyStep(1);focusSetupTarget(document.getElementById('setup-choose-folder')||document.getElementById('setup-storage'));return;}
   if(action.id==='check-runtime'){await setupJourneyStep(0);const target=document.getElementById('setup-check-runtime');if(target)await runSetupAction(target);else focusSetupTarget(document.getElementById('setup-reconnect'));return;}
   if(action.id==='review-install'){await setupJourneyStep(2);const target=document.getElementById('setup-install-review');if(target)await runSetupAction(target);else focusSetupTarget(document.getElementById('setup-reconnect'));return;}
   if(action.id==='accounts'){if(['plex','seerr'].includes(action.app)&&document.getElementById('setup-accounts')){focusSetupTarget(document.getElementById('setup-accounts'));return;}state.focusIntegration=action.app;await load();state.view='apps';render();focusSetupTarget(document.getElementById((action.app||'plex')+'-enabled'));return;}
   if(action.id==='check-progress'){await load();renderPreservingContext();focusSetupTarget(document.getElementById('setup-journey-panel'));return;}
   if(action.id==='verification'){await setupJourneyStep(2);focusSetupTarget(document.getElementById('setup-verification'));return;}
   if(action.id==='reconnect-installation'){focusSetupTarget(document.getElementById('setup-reconnect'));return;}
   if(['source-setup','source-validation'].includes(action.id)){
    if(!document.getElementById('indexer-setup')){await load();state.view='apps';render();}
    if(action.id==='source-validation'){
     const type=document.getElementById('indexer-validation-type');if(type&&action.media_type)type.value=action.media_type;
     focusSetupTarget(document.getElementById('indexer-validation-query')||document.getElementById('indexer-setup'));
    }else{
     const target=document.getElementById('indexer-load-providers');
     if(target)await runSetupAction(target);
     focusSetupTarget(document.getElementById('indexer-provider')||document.getElementById('indexer-setup'));
    }
    return;
   }
   let target;
   if(action.id==='finish-connecting'&&['plex','seerr'].includes(action.app)&&!state.credentials.includes(action.app)){focusSetupTarget(document.getElementById('setup-account-'+action.app)||document.getElementById('setup-accounts'));return;}
   if(action.id==='finish-connecting')target=[...document.querySelectorAll('[data-finish-install]')].find(item=>!action.installation||item.dataset.finishInstall===action.installation);
   else if(action.id==='companion-review')target=[...document.querySelectorAll('[data-companions-review]')].find(item=>!action.installation||item.dataset.companionsReview===action.installation);
   else if(action.id==='resume-install')target=[...document.querySelectorAll('[data-install-resume]')].find(item=>!action.installation||item.dataset.installResume===action.installation);
   else if(['source-check','wiring-preview','test-connections'].includes(action.id))target=document.getElementById(action.target);
   if(!target&&['source-check','wiring-preview','test-connections'].includes(action.id)){await load();state.view='apps';render();target=document.getElementById(action.target);}
   if(target)await runSetupAction(target);
   else{announce('Use the setup tools below to complete this check.');focusSetupTarget(document.getElementById('setup-journey-panel'));}
  }catch(error){announce(error.message);const output=document.getElementById('setup-error');if(output){output.hidden=false;output.textContent=error.message;}}
  finally{if(button.isConnected)button.disabled=false;}
 };
}
