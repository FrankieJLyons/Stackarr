const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

function fixture(operations){
 const scope={state:{config:{integrations:{plex:{enabled:true},prowlarr:{enabled:true}}}},setupDeployment:{operations},setupAppSelected:()=>true,escape:value=>String(value)};
 vm.createContext(scope);vm.runInContext(fs.readFileSync('stackarr/static/setup_accounts.js','utf8'),scope);
 return scope;
}
test('owned Plex library preparation remains accessible after reopening setup',()=>{
 const f=fixture([{id:'owned',state:'needs-setup',apps:['plex','seerr']}]);
 assert.match(f.accountSetupResult(),/Check Plex libraries/);
 f.state.accountReview={notice:'Review folders',libraries:[{name:'Movies',state:'create'}]};
 assert.match(f.accountSetupResult(),/id="accounts-apply"/);
});
test('connected external apps do not receive owned-library controls',()=>{
 const f=fixture([]);assert.equal(f.accountSetupResult(),'');
 f.setupDeployment.operations=[{id:'failed',state:'failed',apps:['plex']}];assert.equal(f.accountSetupResult(),'');
});
