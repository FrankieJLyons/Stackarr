"""Exercise real UI assets with synthetic app state; never contact household apps."""

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

from stackarr.config import CATALOG, Config

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "stackarr/static"


def check(output):
    output.mkdir(parents=True, exist_ok=False)
    config = Config().model_dump()
    enabled = [key for key in CATALOG if key != "seerr"]
    for key in enabled:
        config["integrations"][key].update(enabled=True, url=f"http://localhost:{CATALOG[key]['port']}")
    errors, unexpected = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100}, reduced_motion="reduce")
        page.on("pageerror", lambda error: errors.append(str(error)))

        def asset(route):
            parsed = urlsplit(route.request.url)
            if parsed.hostname != "stackarr.test":
                unexpected.append(route.request.url)
                route.abort()
                return
            if parsed.path == "/api/appearance/icon.svg":
                route.fulfill(path=str(STATIC / "favicon.svg"))
                return
            name = "index.html" if parsed.path == "/" else parsed.path.removeprefix("/static/")
            if name.startswith("/") or ".." in name.split("/") or not (STATIC / name).is_file():
                route.fulfill(status=404, body="Not a fixture asset")
                return
            if parsed.path == "/api/appearance/icon.svg":
                route.fulfill(path=str(STATIC / "favicon.svg"))
                return
            if name == "app.js":
                source = re.sub(r"\r?\nboot\(\);\s*$", "", (STATIC / name).read_text(encoding="utf-8"))
                route.fulfill(content_type="text/javascript", body=source)
            else:
                route.fulfill(path=str(STATIC / name))

        page.route("**/*", asset)
        page.goto("http://stackarr.test/")
        page.evaluate("""({config,catalog})=>{
            state.config=config;state.savedConfig=structuredClone(config);state.catalog=catalog;
            state.credentials=Object.keys(catalog);state.network={origin:'http://stackarr.test'};
            state.view='overview';state.revision=1;
            state.status={summaries:{downloads:{count:3,state:'complete',sources:['qBittorrent']},queue:{count:5,state:'complete',sources:['Sonarr','Radarr']},streams:{count:1,state:'complete',sources:['Plex']}},
                integrations:Object.keys(catalog).filter(key=>config.integrations[key].enabled).map(key=>({id:key,name:catalog[key].name,visible:true,url:config.integrations[key].url,state:key==='radarr'?'error':'ready',stale:false,collected_at:1800000000,error:key==='radarr'?'Synthetic connection issue':'',tables:{downloads:key==='qbittorrent'?[{title:'Permitted sample',state:'downloading',detail:'64%'}]:[],streams:key==='plex'?[{title:'Sample stream',state:'playing'}]:[],queue:key==='sonarr'?[{title:'Sample episode',state:'queued'}]:[],sources:key==='prowlarr'?[{title:'Example source',state:'enabled'}]:[],blocklist:[],health:[],monitoring:[]},capabilities:key==='plex'?['streams']:key==='qbittorrent'?['downloads']:key==='prowlarr'?['sources','health']:['sonarr','radarr'].includes(key)?['queue','blocklist','health']:key==='kuma'?['monitoring']:['health']}))};
            setupDeployment={available:true,operations:[{id:'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',state:'needs-setup',apps:Object.keys(catalog).filter(key=>config.integrations[key].enabled),links:[]}],actions:[]};
            setupDraft={revision:1,draft:{step:2,apps:['sonarr'],choices:{sonarr:{mode:'install'}},data_root:'C:/Media',port_mode:'automatic'}};
            window.fixtureCalls=[];window.fixtureStopped=false;loadSetup=async()=>{};state.storageOverview={available:true,free_gb:120,total_gb:500};
            api=async(path,method='GET',body)=>{
                fixtureCalls.push({path,method,body});
                if(path==='onboarding'&&method==='GET')return structuredClone(setupDraft);
                if(path==='onboarding'&&method==='PUT')return {revision:body.revision+1,draft:body.draft};
                if(path.endsWith('/check'))return {apps:[{app:'sonarr',state:fixtureStopped?'stopped':'running',actions:[fixtureStopped?'start':'restart']}]};
                if(path.endsWith('/apps/sonarr/review'))return {name:'Sonarr',action:body.action,deployment:'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',review_token:'synthetic-review',notice:'Restart only this app. Its settings and media stay in place.'};
                if(path==='deployments/actions/apply')return {id:'synthetic-action'};
                if(path==='onboarding/readiness')return [];
                if(path==='onboarding/storage')return {required:false,valid:true,folders:[]};
                if(path==='onboarding/suggest-ports')return {suggestions:[]};
                if(path==='onboarding/check-ports')return {ports:[{app:'seerr',port:5055,status:'available'}]};
                if(path==='onboarding/plan')return {};
                if(path==='deployments/review')return {review_token:'fixture-install',notice:'Install the selected Seerr app after approval.',apps:[{name:'Seerr',port:5055}],create_folders:[]};
                if(path==='deployments/install'){if(body.review_token!=='fixture-install')throw new Error('Review required');setupDeployment.operations.push({id:'fixture-new-app',state:'queued',phase:'queued',apps:['seerr'],links:[],message:'New app installation queued.'});return {id:'fixture-new-app'};}
                if(path==='deployments')return {...setupDeployment,actions:[{state:'succeeded',message:'Synthetic app action completed.',updated:1800000000}]};
                if(path==='status')return structuredClone(state.status);
                throw new Error('Unexpected fixture request: '+path);
            };
            render();
        }""", {"config": config, "catalog": CATALOG})
        expect(page.get_by_role("heading", name="Media Stack", exact=True)).to_be_visible()
        for title in ["Library & playback", "Requests & downloads", "Tools & monitoring"]:
            expect(page.get_by_role("heading", name=title, exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="Restart Sonarr", exact=True)).to_be_visible()
        page.screenshot(path=str(output / "control-room-desktop.png"), full_page=True)

        page.get_by_role("button", name="Restart Sonarr", exact=True).click()
        expect(page.get_by_role("button", name="Restart app", exact=True)).to_be_visible()
        assert not page.evaluate("fixtureCalls.some(row=>row.path.endsWith('/apply'))")
        page.get_by_role("button", name="Cancel", exact=True).click()
        page.evaluate("window.fixtureStopped=true")
        page.get_by_role("button", name="Restart Sonarr", exact=True).click()
        expect(page.get_by_role("button", name="Start app", exact=True)).to_be_visible()
        page.get_by_role("button", name="Start app", exact=True).click()
        assert page.evaluate("fixtureCalls.some(row=>row.path==='deployments/actions/apply')")
        expect(page.locator("#lifecycle-history")).to_have_count(0)

        # Refreshed cards retain handlers and imported apps never get a power button.
        page.evaluate("state.config.integrations.sonarr.read_only=true;refreshStatusRegions()")
        expect(page.get_by_role("button", name="Restart Sonarr", exact=True)).to_have_count(0)
        page.get_by_role("button", name="Manage Sonarr", exact=True).click()
        expect(page.locator('.settings-app[open]')).to_be_visible()
        page.locator('.control-tabs [data-view="overview"]').click()

        page.locator('.control-tabs [data-view="apps"]').click()
        expect(page.get_by_role("heading", name="Apps", exact=True)).to_be_visible()
        expect(page.locator(".stack-service")).to_have_count(0)
        page.get_by_role("button", name="Set up Seerr", exact=True).click()
        dialog = page.get_by_role("dialog")
        expect(dialog.get_by_role("heading", name="Set up Seerr", exact=True)).to_be_visible()
        page.screenshot(path=str(output / "add-app-desktop.png"), full_page=True)
        dialog.get_by_role("button", name="Cancel", exact=True).click()
        assert not page.evaluate("fixtureCalls.some(row=>row.path==='onboarding'&&row.method==='PUT')")
        page.get_by_role("button", name="Set up Seerr", exact=True).click()
        page.get_by_label("How would you like to add Seerr?", exact=True).select_option("connect")
        page.get_by_label("Seerr address", exact=True).fill("http://existing-server:5055")
        page.get_by_role("button", name="Continue to setup", exact=True).click()
        expect(page.locator("#setup-mode-seerr")).to_have_value("connect")
        assert page.evaluate("setupDraft.draft.apps.length===1 && setupDraft.draft.apps[0]==='seerr' && setupDraft.draft.data_root==='C:/Media'")
        assert not page.evaluate("fixtureCalls.some(row=>row.path.includes('install-apply'))")

        # The catalog's install branch reaches the real setup controls and review boundary.
        page.locator('.control-tabs [data-view="apps"]').click()
        page.get_by_role("button", name="Set up Seerr", exact=True).click()
        page.get_by_role("button", name="Continue to setup", exact=True).click()
        expect(page.locator("#setup-mode-seerr")).to_have_value("install")
        page.get_by_role("button", name="Save & continue", exact=False).click()
        page.get_by_role("button", name="Save & continue", exact=False).click()
        page.get_by_role("button", name="Review installation", exact=True).click()
        assert not page.evaluate("fixtureCalls.some(row=>row.path==='deployments/install')")
        page.get_by_role("button", name="Download & install these apps", exact=True).click()
        expect(page.get_by_text("New app installation queued.", exact=True)).to_be_visible()
        assert page.evaluate("fixtureCalls.filter(row=>row.path==='deployments/install').length===1")

        page.locator('.control-tabs [data-view="settings"]').click()
        page.locator('[data-settings-section="appearance"]').click()
        expect(page.get_by_role("heading", name="Colour & appearance", exact=True)).to_be_visible()
        for accent in ["blue", "red", "yellow", "green", "orange", "purple"]:
            for mode in ["dark", "light"]:
                page.get_by_label("App colour", exact=True).select_option(accent)
                page.get_by_label("Appearance", exact=True).select_option(mode)
                expect(page.locator("html")).to_have_attribute("data-accent", accent)
                expect(page.locator("html")).to_have_attribute("data-theme", mode)
                contrast=page.locator('.theme-preview .primary').evaluate("""el=>{
                    const css=getComputedStyle(el), rgb=value=>value.match(/[0-9.]+/g).slice(0,3).map(Number).map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4;});
                    const lum=value=>{const c=rgb(value);return c[0]*.2126+c[1]*.7152+c[2]*.0722;};
                    const a=lum(css.color),b=lum(css.backgroundColor);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
                }""")
                assert contrast>=4.5,(accent,mode,contrast)
        page.get_by_label("Active downloads", exact=True).uncheck()
        assert page.evaluate("!readForm().config.dashboard.overview_widgets.includes('downloads')")
        page.screenshot(path=str(output / "settings-purple-light.png"), full_page=True)
        page.evaluate("state.dirty=false;theme();state.view='setup';state.setupTask='';setupDeployment.journey={draft_revision:setupDraft.revision,summary:{done:1,total:3},checkpoints:[{id:'choices',title:'Choose apps',detail:'Saved choices',state:'done',apps:[]},{id:'plex-connect',title:'Connect Plex',detail:'Sign in to the server you use.',state:'needs-action',apps:['plex'],action:{id:'accounts',app:'plex',label:'Connect Plex'}},{id:'sources',title:'Choose content sources',detail:'Add a source when Prowlarr is connected.',state:'needs-action',apps:['prowlarr'],action:{id:'source-setup',label:'Choose sources'}}]};state.credentials=state.credentials.filter(key=>key!=='prowlarr');render();")
        expect(page.locator('[data-checkpoint="sources"] button')).to_be_disabled()
        expect(page.locator('[data-checkpoint="sources"]')).to_contain_text('Connect Prowlarr')
        page.screenshot(path=str(output / "setup-checklist.png"), full_page=True)
        page.get_by_role('button', name='Connect Plex', exact=True).click()
        expect(page.get_by_role('heading', name='Reconnect Plex', exact=True)).to_be_visible()
        expect(page.get_by_role('button', name='Check Plex sign-in & continue', exact=True)).to_be_visible()
        page.locator('.control-tabs [data-view="health"]').click()
        expect(page.get_by_role('heading', name='App action history', exact=True)).to_be_visible()
        page.locator('#health-apps .connection-details summary').first.click()
        expect(page.locator('#health-apps .connection-details')).to_contain_text('Last successful check')
        page.screenshot(path=str(output / "health-details-history.png"), full_page=True)
        page.locator('.control-tabs [data-view="overview"]').click()
        for width, name in [(390, "phone"), (768, "tablet")]:
            page.set_viewport_size({"width": width, "height": 1000})
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            page.screenshot(path=str(output / f"control-room-{name}.png"), full_page=True)
            page.get_by_role('button', name='Add app +', exact=True).click()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            expect(page.get_by_role('heading', name='Apps', exact=True)).to_be_visible()
            page.locator('.control-tabs [data-view="overview"]').click()
        page.evaluate("document.documentElement.style.fontSize='200%'")
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        assert not errors, errors
        assert not unexpected, unexpected
        browser.close()
    report = {"passed": True, "scope": "Real static UI; synthetic APIs; no household app requests", "cases": ["original-layout", "review-before-restart", "stopped-app-start", "read-only-import", "refresh-rebind", "scoped-add-app", "preserve-storage", "mobile-tablet-zoom", "install-review-apply-boundary", "six-palettes-light-dark", "ordered-checklist-blockers", "repair-navigation", "health-action-history", "widget-preferences"]}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(check(parser.parse_args().output)))
