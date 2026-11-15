const assert=require('node:assert/strict');
const test=require('node:test');
const fs=require('node:fs');
const vm=require('node:vm');
function fixture(readOnly=false){
 const ctx=vm.createContext({escape:value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'),Date});
 vm.runInContext(fs.readFileSync('stackarr/static/quality_rules.js','utf8'),ctx);
 ctx.readOnly=readOnly;
 vm.runInContext(`qualityState.data={revision:1,read_only:readOnly,history:[],notice:'New requests only'};
 qualityState.draft={enabled:true,before_year:2000,older:'SD',newer:'1080p',exceptions:[{media_id:11,title:'<title>',tier:'4K'}]};
 qualityState.review={scope:'future',policy:qualityState.draft,read_only:readOnly,profiles:[],changes:[],notice:'No searches'};`,ctx);
 return ctx;
}
test('rules distinguish premiere year, exceptions and explicit existing-library apply',()=>{
 const html=fixture().qualityRulesPanel();
 assert.match(html,/premiere year/);assert.match(html,/exceptions win/);assert.match(html,/Unknown years/);
 assert.match(html,/Save rules for new requests/);assert.match(html,/Preview existing library/);
 assert.match(html,/&lt;title&gt;/);assert.doesNotMatch(html,/<title>/);
});
test('native read-only UI offers a preview but no apply or library button',()=>{
 const html=fixture(true).qualityRulesPanel();
 assert.match(html,/Preview new-request rules/);assert.match(html,/read-only/);
 assert.doesNotMatch(html,/id="quality-apply"|id="quality-library"/);
});
test('undo is available for an uncertain operation and escapes upstream title names',()=>{
 const ctx=fixture();
 const html=ctx.qualityResults({rows:[{title:'<bad>',old_name:'Original',new_name:'4K',state:'uncertain'}],message:'Review'});
 assert.match(html,/Restore original profiles/);assert.match(html,/&lt;bad&gt;/);assert.match(html,/Later profile edits are preserved/);
});

test('download format controls explain hard blocks, label limits, and Dolby audio',()=>{
 const html=fixture().qualityRulesPanel();
 assert.match(html,/Block Dolby Vision downloads/);assert.match(html,/green and purple/);
 assert.match(html,/HDR10 hybrids/);assert.match(html,/Dolby Atmos audio stays allowed/);
 assert.match(html,/10-bit video/);assert.match(html,/H.264 \/ AVC/);assert.match(html,/H.265 \/ HEVC/);
 assert.match(html,/AV1/);assert.match(html,/VP9/);assert.match(html,/Avoid \(block\)/);
 assert.match(html,/missing or incorrect labels can bypass/);
});
test('changing a format invalidates the reviewed action and updates the draft',()=>{
 const ctx=fixture();const elements=Object.fromEntries(['quality-block-dv','quality-ten-bit','quality-codec-hevc','quality-apply'].map(id=>[id,{setAttribute(){this.disabled=true;}}]));
 ctx.document={getElementById:id=>elements[id],querySelectorAll:()=>[]};ctx.bindQualityRules();
 elements['quality-block-dv'].checked=true;elements['quality-block-dv'].onchange();
 elements['quality-ten-bit'].value='avoid';elements['quality-ten-bit'].onchange();
 elements['quality-codec-hevc'].value='prefer';elements['quality-codec-hevc'].onchange();
 assert.equal(vm.runInContext('qualityState.review',ctx),null);assert.equal(elements['quality-apply'].disabled,true);
 const value=JSON.parse(vm.runInContext('JSON.stringify(qualityState.draft.formats)',ctx));
 assert.equal(value.block_dolby_vision,true);assert.equal(value.ten_bit,'avoid');assert.equal(value.codecs.hevc,'prefer');
});
test('preview lists format decisions separately from quality',()=>{
 const ctx=fixture();vm.runInContext(`qualityState.review.formats=[{label:'Dolby Vision',action:'Block'},{label:'10-bit',action:'Prefer'}];qualityState.review.format_notice='Release labels only';`,ctx);
 const html=ctx.qualityRulesPanel();assert.match(html,/Block · Dolby Vision/);assert.match(html,/Prefer · 10-bit/);assert.match(html,/Release labels only/);
});
