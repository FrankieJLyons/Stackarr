'use strict';
function backupSchedulePanel(){
 return automaticBackupPanel()+'<section class="panel"><h2>Recover after losing this computer</h2><p>Prepare one encrypted recovery file for the Stackarr account, protected app logins, app settings and installation receipts. Keep your recovery key separately. Media needs its own backup.</p><button id="host-backup-review">Prepare whole-host recovery</button><div id="host-backup-output" role="status"></div></section>';
}
function automaticBackupPanel(){
 const data=state.backupPlan;
 if(!data)return '<section class="panel"><h2>Automatic backups</h2><p>'+escape(state.backupPlanError||'Loading your backup plan…')+'</p><button id="backup-plan-refresh">Refresh backup plan</button></section>';
 const p=data.policy,installs=(setupDeployment.operations||[]).filter(op=>op.state==='needs-setup');
 return '<section class="panel"><h2>Automatic backups</h2><p>Choose a nightly time and how many scheduled copies to keep. Manual backups and safety copies stay available.</p>'+check('Back up nightly','backup-enabled',p.enabled)+'<div class="form-grid">'+field('Nightly time ('+data.timezone+')','backup-time',p.time,'time')+field('Scheduled copies per installation','backup-keep',p.keep,'number','min="1" max="90"')+select('Backup storage','backup-destination',p.destination||'',[['','This computer only'],...data.destinations.map(row=>[row.id,row.name])])+'</div><button id="backup-choose-folder">Choose folder on another disk</button><fieldset><legend>Apps to back up</legend>'+installs.map(op=>'<label><input type="checkbox" data-backup-install="'+escape(op.id)+'" '+((p.deployments.includes(op.id)||(!p.deployments.length&&!p.enabled))?'checked':'')+'> '+op.apps.map(key=>escape(state.catalog[key]?.name||key)).join(' · ')+'</label>').join('')+'</fieldset><p class="hint">'+escape(data.notice)+'</p><div class="actions"><button id="backup-plan-review" class="primary">Review backup plan</button><button id="backup-plan-run" '+(!p.deployments.length?'disabled':'')+'>Run backup plan now</button><button id="backup-plan-refresh">Refresh backup plan</button></div><div id="backup-plan-review-output" role="status"></div><p>Last result: '+escape(p.last_status)+(p.last_success?' · '+escape(new Date(p.last_success*1000).toLocaleString()):'')+'</p><p>Next backup: '+(p.enabled&&p.next_run?escape(new Date(p.next_run*1000).toLocaleString()):'Not scheduled')+'</p><details><summary>Save your recovery key</summary><p>Keep this file privately in a password manager or separate safe place. It unlocks encrypted app backups and controller checkpoints if the original key is lost. Media needs its own backup.</p>'+field('Stackarr owner password','backup-owner-password','','password','autocomplete="current-password"')+'<button id="backup-key-download">Download recovery key</button></details></section>';
}
async function refreshBackupPlan(){
 try{state.backupPlan=await api('backup-policy');state.dockerBackups=(await api('app-backups')).backups;state.backupPlanError='';}catch(e){state.backupPlanError=e.message;}finally{state.backupPlanLoading=false;if(state.view==='backups')render();}
}
function bindBackupPlan(){
 if(state.view!=='backups')return;
 if(!state.backupPlan&&!state.backupPlanError&&!state.backupPlanLoading){state.backupPlanLoading=true;refreshBackupPlan();}
 const bind=(id,fn)=>{const el=document.getElementById(id);if(el)el.onclick=async()=>{el.disabled=true;try{await fn();}catch(e){announce(e.message);const output=document.getElementById('backup-plan-review-output');if(output)output.textContent=e.message;}finally{el.disabled=false;}};};
 bind('backup-plan-refresh',refreshBackupPlan);
 bind('host-backup-review',async()=>{
  const review=await api('host-backup-review','POST',{}),output=document.getElementById('host-backup-output');
  output.innerHTML='<h3>Review whole-host backup</h3><p>'+review.apps.map(escape).join(' · ')+'</p><p>'+escape(review.notice)+'</p><button id="host-backup-apply" class="primary">Create recovery file</button>';
  document.getElementById('host-backup-apply').onclick=async event=>{event.target.disabled=true;try{await api('deployments/actions/apply','POST',{review_token:review.review_token});output.textContent='Creating your encrypted recovery file. Maintenance results below will show its saved location. On a replacement computer, unpack Stackarr and open Recover Stackarr.';await refreshLifecycle();}catch(e){output.textContent=e.message;}};
  document.getElementById('host-backup-apply').focus();
 });
 bind('backup-choose-folder',async()=>{announce('Choose a dedicated folder on another disk in the dialog on your Windows computer.');const selected=await api('backup-folder','POST',{});await refreshBackupPlan();document.getElementById('backup-destination').value=selected.id;});
 bind('backup-plan-review',async()=>{
  const value={enabled:document.getElementById('backup-enabled').checked,time:document.getElementById('backup-time').value,keep:Number(document.getElementById('backup-keep').value),destination:document.getElementById('backup-destination').value||null,deployments:[...document.querySelectorAll('[data-backup-install]:checked')].map(el=>el.dataset.backupInstall)};
  const review=await api('backup-policy-review','POST',value),output=document.getElementById('backup-plan-review-output');
  output.innerHTML='<h3>Review backup plan</h3><p>'+review.apps.map(escape).join(' · ')+'</p><p>'+escape(review.notice)+'</p><button id="backup-plan-apply" class="primary">Save backup plan</button>';
  document.getElementById('backup-plan-apply').onclick=async event=>{event.target.disabled=true;try{await api('deployments/actions/apply','POST',{review_token:review.review_token});await refreshBackupPlan();announce('Backup plan saved.');}catch(e){output.textContent=e.message;}};
  document.getElementById('backup-plan-apply').focus();
 });
 bind('backup-plan-run',async()=>{await api('backup-plan-run','POST',{});announce('Backup plan queued. Follow Maintenance results below.');await refreshLifecycle();});
 bind('backup-key-download',async()=>{const input=document.getElementById('backup-owner-password'),password=input.value;input.value='';const value=await api('backup-key','POST',{password});download('stackarr-backup-recovery-key.json',value);announce('Keep your recovery key privately and separately from the backups.');});
}
