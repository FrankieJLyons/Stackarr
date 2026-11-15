'use strict';
function companionsPanel(){
 const installs=(setupDeployment.operations||[]).filter(op=>op.state==='needs-setup'&&(op.apps||[]).some(key=>['tautulli','kuma','cleanuparr'].includes(key)&&setupAppSelected(key)));
 if(!installs.length)return '';
 return '<section class="panel"><h2>Connect your companion apps</h2><p>One reviewed step creates private local logins, links Tautulli to Docker Plex and adds availability monitors in Uptime Kuma. Cleanuparr connects in dry-run mode with every automatic job off. It has no access to your media folders.</p>'+installs.map(op=>`<button data-companions-review="${escape(op.id)}">Review companion setup</button>`).join('')+'<div id="companion-setup-review" role="status"></div></section>';
}
function webLoginsPanel(){
 const ids=(setupDeployment.login_setup||[]).filter(id=>state.view!=='setup'||setupDeployment.operations.some(op=>op.id===id&&(op.apps||[]).some(key=>['sonarr','radarr','prowlarr'].includes(key)&&setupAppSelected(key))));
 if(!ids.length)return '';
 const review=state.webLoginReview,result=state.webLoginResult;
 return '<section class="panel"><h2>Your Arr app logins</h2><p>New apps get their own generated login. Stackarr keeps it private so you do not need to invent and remember three more passwords. Existing app logins stay yours.</p>'+ids.map(id=>`<button data-review-logins="${escape(id)}">Review app login setup</button>`).join('')+(review?'<div role="status"><p>'+escape(review.notice)+'</p><p>'+review.apps.map(a=>escape(a.name)).join(', ')+'</p><button id="web-logins-apply" class="primary">Prepare and save app logins</button></div>':'')+(result?'<ul role="status">'+result.apps.map(a=>'<li><strong>'+escape(a.name)+'</strong>: '+escape(a.detail)+'</li>').join('')+'</ul>':'')+'</section>';
}
function indexerProvider(){return (state.indexerCatalog?.providers||[]).find(provider=>provider.id===state.indexerProvider&&provider.supported);}
function indexerProviderFieldId(provider,index){return 'indexer-provider-field-'+encodeURIComponent(provider.id)+'-'+index;}
function indexerProviderFields(provider){
 return (provider.fields||[]).map((item,index)=>{
  const id=indexerProviderFieldId(provider,index),help=id+'-help';
  const label=escape(item.label)+(item.required?' (required)':'');
  const attributes=(item.required?' required':'')+' aria-describedby="'+help+'"';
  let input;
  if(item.type==='select')input='<select id="'+escape(id)+'"'+attributes+'><option value="">Choose an option</option>'+(item.options||[]).map(option=>'<option value="'+escape(option.value)+'">'+escape(option.label)+'</option>').join('')+'</select>';
  else if(item.type==='checkbox')input='<input id="'+escape(id)+'" type="checkbox"'+attributes+'>';
  else input='<input id="'+escape(id)+'" type="'+(item.private||item.type==='password'?'password':item.type==='number'?'number':'text')+'" value="" autocomplete="'+(item.private||item.type==='password'?'new-password':'off')+'"'+attributes+'>';
  return '<div class="field"><label for="'+escape(id)+'">'+label+'</label>'+input+'<p class="hint" id="'+help+'">'+escape(item.help|| (item.private?'Get this from your content provider account. Keep it private.':'Use the details supplied by this provider.'))+'</p></div>';
 }).join('');
}
function indexerCatalogPanel(){
 const catalog=state.indexerCatalog,provider=indexerProvider();
 if(!catalog)return '<button id="indexer-load-providers" class="primary">Choose my source provider</button>';
 const providers=(catalog.providers||[]).filter(item=>item.supported);
 const body='<p class="hint">'+escape(catalog.notice||'These forms come from your connected Prowlarr app. Choose a provider you already use.')+'</p>'+
  (providers.length?'<div class="field"><label for="indexer-provider">Your source provider</label><select id="indexer-provider" data-setup-control="navigation"><option value="">Choose your provider</option>'+providers.map(item=>'<option value="'+escape(item.id)+'"'+(item.id===state.indexerProvider?' selected':'')+'>'+escape(item.name)+(item.privacy==='private'?' · account required':'')+'</option>').join('')+'</select></div>':'<p>No guided provider forms are available from this Prowlarr version. Use Advanced provider setup below.</p>')+
  (provider?'<div id="indexer-provider-details"><h3>'+escape(provider.name)+'</h3><p>'+ (provider.privacy==='private'?'This provider needs its own account. Use the provider’s account details here.':'Use your provider’s account or key if its form requires one.')+' Your Plex and Stackarr sign-ins are separate. Prowlarr checks the details it requires before saving.</p><div class="form-grid">'+field('Name in your source list','indexer-provider-name',provider.name,'text','required maxlength="80" autocomplete="off"')+indexerProviderFields(provider)+'</div><div class="actions"><button id="indexer-provider-connect" class="primary">Test & connect source</button><button id="indexer-reset">Clear entered details</button></div><details><summary>Review before connecting</summary><button id="indexer-provider-review">Review source details</button></details></div>':'');
 return state.indexerReview||state.indexerResult?'<details id="indexer-provider-editor"><summary>'+(state.indexerResult?'Add another source':'Change these source details')+'</summary>'+body+'</details>':body;
}
function indexerSharingPanel(checked){
 if(!checked)return '';
 const sources=checked.sources||[],apps=(checked.apps||[]).filter(app=>setupAppSelected(app.app));
 const enabled=sources.filter(source=>source.enabled);
 const sharingKnown=app=>Number.isInteger(app.shared_sources)&&app.shared_sources>=0&&app.state!=='unavailable';
 return '<div role="status" id="indexer-sharing-result"><h3>Source sharing</h3>'+(!sources.length?'<p>No sources added yet. Choose your provider above, review its details, then test and connect it.</p>':'<ul>'+sources.map(source=>'<li>'+escape(source.name)+' · '+(source.enabled?'enabled':'disabled — enable it in Prowlarr before searching')+'</li>').join('')+'</ul>')+
  apps.map(app=>'<p>'+escape(app.name)+': '+(sharingKnown(app)?app.shared_sources+' source(s) shared from Prowlarr.':'sharing is unavailable. Check this app’s saved connection, then check sharing again.')+'</p>').join('')+
  (apps.some(app=>!sharingKnown(app))?'<p><button class="linklike" id="indexer-test-connections">Test saved app connections</button> to find which app needs reconnecting.</p>':'')+
  (enabled.length&&apps.some(app=>sharingKnown(app)&&app.shared_sources===0)?'<p>If you just added this source, wait a moment and check sharing again. If it stays missing, <button class="linklike" id="indexer-review-connections">Review app connections</button> to share compatible sources with your movie and TV apps.</p>':'')+
  (enabled.length?'<p class="hint">Sharing confirms configuration. Test a title below to check authentication, categories and search results.</p>':'')+'</div>';
}
function indexerValidationPanel(){
 const result=state.indexerValidation;
 const selected=['radarr','sonarr'].filter(key=>setupAppSelected(key)&&state.config.integrations[key]?.enabled);
 if(!selected.length)return '';
 const options=selected.map(key=>'<option value="'+(key==='radarr'?'movie':'tv')+'">'+(key==='radarr'?'Movie':'TV show')+'</option>').join('');
 const headings={results:'Search results found','no-matches':'Sources responded, but no matching copy was found','needs-attention':'A source needs attention','not-configured':'No enabled sources to test'};
 const sourceStates={results:'Results found','no-matches':'No matching copy','authentication-failed':'Provider sign-in or key rejected','test-failed':'Connection test failed','search-failed':'Search unavailable','category-missing':'Movie or TV category missing',unverified:'Not fully verified',disabled:'Disabled','not-tested':'Not tested in this check'};
 return '<details id="indexer-validation"'+(result?' open':'')+'><summary>Test a movie or TV search</summary><p>Enter a title you may obtain from your provider. This only tests your sources; it does not request or download anything. A title in Seerr’s catalog does not guarantee a downloadable copy.</p><div class="form-grid">'+field('Title to look for','indexer-validation-query','','text','required minlength="2" maxlength="120" data-setup-control="navigation" autocomplete="off"')+'<div class="field"><label for="indexer-validation-type">Search for</label><select id="indexer-validation-type" data-setup-control="navigation">'+options+'</select></div></div><button id="indexers-validate">Test source search</button>'+
  (result?'<div id="indexer-validation-result" role="status"><h3>'+escape(headings[result.state]||'Search not verified')+'</h3>'+(state.indexerValidationFor?'<p>'+(state.indexerValidationFor.media_type==='tv'?'TV':'Movie')+' search for “'+escape(state.indexerValidationFor.query)+'”.</p>':'')+'<p>'+escape(result.notice)+'</p><ul>'+(result.sources||[]).map(source=>'<li><strong>'+escape(source.name)+'</strong>: '+escape(sourceStates[source.state]||'Not verified')+(source.result_count===null||source.result_count===undefined?'':' · '+Number(source.result_count)+' result(s)')+'<p>'+escape(source.detail)+'</p></li>').join('')+'</ul>'+(result.limited?'<p class="hint">This bounded check did not test every source. Sources marked “Not tested” are still unverified.</p>':'')+
  (result.state==='results'?'<p>Next: return to your setup checklist and review app connections. Then try a permitted movie and an episode through requesting, downloading, importing and playback.</p>':result.state==='no-matches'?'<p>Try another title or spelling, check the release date, or choose another source. Your working connection does not need to be replaced because one search had no matches.</p>':'')+'</div>':'')+'</details>';
}
function indexerPanel(){
 const app=state.config.integrations.prowlarr;
 if(!setupAppSelected('prowlarr')||!app?.enabled||!state.credentials.includes('prowlarr'))return '';
 if(app.read_only)return '<section class="panel" id="indexer-setup"><h2>Your existing sources</h2><p>Prowlarr was imported in read-only mode. Its sources and linked apps stay in the original installation. Add or test sources there.</p>'+appLink(browserAppUrl('prowlarr'))+'<div class="actions"><button id="indexers-check">Check source sharing</button></div>'+indexerSharingPanel(state.indexerStatus)+'</section>';
 const review=state.indexerReview,result=state.indexerResult,checked=state.indexerStatus,plex=state.config.integrations.plex;
 const shared=checked?.sources?.some(source=>source.enabled)&&['radarr','sonarr'].filter(key=>setupAppSelected(key)&&state.config.integrations[key]?.enabled).every(key=>checked.apps?.some(row=>row.app===key&&row.shared_sources>0));
 return '<section class="panel" id="indexer-setup" tabindex="-1"><h2>Where will your media come from?</h2><p><strong>Already have movie or TV files?</strong> Add them to your chosen library folders. You can watch existing files without a download source.'+(setupAppSelected('plex')&&plex?.enabled?' '+appLink(browserAppUrl('plex')):'')+'</p>'+
  '<h3>Find new movies and episodes</h3><p>A content source tells your apps which copies are available. Some providers need a separate account or subscription and a provider key. Have those details ready; Stackarr connects your apps without asking you to copy their private API keys.</p>'+indexerCatalogPanel()+
  '<div id="indexer-error" role="alert">'+escape(state.indexerError||'')+'</div>'+
  '<div id="indexer-review-result" role="status">'+(review?'<h3>Review this source</h3><p>'+escape(review.name)+(review.provider?' · '+escape(review.provider):review.feed_url?' · '+escape(review.feed_url):'')+'</p><p>'+escape(review.notice)+'</p>'+(review.already_exists?'<p>An existing source will be preserved. Check its sharing below.</p>':'<button id="indexer-apply" class="primary">Test and connect source</button>'):'')+'</div>'+
  (result?'<p role="status">'+escape(result.detail)+'</p>':'')+
  (shared&&state.config.integrations.seerr?.enabled&&state.credentials.includes('seerr')?'<p>Your source is shared with the selected movie and TV apps.</p><button class="primary" data-view="home">Find a movie or show →</button>':'')+
  '<div class="actions"><button id="indexers-check">Check source sharing</button></div>'+indexerSharingPanel(checked)+indexerValidationPanel()+
  '<details id="indexer-advanced"><summary>Advanced provider setup</summary><p>This guided path uses torrent sources with qBittorrent. Other source types, such as Usenet, need a compatible download app configured separately.</p><p>If your provider’s form is not supported here, '+appLink(browserAppUrl('prowlarr'))+', then return to check source sharing.</p><details id="indexer-torznab"><summary>Connect an existing Torznab feed</summary><p>Use this only if your provider supplies a Torznab feed address. Enter its address without query parameters and put its provider key in the private field.</p><div class="form-grid">'+field('Source name','indexer-name','','text','required maxlength="80" autocomplete="off"')+field('Torznab feed address','indexer-url','','url','required placeholder="https://provider.example/api"')+field('Provider key (if required)','indexer-key','','password','autocomplete="new-password"')+'</div><div class="actions"><button id="indexer-review">Review source</button><button id="indexer-torznab-reset">Clear entered details</button></div></details></details></section>';
}
function bindSetupExtras(){
 const action=(id,fn)=>{const button=document.getElementById(id);if(button)button.onclick=async()=>{
  const sourceAction=id.startsWith('indexer');
  if(sourceAction&&state.indexerBusy){announce('A source check is already running. Wait for its result.');return;}
  button.disabled=true;if(sourceAction){state.indexerBusy=true;state.indexerError='';const output=document.getElementById('indexer-error');if(output)output.textContent='';}
  try{await fn();}catch(e){
   if(sourceAction){state.indexerError=e.message;renderPreservingContext();const output=document.getElementById('indexer-error');if(output)output.textContent=e.message;}
   else{state.error=e.message;renderPreservingContext();}
   announce(e.message);
  }finally{button.disabled=false;if(sourceAction)state.indexerBusy=false;}
 };};
 document.querySelectorAll('[data-companions-review]').forEach(button=>button.onclick=async()=>{
  if(state.dirty){announce('Save changes before reviewing companion setup.');return;}
  button.disabled=true;
  try{const review=await api('deployments/'+button.dataset.companionsReview+'/companions-review','POST',{});showManagedReview(review,'Companion apps','companion-setup-review');}catch(e){state.error=e.message;render();}
 });
 document.querySelectorAll('[data-review-logins]').forEach(button=>button.onclick=async()=>{
  if(state.dirty){announce('Save changes before reviewing app logins.');return;}
  button.disabled=true;
  try{state.webLoginReview=await api('deployments/'+button.dataset.reviewLogins+'/logins/review','POST',{});render();}catch(e){state.error=e.message;render();}
 });
 action('web-logins-apply',async()=>{
  if(state.dirty)throw new Error('Save changes and review app logins again.');
  const token=state.webLoginReview?.review_token;state.webLoginReview=null;
  state.webLoginResult=await api('app-logins/apply','POST',{review_token:token});await load();render();
 });
 const checkSources=async()=>{state.indexerStatus=null;setupDeployment={...setupDeployment,journey:null};try{state.indexerStatus=await api('indexers/status');}catch(error){setupDeployment=await api('deployments');throw error;}setupDeployment=await api('deployments');};
 const requireSavedSource=()=>{if(state.dirty)throw new Error('Review or clear your source details, and save any app changes, before running another check.');};
 const clearReview=()=>{state.indexerEditGeneration=(state.indexerEditGeneration||0)+1;state.indexerReview=null;state.indexerResult=null;const output=document.getElementById('indexer-review-result');if(output)output.replaceChildren();};
 const clearSourceDirty=()=>{state.indexerDirty=false;state.dirty=Boolean(state.appDirty);};
 const acceptSourceReview=(review,generation,revision)=>{
  if(generation!==state.indexerEditGeneration||revision!==state.revision||state.appDirty||state.indexerDirty){
   state.indexerReview=null;announce('Details changed while the source review was running. Your edits are kept. Review the current details again.');return false;
  }
  state.indexerReview=review;render();return true;
 };
 const validFields=ids=>{
  for(const id of ids){const input=document.getElementById(id);if(input&&!input.reportValidity())return false;}
  return true;
 };
 const providerSelect=document.getElementById('indexer-provider');
 if(providerSelect)providerSelect.onchange=event=>{
  event.stopImmediatePropagation();
  if(state.dirty){providerSelect.value=state.indexerProvider||'';announce('Review or clear entered source details, and save app changes, before choosing another provider.');return;}
  state.indexerProvider=providerSelect.value;clearReview();state.indexerError='';render();
 };
 document.querySelectorAll('#indexer-provider-details input,#indexer-provider-details select,#indexer-torznab input').forEach(input=>{
  input.addEventListener('input',clearReview);input.addEventListener('change',clearReview);
 });
 for(const id of ['indexer-validation-query','indexer-validation-type']){
  const input=document.getElementById(id);
  if(input)input.addEventListener('input',()=>{state.indexerValidationGeneration=(state.indexerValidationGeneration||0)+1;state.indexerValidation=null;state.indexerValidationFor=null;document.getElementById('indexer-validation-result')?.remove();});
 }
 action('indexer-load-providers',async()=>{requireSavedSource();state.indexerCatalog=await api('indexers/catalog');renderPreservingContext();});
 const resetSource=async()=>{
  document.querySelectorAll('#indexer-provider-details input,#indexer-provider-details select,#indexer-torznab input').forEach(input=>{input.value='';if(input.type==='checkbox')input.checked=false;});
  clearReview();clearSourceDirty();announce('Entered source details cleared. Choose a provider or enter the details again.');
 };
 action('indexer-reset',resetSource);action('indexer-torznab-reset',resetSource);
 const prepareProvider=async(connect=false)=>{
  if(state.appDirty)throw new Error('Save your app settings before reviewing a source.');
  const provider=indexerProvider();if(!provider)throw new Error('Choose a supported source provider first.');
  const ids=['indexer-provider-name',...(provider.fields||[]).map((_,index)=>indexerProviderFieldId(provider,index))];
  if(!validFields(ids))return;
  const fields=Object.create(null);
  (provider.fields||[]).forEach((item,index)=>{
   const input=document.getElementById(indexerProviderFieldId(provider,index)),value=input.value;
   if(input.type==='checkbox')fields[item.name]=input.checked;
   else if(value!==''||item.required){
    if(item.type==='select')fields[item.name]=(item.options||[]).find(option=>String(option.value)===value)?.value;
    else fields[item.name]=input.type==='number'?Number(value):value;
   }
   if(item.private||item.type==='password')input.value='';
  });
  const payload={provider_id:provider.id,name:document.getElementById('indexer-provider-name').value.trim(),fields};
  clearReview();clearSourceDirty();const generation=state.indexerEditGeneration,revision=state.revision;
  const review=await api('indexers/providers/review','POST',payload);
  const accepted=acceptSourceReview(review,generation,revision);
  if(connect&&accepted)await connectReviewedSource();
 };
 action('indexer-provider-review',()=>prepareProvider(false));
 action('indexer-provider-connect',()=>prepareProvider(true));
 action('indexers-check',async()=>{requireSavedSource();await checkSources();renderPreservingContext();});
 action('indexer-review-connections',async()=>{
  requireSavedSource();const target=document.getElementById('wiring-preview');if(!target)throw new Error('Open app connection settings to review source sharing.');
  if(typeof runSetupAction==='function')await runSetupAction(target);else{target.scrollIntoView({block:'nearest'});target.focus();if(!target.disabled&&typeof target.onclick==='function')await target.onclick();}
 });
 action('indexer-test-connections',async()=>{
  requireSavedSource();
  if(!document.getElementById('test')){state.view='apps';render();}
  const target=document.getElementById('test');if(!target)throw new Error('Open Apps and test the saved connection for the unavailable app.');
  if(typeof runSetupAction==='function')await runSetupAction(target);else{target.scrollIntoView({block:'nearest'});target.focus();if(!target.disabled&&typeof target.onclick==='function')await target.onclick();}
 });
 action('indexers-validate',async()=>{
  requireSavedSource();if(!validFields(['indexer-validation-query']))return;
  const query=document.getElementById('indexer-validation-query').value.trim(),media_type=document.getElementById('indexer-validation-type').value;
  if(query.length<2)throw new Error('Enter at least two characters of a movie or TV title.');
  const generation=state.indexerValidationGeneration||0;let result;
  state.indexerValidation=null;state.indexerValidationFor=null;document.getElementById('indexer-validation-result')?.remove();setupDeployment={...setupDeployment,journey:null};
  try{result=await api('indexers/validate','POST',{query,media_type});}
  finally{setupDeployment=await api('deployments');}
  if(generation!==(state.indexerValidationGeneration||0)||document.getElementById('indexer-validation-query')?.value.trim()!==query||document.getElementById('indexer-validation-type')?.value!==media_type){
   announce('Search details changed during the check. Run it again for the current title and media type.');return;
  }
  state.indexerValidation=result;state.indexerValidationFor={query,media_type};
  renderPreservingContext();
 });
 action('indexer-review',async()=>{
  if(state.appDirty)throw new Error('Save your app settings before reviewing a source.');
  if(!validFields(['indexer-name','indexer-url']))return;
  const key=document.getElementById('indexer-key'),payload={name:document.getElementById('indexer-name').value.trim(),feed_url:document.getElementById('indexer-url').value.trim(),api_key:key.value};key.value='';
  clearReview();clearSourceDirty();const generation=state.indexerEditGeneration,revision=state.revision;
  const review=await api('indexers/review','POST',payload);acceptSourceReview(review,generation,revision);
 });
 const connectReviewedSource=async()=>{
  if(state.dirty)throw new Error('Save changes and review the source again.');
  const token=state.indexerReview?.review_token;if(!token)throw new Error('Review this source again before connecting it.');state.indexerReview=null;state.indexerValidation=null;
  state.indexerResult=await api('indexers/apply','POST',{review_token:token});await checkSources();renderPreservingContext();
 };
 action('indexer-apply',connectReviewedSource);
}
