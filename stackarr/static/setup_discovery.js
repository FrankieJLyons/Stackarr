'use strict';
function setupUseDiscovered(draft,result){
 if(!['compatible-api','credentials-required','manual-check'].includes(result.state))throw new Error('Check this app address manually before connecting.');
 const next=structuredClone(draft);
 if(!next.apps.includes(result.app))next.apps.push(result.app);
 next.choices={...next.choices,[result.app]:{mode:'connect',url:result.address,browser_url:result.browser_address||result.address,port:0,quality_profile:''}};
 return next;
}
function setupDiscoveryPanel(){
 if(!setupDiscovery)return '';
 const usable=r=>['compatible-api','credentials-required'].includes(r.state)||(r.state==='manual-check'&&r.source==='docker-published-port');
 const found=new Set(setupDiscovery.results.filter(usable).map(r=>r.app));
 const missing=[...new Set(setupDiscovery.results.filter(r=>!found.has(r.app)).map(r=>r.app))];
 return '<p>'+escape(setupDiscovery.message)+'</p><div class="cards">'+[...found].map(key=>{
  const matches=setupDiscovery.results.map((r,i)=>({r,i})).filter(({r})=>r.app===key&&usable(r));
  const owned=setupDeployment.operations.some(op=>op.state==='needs-setup'&&op.apps.includes(key));
  return '<article class="card"><h3>'+escape(state.catalog[key].name)+'</h3>'+(matches.length>1?'<p>Multiple addresses found. Choose the instance you already use.</p>':'')+matches.map(({r,i})=>{
   const label={'compatible-api':'App responded','credentials-required':'Sign-in required · confirm this is your app','manual-check':'Docker app found · connection needs checking'}[r.state];
   return '<p class="hint">'+escape(label)+'<br>'+escape(r.browser_address||r.address)+'</p>'+(!owned?'<button data-discovered-app="'+i+'">Use this '+escape(state.catalog[key].name)+' app</button>':'<p>Already installed by this Stackarr.</p>');
  }).join('')+'</article>';
 }).join('')+'</div>'+(missing.length?'<p>No confirmed connection found for '+missing.map(key=>escape(state.catalog[key].name)).join(', ')+'.</p>':'')+'<p class="hint">Missing an app? It may use HTTPS, another computer, or a custom address. Enter it under Customize apps. Choosing a result saves an address only; existing downloads, libraries and startup remain unchanged.</p>';
}
