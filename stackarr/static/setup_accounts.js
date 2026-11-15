function accountSetupResult(){
 const owned=(setupDeployment.operations||[]).filter(op=>op.state==='needs-setup'&&(op.apps||[]).includes('plex')&&setupAppSelected('plex')&&state.config.integrations.plex?.enabled);
 if(!state.accountResult&&!owned.length)return '';
 return '<section class="panel" id="setup-accounts"><h2>'+(state.accountResult?'Watching setup saved':'Your Plex libraries')+'</h2>'+(state.accountResult?'<p role="status">'+escape(state.accountResult.message)+'</p>'+(state.config.integrations.prowlarr?.enabled?'<button id="accounts-next" class="primary">Continue to content sources →</button>':'<button class="primary" data-view="home">Open Home →</button>'):'<p>Stackarr uses the Windows media folder you chose. Check these libraries here to prepare missing Movies and TV folders without browsing Docker paths in Plex. Existing libraries and accounts are kept.</p>')+owned.map(op=>'<button data-accounts-review="'+escape(op.id)+'">Check Plex libraries</button>').join('')+accountSetupReview()+'<p id="account-setup-error" role="alert">'+escape(state.accountError||'')+'</p></section>';
}
function accountSetupReview(){
 const review=state.accountReview;
 return review?'<h3>Ready to prepare your library</h3><p>'+escape(review.notice)+'</p><ul>'+review.libraries.map(row=>'<li>'+escape(row.name)+' · '+(row.state==='create'?'prepare library':'keep existing library')+'</li>').join('')+'</ul><button class="primary" id="accounts-apply">Prepare watching and requests</button><p id="account-setup-progress" role="status"></p>':'';
}
function accountSetupSteps(installs,links){
 const addresses=new Map();
 for(const op of installs)for(const link of links(op))if(['plex','seerr'].includes(link.app)&&!addresses.has(link.app))addresses.set(link.app,link.url);
 const owned=installs.filter(op=>op.apps.includes('plex'));
 if(owned.length&&!addresses.has('plex')&&state.config.integrations.plex?.enabled&&browserAppUrl('plex'))addresses.set('plex',browserAppUrl('plex'));
 if(!addresses.size)return '';
 let html='<ol class="account-setup-steps">';
 if(addresses.has('plex')){
  html+='<li id="setup-account-plex" tabindex="-1"><h3>1. Sign in to Plex for watching</h3><p>Plex plays your movies and TV. Sign in and give this new server a name you recognise. At Plex’s Media Library screen, choose Next without Add Library, then Done. Return here: Stackarr uses the Windows folder you already chose and prepares your libraries. You do not need Plex’s Docker folder picker.</p><p><a class="primary watch-app-link" href="'+escape(addresses.get('plex'))+'" target="_blank" rel="noopener noreferrer">Sign in to Plex ↗</a></p></li>';
  html+='<li id="setup-account-seerr" tabindex="-1"><h3>2. Prepare movies, TV and requests</h3><p>One review connects your new requests app using the Plex sign-in you just completed, prepares the matching library folders, and connects the new download apps. You do not need another Plex sign-in or any app keys.</p>'+owned.map(op=>'<button class="primary" data-accounts-review="'+escape(op.id)+'">Check Plex sign-in & continue →</button>').join('')+'</li>';
  if(state.accountReview)html+='<li>'+accountSetupReview()+'</li>';
  if(state.accountResult)html+='<li><p role="status">'+escape(state.accountResult.message)+'</p><button id="accounts-next" class="primary">Continue to content sources →</button></li>';
  html+='</ol><p id="account-setup-error" role="alert">'+escape(state.accountError||'')+'</p><details><summary>Advanced account setup</summary><p>If your requests app already uses another account or server, review it in Seerr. Stackarr preserves that existing connection.</p>'+(addresses.has('seerr')?'<a href="'+escape(addresses.get('seerr'))+'" target="_blank" rel="noopener noreferrer">Open Seerr setup ↗</a>':'')+'</details>';
  return html;
 }
 if(addresses.has('seerr'))html+='<li><h3>Connect requests with Plex</h3><p>Open Seerr and choose Login with Plex. Select the Plex server and libraries you already use, then return and choose Finish connecting. If it has no libraries yet, Continue without libraries lets you finish sign-in.</p><a href="'+escape(addresses.get('seerr'))+'" target="_blank" rel="noopener noreferrer">Open Seerr setup ↗</a></li>';
 return html+'</ol>';
}
function bindAccountSetup(){
 document.querySelectorAll('[data-accounts-review]').forEach(button=>button.onclick=async()=>{
  if(state.dirty){announce('Save your current changes before connecting Plex.');return;}
  button.disabled=true;button.textContent='Checking Plex sign-in…';state.accountReview=null;state.accountError='';
  try{state.accountReview=await api('deployments/'+button.dataset.accountsReview+'/accounts/review','POST',{});render();focusSetupTarget(document.getElementById('accounts-apply'));}
  catch(error){state.accountError=error.message;renderPreservingContext();focusSetupTarget(document.getElementById('account-setup-error'));}
  finally{if(button.isConnected){button.disabled=false;button.textContent='Check Plex sign-in & continue →';}}
 });
 on('accounts-apply',async()=>{
  if(state.dirty)throw new Error('Save changes, then check Plex sign-in again.');
  const token=state.accountReview?.review_token;if(!token)throw new Error('Check Plex sign-in before preparing your library.');
  state.accountReview=null;state.accountError='';
  const progress=document.getElementById('account-setup-progress');if(progress)progress.textContent='Connecting your requests account and preparing library folders… Keep this page open.';
  try{state.accountResult=await api('accounts/apply','POST',{review_token:token});await api('refresh','POST',{});await load();render();announce(state.accountResult.message);}
  catch(error){state.accountError=error.message;render();focusSetupTarget(document.getElementById('account-setup-error'));}
 });
 on('accounts-next',async()=>{await load();render();focusSetupTarget(document.getElementById('indexer-setup')||document.getElementById('setup-verification'));});
 document.querySelectorAll('[data-copy-account-address]').forEach(button=>button.onclick=async()=>{
  const output=button.closest('details').querySelector('[data-account-copy-status]');
  try{await navigator.clipboard.writeText(button.dataset.copyAccountAddress);output.textContent='Seerr address copied. Paste it into your usual browser.';}
  catch(e){const input=button.closest('details').querySelector('[data-account-address]');input.focus();input.select();output.textContent='Select and copy the address above, then paste it into your usual browser.';}
 });
}
