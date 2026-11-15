'use strict';
const watchViews=['home','requests','library'];
const homeState={data:null,results:null,query:'',filter:'all',page:1,requestPage:1,requests:null,loading:false,error:'',generation:0,loaded:0};
let homeTimer;
function clearHome(){clearTimeout(homeTimer);homeState.generation++;Object.assign(homeState,{data:null,results:null,requests:null,query:'',filter:'all',page:1,requestPage:1,loading:false,error:'',loaded:0});document.getElementById('title-dialog')?.remove();}
function watchShell(){
 return `<div class="watch-shell"><header class="watch-header">${brand()}<nav aria-label="Main navigation">${[['home','Home'],['requests','Your requests'],['library','Your library']].map(([key,label])=>`<button data-view="${key}" ${state.view===key?'aria-current="page"':''}>${label}</button>`).join('')}</nav><div class="watch-utilities"><button data-view="setup" class="quiet">Setup</button><button data-view="overview" class="quiet">Manage server</button><button id="logout" class="linklike">Sign out</button></div></header><main class="watch-content" id="main" tabindex="-1">${homeSetupBanner()}${content()}</main></div>`;
}
function homeSetupBanner(){
 const journey=setupDeployment?.journey;
 const next=journey?.next_action;
 if(!next||['verification','source-validation'].includes(next.id)||!journey.selected_apps?.length)return '';
 const row=journey.checkpoints.find(item=>item.id===next.checkpoint_id);
 return `<section class="home-setup-banner" aria-label="Your next setup step"><div><strong>Let’s finish your setup</strong><p>${escape(row?.title||'Connect your media apps')} · ${escape(row?.detail||'Your saved progress is ready.')}</p></div><button class="primary" data-view="setup">Continue setup →</button></section>`;
}
function homeQualityChoice(item){
 if(!item.can_request)return '';
 const options=item.quality_options||[];
 if(item.existing_series)return `<p class="hint">${escape(item.quality_notice)}</p>`;
 if(!options.length)return `<p class="banner" role="status">${escape(item.quality_notice||'Quality could not be checked. Reopen this title to try again.')}</p><button type="button" id="title-setup">Continue setup</button>`;
 return `<label for="title-quality">Download quality</label><select id="title-quality" required aria-describedby="title-quality-help">${options.some(option=>option.default)?'':'<option value="">Choose quality for this title</option>'}${options.map(option=>`<option value="${escape(option.value)}" ${option.default?'selected':''}>${escape(option.label)}${option.default?' · your default':''}</option>`).join('')}</select><p id="title-quality-help" class="hint">${item.quality_notice?escape(item.quality_notice)+' ':''}Applies to this new title. You can override the suggested quality here. Existing files stay as they are.</p>`;
}
function homeRefreshOptions(){return {search:state.view==='home'&&!!homeState.results,requests:state.view==='requests'};}
function homeCard(item){
 return `<button class="title-card" data-title-kind="${item.kind}" data-title-id="${item.id}" aria-label="${escape(item.title)}${item.year?' ('+escape(item.year)+')':''}, ${escape(item.progress.label)}"><span class="poster-frame">${item.poster?`<img src="${escape(item.poster)}" loading="lazy" alt="">`:''}<span class="poster-fallback" aria-hidden="true">${item.kind==='tv'?'TV':'FILM'}<strong>${escape(item.title)}</strong></span><span class="title-status state-${escape(item.progress.state)}">${escape(item.progress.label)}</span></span><span class="title-name">${escape(item.title)}</span><span class="title-meta">${item.kind==='tv'?'TV show':'Movie'}${item.year?' · '+escape(item.year):''}${item.requested_quality?' · requested '+escape(item.requested_quality):item.is4k?' · 4K':''}</span></button>`;
}
function homeRail(label,data,description='',more=''){
 let items=(data?.items||[]).filter(item=>homeState.filter==='all'||item.kind===homeState.filter);
 return `<section class="watch-rail"><div class="watch-section-head"><div><h2>${label}</h2>${description?`<p>${description}</p>`:''}</div>${more}</div>${data?.error?`<div class="watch-empty" role="status">${escape(data.error)}</div>`:items.length?`<div class="title-row">${items.map(homeCard).join('')}</div>`:`<div class="watch-empty">${homeState.loading?'Loading titles…':homeState.filter==='all'?'Nothing here yet. Find something you’d love to watch.':'No titles of this type in this row yet.'}</div>`}</section>`;
}
function homeScreen(){
 const h=homeState,data=h.data;
 if(!state.config.integrations.seerr?.enabled||!state.credentials.includes('seerr'))return `<div class="watch-page-heading"><p class="eyebrow">YOUR MEDIA, TOGETHER</p><h1>${state.config.integrations.plex?.enabled?'Open your Plex library.':'Your next great watch starts here.'}</h1><p>${state.config.integrations.plex?.enabled?'Watch your existing movies and TV in Plex. Add finding and requesting through Setup whenever you want.':'Follow Setup to connect watching, finding and requesting movies and TV shows.'}</p></div><div class="actions">${homeAppLink('plex','Open Plex to watch →')}<button class="primary" data-view="setup">Continue setup →</button></div>`;
 const checked=(state.view==='requests'?(h.requests||data?.requests)?.checked_at:state.view==='home'&&h.results?h.results.checked_at:data?.checked_at)*1000;
 const error=(data?.preview_notice?`<p class="banner preview-label">${escape(data.preview_notice)}</p>`:'')+(h.error?`<div class="banner error" role="status">${escape(h.error)}${data?' Previously loaded titles may be out of date.':''} <button id="home-retry">Try again</button><button data-view="apps">Check connections</button></div>`:'');
 if(!data&&!h.results)return `<div class="watch-page-heading"><p class="eyebrow">YOUR MEDIA. YOUR EVENING.</p><h1>Your next great watch starts here.</h1></div>${error}${h.loading?'<p class="watch-empty" role="status">Loading your home…</p>':'<p>Connect Seerr to browse, request and see library availability here.</p><button class="primary" data-view="setup">Finish setup →</button>'}`;
 const tools=`<div class="watch-tools"><div class="watch-filters" aria-label="Title type">${[['all','All'],['movie','Movies'],['tv','TV shows']].map(([key,label])=>`<button data-home-filter="${key}" aria-pressed="${h.filter===key}">${label}</button>`).join('')}</div><span class="hint" id="home-checked">${h.loading?'Updating…':checked?'Updated '+new Date(checked).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}):'Connected through Seerr'}</span><button id="home-refresh" ${h.loading?'disabled':''}>↻ Refresh</button></div>`;
 if(state.view==='requests'){
  const requests=h.requests||data?.requests;
  return `<div class="watch-page-heading"><p class="eyebrow">THE JOURNEY TO PLAY</p><h1>Your requests</h1><p>See what’s waiting, downloading and ready for movie night.</p></div>${error}${tools}${homeRail('On your list',requests,'Requests visible to your connected Seerr owner. Status updates every 30 seconds while you’re here.')}${homePager(h.requestPage,requests?.pages,'requests')}<p class="watch-footnote">“Requested” can mean waiting for a suitable release. A completed download still needs importing and a Plex library check. Open a title for details or to watch when it is ready. Advanced request controls are available in Seerr.</p>${homeAppLink('seerr','Open Seerr')}`;
 }
 if(state.view==='library')return `<div class="watch-page-heading"><p class="eyebrow">MAKE IT A MOVIE NIGHT</p><h1>Your library</h1><p>Titles Seerr reports in your library. Open a title to check Plex and start watching.</p></div>${error}${tools}${homeRail('Recently added',data?.available,'Includes partially available shows; Plex lists the episodes you can play.')}<p class="watch-footnote">This preview shows the 12 most recently added library titles. Search above in Home or open Plex for your full library.</p>${homeAppLink('plex','Open your full Plex library')}`;
 const featured=(data?.trending?.items||[]).find(item=>item.backdrop&&(h.filter==='all'||item.kind===h.filter))||(data?.trending?.items||[]).find(item=>h.filter==='all'||item.kind===h.filter);
 const search=`<form id="home-search-form" role="search"><label for="home-search">Find your next watch</label><div><input type="search" id="home-search" maxlength="160" placeholder="Search movies and TV shows" value="${escape(h.query)}" autocomplete="off"><button type="submit" class="primary">Search</button>${h.results?'<button type="button" id="home-clear">Clear</button>':''}</div></form>`;
 if(h.results)return `<div class="watch-page-heading"><p class="eyebrow">FIND YOUR NEXT WATCH</p><h1>Something good is waiting.</h1></div>${search}${error}${tools}<section class="watch-rail"><h2>Results for “${escape(h.query)}”</h2><div class="title-grid">${h.results.items.filter(item=>h.filter==='all'||item.kind===h.filter).map(homeCard).join('')||`<p>${h.loading?'Searching…':h.error?'Search results are unavailable. Try again.':'No matches on this page. Try another name, title type or page.'}</p>`}</div></section>${homePager(h.page,h.results.pages,'search')}`;
 return `${error}<section class="watch-feature">${featured?.backdrop?`<img class="feature-art" src="${escape(featured.backdrop)}" alt="">`:''}<div class="feature-shade"></div><div class="feature-copy"><p class="eyebrow">YOUR MEDIA. YOUR EVENING.</p><h1>${featured?escape(featured.title):'Find your next<br>great watch.'}</h1><p class="feature-meta">${featured?`${featured.kind==='tv'?'TV show':'Movie'}${featured.year?' · '+escape(featured.year):''} · Trending on TMDB`:'Movies, TV shows and everything you’re looking forward to.'}</p><p class="feature-overview">${featured?escape(featured.overview):'Search for something you love, request it, and follow it all the way to your library.'}</p><div class="actions">${featured?`<button class="primary" data-title-kind="${featured.kind}" data-title-id="${featured.id}">View title →</button>`:'<button class="primary" data-view="setup">Finish setup →</button>'}<button data-view="library" class="feature-secondary">Your library</button></div></div></section>${search}${tools}${homeRail('Ready for your evening',data?.available,'In your library. Open a title to check Plex.', '<button class="linklike" data-view="library">View library →</button>')}${homeRail('On its way',data?.requests,'Follow your requests, from finding a release to your library.','<button class="linklike" data-view="requests">All requests →</button>')}${homeRail('Trending now',data?.trending,'Popular on TMDB; availability depends on your library and sources.')}${homeRail('Movie night',data?.movies)}${homeRail('One more episode',data?.tv)}<footer class="watch-footnote">Title information and artwork from TMDB through Seerr. This product uses the TMDB API but is not endorsed or certified by TMDB. Choose quality when requesting a new title. Your connected Seerr account handles approvals and finding releases.</footer>`;
}
function homePager(page,pages=1,scope){return pages>1?`<div class="pager"><button data-home-page="${page-1}" data-home-scope="${scope}" ${page<=1?'disabled':''}>Previous</button><span>Page ${page} of ${pages}</span><button data-home-page="${page+1}" data-home-scope="${scope}" ${page>=pages?'disabled':''}>Next</button></div>`:'';}
function homeAppLink(key,label){
 const app=state.config.integrations[key];
 if(!app?.enabled)return '';
 const url=browserAppUrl(key);
 if(!url)return '<span class="hint">Home-network link not configured</span>';
 return `<a class="watch-app-link" href="${escape(url)}" rel="noreferrer">${label} ↗</a>`;
}
function repaintHome(){if(!watchViews.includes(state.view)||!root.querySelector('.watch-shell'))return;renderPreservingContext();}
async function loadHome({search=false,requests=false,quiet=false}={}){
 if(homeState.loading)return;
 clearTimeout(homeTimer);
 const generation=homeState.generation;
 homeState.loading=true;homeState.error='';if(search)homeState.results={items:[],pages:homeState.results?.pages||1};if(!quiet)repaintHome();
 try{
  const path=search?'home/search?query='+encodeURIComponent(homeState.query)+'&page='+homeState.page:requests?'home/requests?page='+homeState.requestPage:'home';
  const data=await api(path);
  if(generation!==homeState.generation)return;
  if(search)homeState.results=data;else if(requests)homeState.requests=data;else{homeState.data=data;homeState.requests=null;}
  homeState.loaded=Date.now();
 }catch(e){if(generation===homeState.generation)homeState.error=e.message;}
 finally{if(generation===homeState.generation){homeState.loading=false;repaintHome();scheduleHome();}}
}
function scheduleHome(){
 clearTimeout(homeTimer);
 if(!watchViews.includes(state.view)||document.hidden||(state.view==='home'&&homeState.results)||(state.config&&(!state.config.integrations.seerr?.enabled||!state.credentials.includes('seerr'))))return;
 homeTimer=setTimeout(()=>{if(!document.getElementById('title-dialog')?.open)loadHome({requests:state.view==='requests',quiet:true});else scheduleHome();},30000);
}
document.addEventListener('visibilitychange',()=>{if(document.hidden)clearTimeout(homeTimer);else scheduleHome();});
function bindHome(){
 clearTimeout(homeTimer);
 if(!watchViews.includes(state.view))return;
 if(!state.config.integrations.seerr?.enabled||!state.credentials.includes('seerr'))return;
 root.querySelectorAll('img').forEach(img=>{img.onerror=()=>{img.hidden=true;};});
 on('home-refresh',()=>loadHome(homeRefreshOptions()));
 on('home-retry',()=>loadHome(homeRefreshOptions()));
 const form=document.getElementById('home-search-form');
 if(form)form.onsubmit=e=>{e.preventDefault();if(homeState.loading)return;const value=form.querySelector('input').value.trim();if(!value){document.getElementById('home-search').focus();return;}homeState.query=value;homeState.page=1;loadHome({search:true});};
 on('home-clear',()=>{homeState.query='';homeState.results=null;homeState.page=1;repaintHome();});
 root.querySelectorAll('[data-home-filter]').forEach(button=>button.onclick=()=>{homeState.filter=button.dataset.homeFilter;repaintHome();});
 root.querySelectorAll('[data-home-page]').forEach(button=>button.onclick=()=>{if(homeState.loading)return;const search=button.dataset.homeScope==='search';if(search)homeState.page=Number(button.dataset.homePage);else homeState.requestPage=Number(button.dataset.homePage);loadHome({search,requests:!search});});
 root.querySelectorAll('[data-title-id]').forEach(button=>button.onclick=()=>openHomeTitle(button.dataset.titleKind,Number(button.dataset.titleId),button));
 if(!homeState.data&&!homeState.error&&!homeState.loading)queueMicrotask(()=>loadHome());else scheduleHome();
}
async function openHomeTitle(kind,id,opener){
 document.getElementById('title-dialog')?.remove();
 const dialog=document.createElement('dialog');dialog.id='title-dialog';dialog.className='title-dialog';dialog.setAttribute('aria-labelledby','title-dialog-name');
 dialog.innerHTML='<div class="title-dialog-loading"><h2 id="title-dialog-name">Loading title…</h2><button class="dialog-close" aria-label="Close title details">×</button></div>';
 document.body.append(dialog);dialog.showModal();
 dialog.addEventListener('close',()=>{dialog.remove();const target=opener?.isConnected?opener:root.querySelector(`[data-title-kind="${kind}"][data-title-id="${id}"]`);if(target)target.focus({preventScroll:true});});
 const close=()=>dialog.querySelector('.dialog-close').onclick=()=>dialog.close();close();
 dialog.addEventListener('click',e=>{if(e.target===dialog){const box=dialog.getBoundingClientRect();if(e.clientX<box.left||e.clientX>box.right||e.clientY<box.top||e.clientY>box.bottom)dialog.close();}});
 try{
  const item=await api(`home/titles/${kind}/${id}`);if(!dialog.open)return;
  dialog.innerHTML=`<div class="title-detail-art">${item.backdrop?`<img src="${escape(item.backdrop)}" alt="">`:''}<button class="dialog-close" aria-label="Close title details">×</button></div><div class="title-detail-copy"><p class="eyebrow">${item.kind==='tv'?'TV SHOW':'MOVIE'}${item.year?' · '+escape(item.year):''}</p><h2 id="title-dialog-name">${escape(item.title)}</h2><p class="detail-state state-${escape(item.progress.state)}">${escape(item.progress.label)}</p><p>${escape(item.overview)||'No description is available for this title.'}</p><p class="detail-progress">${escape(item.progress.detail)}</p>${item.requested_quality?`<p class="hint">Requested quality: ${escape(item.requested_quality)}</p>`:''}${item.play_url?`<a class="primary play-link" href="${escape(item.play_url)}" rel="noreferrer">▶ Open in Plex ↗</a><p class="hint">Plex opens this title’s page here. Choose Play there; your Plex sign-in may be needed. Use Back to return to Stackarr.</p>`:''}${item.play_notice?`<p class="banner" role="status">${escape(item.play_notice)}</p>`:''}<form id="title-request-form">${homeQualityChoice(item)}${item.kind==='tv'&&item.seasons.length?`<fieldset><legend>Choose seasons</legend><div class="season-list">${item.seasons.map(s=>`<label><input type="checkbox" name="season" value="${s.number}" ${s.requestable?'':'disabled'}><span>${escape(s.name)}<small>${escape(s.label)}</small></span></label>`).join('')}</div></fieldset>`:''}${item.can_request&&(item.existing_series||item.quality_options?.length)?`<p class="hint">Uses your connected Seerr account and approval settings. ${item.kind==='tv'?'Selected seasons are sent to Sonarr through Seerr. Future seasons are not automatically requested here.':''}</p><button class="primary" type="submit">${item.kind==='tv'?'Request selected seasons':'Request movie'}</button>`:''}<p id="title-request-result" role="status"></p></form><div class="title-detail-footer">${homeAppLink('seerr','More options in Seerr')}${homeAppLink('plex','Open Plex')}</div></div>`;
  close();dialog.querySelectorAll('img').forEach(img=>{img.onerror=()=>{img.hidden=true;};});dialog.querySelector('.dialog-close').focus({preventScroll:true});
  const form=dialog.querySelector('form'),submit=form.querySelector('button[type=submit]');
  const setup=dialog.querySelector('#title-setup');if(setup)setup.onclick=()=>{dialog.close();state.view='setup';render();};
  if(!submit)return;
  if(kind==='tv'){submit.disabled=true;form.onchange=()=>{submit.disabled=!form.querySelector('input:checked');};}
  let sending=false;
  form.onsubmit=async e=>{e.preventDefault();if(sending)return;const result=form.querySelector('#title-request-result');const seasons=Array.from(form.querySelectorAll('input:checked')).map(input=>Number(input.value));if(kind==='tv'&&!seasons.length){result.textContent='Choose at least one season.';return;}sending=true;submit.disabled=true;submit.textContent='Saving request…';result.textContent='';
   try{const saved=await api(`home/titles/${kind}/${id}/request`,'POST',{seasons,quality:form.querySelector('#title-quality')?.value||''});result.textContent=saved.message;const follow=document.createElement('button');follow.type='button';follow.className='primary';follow.textContent='Follow in Your requests →';follow.onclick=()=>{dialog.close();state.view='requests';render();loadHome({requests:true});};result.append(document.createElement('br'),follow);submit.textContent='✓ Request saved';form.querySelectorAll('input,select').forEach(input=>{input.disabled=true;if(input.checked)input.closest('label').querySelector('small').textContent='Requested';});if(saved.progress){dialog.querySelector('.detail-state').textContent=saved.progress.label;dialog.querySelector('.detail-progress').textContent=saved.progress.detail;}announce(saved.message);homeState.loaded=0;if(saved.progress&&homeState.results)homeState.results.items=homeState.results.items.map(row=>row.kind===kind&&row.id===id?{...row,progress:saved.progress}:row);await loadHome({requests:state.view==='requests',quiet:true});}
   catch(e){result.textContent=e.message;submit.textContent='Check requests before retrying';const check=document.createElement('button');check.type='button';check.textContent='Close and check requests';check.onclick=()=>{dialog.close();state.view='requests';render();loadHome({requests:true});};result.append(document.createElement('br'),check);}
  };
 }catch(e){if(!dialog.open)return;dialog.innerHTML='<div class="title-detail-copy"><button class="dialog-close" aria-label="Close title details">×</button><h2 id="title-dialog-name">Could not load this title</h2><p role="alert">'+escape(e.message)+'</p></div>';close();}
}
