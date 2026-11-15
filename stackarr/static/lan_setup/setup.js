'use strict';
(() => {
 let key=location.hash.slice(1), busy=false, review=null, timer=null, state=null, closed=false;
 const $=id=>document.getElementById(id), buttons=()=>document.querySelectorAll('button');
 const trustGuides={
  windows:'Open the .cer file on the device. Choose Install Certificate → Current User → Place all certificates in the following store → Trusted Root Certification Authorities. Check the fingerprint on this server before confirming. Close and reopen the browser.',
  macos:'Open the .cer file in Keychain Access. Add it to the login or System keychain. Open the certificate, expand Trust, and set Secure Sockets Layer (SSL) to Always Trust after checking its fingerprint. Reopen the browser.',
  ios:'Transfer the .cer file to your iPhone or iPad and open it. In Settings, install the downloaded profile after checking its fingerprint. Then open General → About → Certificate Trust Settings and enable full trust for this root. Managed devices may restrict this.',
  android:'Transfer the .cer file to your device. In Settings, search for “Install a certificate” and choose CA certificate. Compare its fingerprint before installing it. Menu names vary by device; some apps do not accept user-installed CAs.',
  firefox:'First install the certificate for your operating system. If Firefox still warns, open Settings → Privacy & Security → Certificates → View Certificates → Authorities → Import. Choose the same .cer file and allow it to identify websites after checking its fingerprint.'
 };
 if($('device-system'))$('device-system').onchange=()=>{$('device-instructions').textContent=trustGuides[$('device-system').value];};
 if(!key){try{key=sessionStorage.getItem('stackarr-lan-key');}catch(_){}}
 if(location.hash){try{sessionStorage.setItem('stackarr-lan-key',key);}catch(_){}history.replaceState(null,'','/');}
 async function api(action,values={}){
  const response=await fetch('/api/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-LAN-Key':key},body:JSON.stringify(values)});
  const data=await response.json().catch(()=>({message:'Setup could not be reached. Reopen Home network & recovery on this computer.'}));
  if(!response.ok)throw new Error(data.message||'This step could not finish. Try again.');return data;
 }
 function panel(name){for(const id of ['setup','devices','recovery']){$(id+'-panel').hidden=id!==name;$(id+'-tab').setAttribute('aria-pressed',String(id===name));}$(name==='setup'?'setup-heading':name==='devices'?'devices-heading':'recovery-heading').focus();}
 for(const id of ['setup','devices','recovery'])$(id+'-tab').onclick=()=>panel(id);
 function render(data){
  state=data;$('prepared').hidden=!data.prepared;$('device-empty').hidden=data.prepared;$('device-guide').hidden=!data.prepared;
  $('local-link').href=data.local_url;
  if(data.prepared){$('remote-address').textContent=data.address;$('gateway-status').textContent=data.gateway_running?'Secure access is running from this helper. Keep this helper running while other devices connect.':'Address and certificate saved. Enable this address, then start secure access below.';$('fingerprint').textContent=data.certificate?data.certificate.fingerprint.match(/.{1,4}/g).join(' '):'Certificate needs recovery. Use your local dashboard.';$('certificate-expiry').textContent=data.certificate?'Trust certificate valid until '+data.certificate.expires+'. Its SHA-256 file hash matches the fingerprint above. Keep this certificate: preparing it again is not needed for each device.':'';$('firewall-help').textContent='Secure address: '+data.address+'. Allowed clients: '+data.clients.join(', ')+'.';}
  $('diagnosis').textContent=[...(data.issues||[]),data.checks.message||''].filter(Boolean).join(' ');$('certificate').disabled=busy||!data.certificate;
  const job=data.job;
  if(job){$('message').textContent=job.message;clearTimeout(timer);if(!['succeeded','rolled-back','failed-recovered','needs-recovery'].includes(job.phase))timer=setTimeout(refresh,1200);}
  const working=job&&!['succeeded','rolled-back','failed-recovered','needs-recovery'].includes(job.phase);
  for(const id of ['prepare','enable','apply','start','restart','stop','undo','recover','close'])$(id).disabled=busy||!!working;
 }
 async function refresh(){if(closed)return;if(busy){timer=setTimeout(refresh,1200);return;}try{render(await api('status'));}catch(error){showError(error);}}
 function showError(error){$('error').textContent=error.message;$('error').hidden=false;}
 async function step(message,work){if(busy||closed)return;busy=true;buttons().forEach(b=>b.disabled=true);$('message').textContent=message;$('error').hidden=true;try{await work();}catch(error){showError(error);}finally{busy=false;if(!closed){buttons().forEach(b=>b.disabled=false);if(state)render(state);}}}
 async function choices(){const data=await api('choices');const select=$('network');select.replaceChildren(new Option('Choose a connection',''));for(const row of data.interfaces){const option=new Option(row.name+' · '+row.address+' · '+row.profile,JSON.stringify(row));select.add(option);}if(data.interfaces.length===1){select.selectedIndex=1;select.onchange();}$('network-note').textContent=data.interfaces.length?'Choose the connection shared with your other computers.':'No suitable connection was found. Connect to your home network and refresh, or enter its details.';}
 $('network').onchange=()=>{if(!$('network').value)return;const row=JSON.parse($('network').value);$('address').value=row.address;$('clients').value=row.clients;$('network-note').textContent=row.profile==='Private'?'Private home connection selected.':'This connection is not marked Private. Keep preparation separate; review its Windows network profile on the spare test host.';};
 $('scan').onclick=()=>step('Reading available connections…',choices);
 $('prepare').onclick=()=>step('Creating your local HTTPS address and trust certificate…',async()=>{render(await api('prepare',{address:$('address').value.trim(),clients:$('clients').value.trim(),port:Number($('port').value),hostname:$('hostname').value.trim()}));$('message').textContent='Address and certificate saved. Review enabling this address, then start secure access.';});
 $('copy-address').onclick=()=>step('Copying your home-network address…',async()=>{
  if(!state?.address)throw new Error('Prepare your address first.');
  if(navigator.clipboard?.writeText){try{await navigator.clipboard.writeText(state.address);$('message').textContent='Address copied. Open it on a device after trusting the certificate.';return;}catch(_){}}
  const selection=getSelection(),range=document.createRange();range.selectNodeContents($('remote-address'));selection.removeAllRanges();selection.addRange(range);$('message').textContent='Address selected. Copy it using your device’s copy command.';
 });
 $('go-devices').onclick=()=>panel('devices');
 $('certificate').onclick=()=>step('Preparing the public certificate download…',async()=>{const data=await api('certificate');const blob=new Blob([Uint8Array.from(atob(data.data),c=>c.charCodeAt(0))],{type:'application/pkix-cert'});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=data.filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);$('message').textContent='Only the public certificate was downloaded. Trust settings have not changed.';});
 for(const [id,action] of [['enable','enable'],['undo','undo'],['recover','recover']])$(id).onclick=()=>step('Checking the saved settings and recovery checkpoint…',async()=>{review=await api('review',{action});$('review-title').textContent={enable:'Enable this address for testing?',undo:'Turn off home-network access?',recover:'Recover the interrupted change?'}[action];$('review-notice').textContent=review.notice;$('review-address').textContent='Home address: '+review.address+'. Recovery address: '+review.local_url;$('review-dialog').showModal();});
 $('cancel').onclick=()=>{review=null;$('review-dialog').close();};
 $('apply').onclick=()=>step('Applying the reviewed change. Keep this helper open…',async()=>{const value=review;review=null;$('review-dialog').close();render(await api('apply',{token:value.token}));});
 for(const id of ['start','restart'])$(id).onclick=()=>step('Checking Docker and the saved address, then starting this gateway…',async()=>{render(await api('start'));$('message').textContent='The gateway answered with a valid certificate. Other-computer and reboot checks remain pending.';});
 $('check').onclick=()=>step('Checking the saved certificate and Docker without restarting services…',async()=>render(await api('check')));
 $('stop').onclick=()=>step('Stopping only this helper’s gateway…',async()=>{await api('stop');render(await api('status'));$('message').textContent='This gateway is stopped. Your saved setup and local dashboard are kept.';});
 $('close').onclick=()=>step('Finishing setup and stopping this helper’s gateway…',async()=>{await api('close');closed=true;clearTimeout(timer);try{sessionStorage.removeItem('stackarr-lan-key');}catch(_){}key=null;$('message').textContent='Setup finished. Your saved setup is kept. Reopen Home network & recovery to continue.';buttons().forEach(b=>b.disabled=true);});
 if(!key){$('message').textContent='Reopen Home network & recovery from Start Stackarr on this computer.';buttons().forEach(b=>b.disabled=true);return;}
 $('device-system').onchange();
 step('Opening your saved setup…',async()=>{render(await api('status'));await choices();$('message').textContent=state.prepared?'Your saved address is ready to review. Device checks remain pending.':'Prepare now and connect another computer when your test host is ready.';});
})();
