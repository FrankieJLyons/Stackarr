'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const test=require('node:test');
const vm=require('node:vm');

test('overlapping startup calls await the same one-use setup handoff',async()=>{
 let resolve, calls=0;
 const context=vm.createContext({URLSearchParams,location:{hash:'#setup=synthetic-ticket',pathname:'/',search:''},
  history:{replaceState(){}},window:{addEventListener(){}},
  api:()=>{calls++;return new Promise(done=>{resolve=done;});}});
 vm.runInContext(fs.readFileSync('stackarr/static/launcher.js','utf8'),context);
 let firstDone=false,secondDone=false;
 const first=context.receiveSetupHandoff().then(()=>{firstDone=true;});
 const second=context.receiveSetupHandoff().then(()=>{secondDone=true;});
 await Promise.resolve();
 assert.equal(calls,1);
 assert.equal(firstDone,false);
 assert.equal(secondDone,false);
 resolve({approved:true});
 await Promise.all([first,second]);
 assert.equal(firstDone&&secondDone,true);
 await context.receiveSetupHandoff();
 assert.equal(calls,1);
});

test('TV checklist action selects TV before focusing the search field',async()=>{
 const type={value:'movie'},query={},workspace={};
 let focus;
 const context=vm.createContext({state:{dirty:false},setupActionBlock:()=>'',render(){},
  document:{getElementById:id=>({'indexer-validation-type':type,'indexer-validation-query':query,'setup-task-workspace':workspace}[id])},
  focusSetupTarget:node=>{focus=node;}});
 vm.runInContext(fs.readFileSync('stackarr/static/preferences.js','utf8'),context);
 context.setupActionBlock=()=>'';
 await context.openSetupCheckpoint({action:{id:'source-validation',media_type:'tv'}});
 assert.equal(type.value,'tv');
 assert.equal(focus,query);
});
