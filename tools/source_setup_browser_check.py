"""Exercise source setup UI with synthetic provider APIs and no external access.

This checks provider forms, review/test/save, error handling, source search states,
keyboard focus and desktop/mobile layout. It does not certify a real provider,
request, download, import or Plex playback. The live alpha remains untouched.
"""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]

FIXTURE = r"""
const root = document.querySelector('#root');
const state = {view:'setup',dirty:false,appDirty:false,indexerDirty:false,credentials:['prowlarr'],
  config:{integrations:{prowlarr:{enabled:true,url:'http://synthetic.invalid/prowlarr'},
    plex:{enabled:true,url:'http://synthetic.invalid/plex'},radarr:{enabled:true},sonarr:{enabled:true}}}};
let setupDeployment = {operations:[],web_login_apps:[]};
let selectedApps = new Set(['prowlarr','plex','radarr','sonarr']);
const setupAppSelected = key => selectedApps.has(key);
const escape = value => String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const field = (label,id,value,type='text',extra='') => `<div class="field"><label for="${id}">${label}</label><input id="${id}" value="${escape(value)}" type="${type}" ${extra}></div>`;
const announce = text => document.querySelector('#announcer').textContent = text;
let calls = [], validationState = 'results', sourceAdded = false, sharing = 0, unavailable = false, failReview = false, connectionReviews = 0;
let deferReview = false, pendingReview = null, deferSearch = false, pendingSearch = null;
const provider = {id:'synthetic-provider',name:'Example provider',privacy:'private',supported:true,fields:[
  {name:'accountName',label:'Provider account name',type:'text',required:true,help:'The account name supplied by your provider.'},
  {name:'apiKey',label:'Provider key',type:'password',private:true,required:true,help:'Copy this from your provider account settings.'},
  {name:'tier',label:'Account type',type:'select',required:true,options:[{value:'standard',label:'Standard'}]},
]};
async function api(path,method='GET',body) {
  calls.push({path,method,body});
  if(path==='indexers/catalog')return {providers:[provider],notice:'Provider forms supplied by your connected Prowlarr app.'};
  if(path==='indexers/providers/review'||path==='indexers/review') {
    if(failReview)throw new Error('The provider is unavailable. Try again later.');
    const result={name:body.name,provider:provider.name,review_token:'synthetic-review',already_exists:false,notice:'Test this provider and connect it. No media is downloaded.'};
    if(deferReview)return new Promise(resolve=>{pendingReview=()=>resolve(result);});
    return result;
  }
  if(path==='indexers/apply') {sourceAdded=true;return {state:'connected',detail:'Source tested and saved. Check source sharing.'};}
  if(path==='indexers/status')return {sources:sourceAdded?[{name:'My source',enabled:true}]:[],apps:[
    {app:'sonarr',name:'Sonarr',shared_sources:unavailable?null:sharing,state:unavailable?'unavailable':'checked'},
    {app:'radarr',name:'Radarr',shared_sources:sharing}]};
  if(path==='indexers/validate') {
    const result={media_type:body.media_type,state:validationState,notice:'Synthetic source search; no request or download.',limited:false,
    sources:[{name:'My source',state:validationState==='needs-attention'?'authentication-failed':validationState,
      detail:validationState==='needs-attention'?'Check your provider account key.':validationState==='no-matches'?'Connection and categories passed.':'The source returned a matching release.',
      result_count:validationState==='needs-attention'?null:validationState==='no-matches'?0:1}]};
    if(deferSearch)return new Promise(resolve=>{pendingSearch=()=>resolve(result);});
    return result;
  }
  if(path==='deployments')return {operations:[],journey:{checkpoints:[]}};
  throw new Error('Unexpected synthetic endpoint: '+path);
}
function render() {
  state.dirty=state.appDirty=state.indexerDirty=false;
  root.innerHTML=indexerPanel()+'<section class="panel"><button id="wiring-preview">Review app connections</button><button id="test">Test app connections</button><p id="connection-result"></p></section>';
  bindSetupExtras();
  root.querySelectorAll('input,select').forEach(input=>{if(input.dataset.setupControl!=='navigation')input.addEventListener('input',()=>{state.dirty=state.indexerDirty=true;});});
  document.querySelector('#wiring-preview').onclick=async()=>{connectionReviews++;sharing=1;document.querySelector('#connection-result').textContent='Reviewed synthetic app connections.';};
  document.querySelector('#test').onclick=async()=>{document.querySelector('#connection-result').textContent='Sonarr needs reconnecting.';};
}
function renderPreservingContext() {
  if(state.dirty)return;
  const openIds=[...document.querySelectorAll('details[open]')].map(item=>item.id);
  const values=[...document.querySelectorAll('input,select')].filter(item=>item.type!=='password').map(item=>[item.id,item.value]);
  const focused=document.activeElement?.id;
  render();
  openIds.forEach(id=>{const item=document.getElementById(id);if(item)item.open=true;});
  values.forEach(([id,value])=>{const item=document.getElementById(id);if(item)item.value=value;});
  document.getElementById(focused)?.focus();
}
window.fixture={state,render,get calls(){return calls;},resetCalls(){calls=[];},
  setValidation(value){validationState=value;},failReview(value){failReview=value;},
  setUnavailable(value){unavailable=value;},
  deferReview(value){deferReview=value;},resolveReview(){pendingReview();},
  deferSearch(value){deferSearch=value;},resolveSearch(){pendingSearch();},
  selectOnly(keys){selectedApps=new Set(keys);render();},get connectionReviews(){return connectionReviews;}};
"""


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    errors = []
    cases = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for width, height in [(1440, 1000), (390, 844)]:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.route("**/*", lambda route: route.abort())
            page.set_content('<main id="root" class="content"></main><div id="announcer" role="status"></div>')
            page.add_style_tag(path=str(ROOT / "stackarr/static/theme.css"))
            page.add_style_tag(path=str(ROOT / "stackarr/static/app.css"))
            page.add_script_tag(content=FIXTURE)
            page.add_script_tag(path=str(ROOT / "stackarr/static/setup_extras.js"))
            page.evaluate("fixture.render()")
            expect(page.get_by_role("heading", name="Where will your media come from?")).to_be_visible()
            expect(page.locator("#indexer-advanced")).not_to_have_attribute("open", "")
            page.locator("#indexer-advanced summary").first.click()
            page.locator("#indexer-torznab summary").click()
            page.locator("#indexer-name").fill("Original feed")
            page.locator("#indexer-url").fill("https://source.synthetic.invalid/api")
            page.locator("#indexer-key").fill("first-key")
            page.evaluate("fixture.deferReview(true)")
            page.locator("#indexer-review").click()
            page.locator("#indexer-key").fill("newer-feed-key")
            page.evaluate("fixture.resolveReview()")
            page.wait_for_function("!fixture.state.indexerBusy")
            expect(page.locator("#indexer-key")).to_have_value("newer-feed-key")
            expect(page.locator("#indexer-apply")).to_have_count(0)
            assert page.evaluate("fixture.state.indexerDirty")
            page.locator("#indexer-torznab-reset").click()
            page.evaluate("fixture.deferReview(false)")
            page.locator("#indexer-advanced summary").first.click()
            page.locator("#indexer-load-providers").click()
            page.locator("#indexer-provider").select_option("synthetic-provider")
            assert not page.evaluate("fixture.state.dirty")
            expect(page.get_by_text("This provider needs its own account.", exact=False)).to_be_visible()
            page.get_by_text('Review before connecting', exact=True).click()

            page.locator("#indexer-provider-review").click()
            assert not page.evaluate("fixture.calls.some(call=>call.path==='indexers/providers/review')")
            fields = page.locator("#indexer-provider-details input")
            page.locator("#indexer-provider-name").fill("My source")
            fields.nth(1).fill("sample-account")
            fields.nth(2).fill("synthetic-provider-private-key")
            page.locator("#indexer-provider-details select").select_option("standard")
            assert page.evaluate("fixture.state.indexerDirty")

            page.locator("#indexers-check").click()
            expect(page.locator("#indexer-error")).to_contain_text("Review or clear")
            expect(fields.nth(2)).to_have_value("synthetic-provider-private-key")
            page.evaluate("fixture.deferReview(true)")
            page.locator("#indexer-provider-review").click()
            fields.nth(2).fill("newer-provider-key")
            page.evaluate("fixture.resolveReview()")
            page.wait_for_function("!fixture.state.indexerBusy")
            expect(fields.nth(2)).to_have_value("newer-provider-key")
            expect(page.locator("#indexer-apply")).to_have_count(0)
            assert page.evaluate("fixture.state.indexerDirty")
            page.evaluate("fixture.deferReview(false)")
            page.locator("#indexer-provider-review").click()
            expect(page.locator("#indexer-review-result")).to_contain_text("Review this source")
            assert not page.evaluate("JSON.stringify(fixture.state).includes('synthetic-provider-private-key')")
            expect(page.locator("#indexer-provider-details input[type=password]")).to_have_value("")
            page.locator("#indexer-apply").click()
            expect(page.locator("#indexer-sharing-result")).to_contain_text("0 source(s)")
            page.locator("#indexer-review-connections").click()
            assert page.evaluate("fixture.connectionReviews") == 1
            expect(page.locator("#wiring-preview")).to_be_focused()
            page.locator("#indexers-check").click()
            expect(page.locator("#indexer-sharing-result")).to_contain_text("1 source(s)")
            page.evaluate("fixture.setUnavailable(true)")
            page.locator("#indexers-check").click()
            expect(page.locator("#indexer-sharing-result")).to_contain_text("Sonarr: sharing is unavailable")
            expect(page.locator("#indexer-sharing-result")).not_to_contain_text("Sonarr: 0 source")
            page.locator("#indexer-test-connections").click()
            expect(page.locator("#test")).to_be_focused()
            expect(page.locator("#connection-result")).to_contain_text("Sonarr needs reconnecting")
            page.evaluate("fixture.setUnavailable(false)")
            page.locator("#indexers-check").click()

            page.locator("#indexer-validation summary").click()
            page.locator("#indexer-validation-query").fill("Original sample")
            page.locator("#indexer-validation-type").select_option("movie")
            assert not page.evaluate("fixture.state.dirty")
            page.evaluate("fixture.resetCalls()")
            page.locator("#indexers-validate").click()
            expect(page.locator("#indexer-validation-result")).to_contain_text("Search results found")
            assert page.evaluate("fixture.calls.map(call=>call.path)") == ["indexers/validate", "deployments"]
            expect(page.locator("#indexer-validation-query")).to_have_value("Original sample")
            page.evaluate("fixture.deferSearch(true)")
            page.locator("#indexers-validate").click()
            page.locator("#indexer-validation-query").fill("Another sample")
            page.evaluate("fixture.resolveSearch()")
            page.wait_for_function("!fixture.state.indexerBusy")
            expect(page.locator("#indexer-validation-result")).to_have_count(0)
            expect(page.locator("#indexer-validation-query")).to_have_value("Another sample")
            page.evaluate("fixture.deferSearch(false)")
            page.locator("#indexer-validation-query").fill("Original sample")
            page.evaluate("fixture.setValidation('no-matches')")
            page.locator("#indexers-validate").click()
            expect(page.locator("#indexer-validation-result")).to_contain_text("Sources responded, but no matching copy was found")
            expect(page.locator("#indexer-validation-result")).to_contain_text("0 result(s)")
            page.evaluate("fixture.setValidation('needs-attention')")
            page.locator("#indexers-validate").click()
            expect(page.locator("#indexer-validation-result")).to_contain_text("Provider sign-in or key rejected")
            expect(page.locator("#indexer-validation-result")).not_to_contain_text("0 result(s)")
            expect(page.locator("#indexer-validation-result")).not_to_contain_text("Ready to watch")

            page.evaluate("document.querySelector('#announcer').textContent=''")
            page.screenshot(path=str(output / f"sources-{width}.png"), full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth"), f"Overflow at {width}px"
            page.evaluate("fixture.selectOnly(['plex'])")
            expect(page.locator("#indexer-setup")).to_have_count(0)
            cases.append({"width": width, "provider_review": "passed", "secret_cleared": True,
                          "inflight_source_edits": "preserved and stale review discarded",
                          "inflight_query_edit": "stale search presentation discarded",
                          "sharing_and_connection_action": "passed", "search_state_separation": "passed",
                          "unselected_apps": "no source task", "horizontal_overflow": False})
            page.close()
        browser.close()
    assert not errors, errors
    report = {"scope": "Synthetic source UI only; no real provider, media or alpha operations",
              "scenarios": cases, "browser_errors": errors}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.output)


if __name__ == "__main__":
    main()
