'use strict';
let localLauncher=false;
let launcherApproved=false;
let pairingTimer;
let setupApprovalTimer;
const setupApprovalExpired='Setup approval expired. Reopen Start Stackarr on this computer, then return here. Your password has not been saved.';
async function checkSetupApproval(form){
 const session=await api('session');
 if(!form.isConnected)return false;
 if(!session.setup_required){await boot();return false;}
 launcherApproved=!!session.setup_approved;
 const button=form.querySelector('button'),message=form.querySelector('#auth-error');
 if(!launcherApproved){button.disabled=true;message.textContent=setupApprovalExpired;}
 else if(message.textContent===setupApprovalExpired){
  button.disabled=form.dataset.submitting==='true';
  message.textContent='Setup approval renewed. Continue when ready.';
 }
 return launcherApproved;
}
function watchSetupApproval(form){
 clearTimeout(setupApprovalTimer);
 const check=async()=>{
  if(!form.isConnected)return;
  try{if(form.dataset.submitting!=='true')await checkSetupApproval(form);}catch{/* Submission checks again if a background check cannot connect. */}
  if(form.isConnected)setupApprovalTimer=setTimeout(check,30000);
 };
 setupApprovalTimer=setTimeout(check,30000);
}
function launcherApproval(){
 root.innerHTML='<main class="auth-form"><section><h1>Connect to your Stackarr window.</h1><p>Request a code here, then approve the matching code in the Stackarr setup window on this computer.</p><button id="request-pair" class="primary">Request setup approval</button><p id="pair-status" role="status"></p><p class="hint">Approval expires after two minutes. Keep the Stackarr window open.</p></section></main>';
 document.getElementById('request-pair').onclick=async()=>{
  const button=document.getElementById('request-pair');button.disabled=true;
  try{
   const result=await api('launcher/pair','POST',{});
   document.getElementById('pair-status').textContent='Your code: '+result.code+'. Approve this code in the Stackarr window.';
   const deadline=Date.now()+result.expires_in*1000;
   const check=async()=>{
    if(!document.getElementById('pair-status'))return;
    try{
     const session=await api('session');
     if(session.setup_approved){launcherApproved=true;auth(true);return;}
     if(!session.setup_required){auth(false);return;}
     if(Date.now()>=deadline){document.getElementById('pair-status').textContent='Approval expired. Request a new code.';button.disabled=false;return;}
     pairingTimer=setTimeout(check,1000);
    }catch(e){document.getElementById('pair-status').textContent=e.message;button.disabled=false;}
   };
   clearTimeout(pairingTimer);await check();
  }catch(e){document.getElementById('pair-status').textContent=e.message;button.disabled=false;}
 };
}

// Capture and remove the one-use invitation before any asynchronous requests.
let setupInvitation;
function captureSetupInvitation(){
 setupInvitation=new URLSearchParams(location.hash.slice(1)).get('setup');
 if(setupInvitation)history.replaceState(null,'',location.pathname+location.search);
}
captureSetupInvitation();
window.addEventListener('hashchange',()=>{captureSetupInvitation();if(setupInvitation)boot();});
async function receiveSetupHandoff(){
 if(!setupInvitation)return;
 const ticket=setupInvitation;setupInvitation=null;
 await api('setup/handoff','POST',{ticket});
}
function dockerWelcome(){
 root.innerHTML='<main class="auth-form" id="main"><section>'+brand()+'<h1>Welcome to Stackarr.</h1><p>Open <strong>Start Stackarr</strong> from your download on the computer running Stackarr. It opens a private setup page automatically, where you can choose your password.</p><p>If someone else installed Stackarr for you, ask them to open setup on that computer.</p><p>You do not need to find or copy a security code.</p><button id="check-setup">Check again</button></section></main>';
 document.getElementById('check-setup').onclick=boot;
}
