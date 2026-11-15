"""Check status refresh in an isolated browser with synthetic data and no server."""

import argparse
import json
import re
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = (ROOT / "stackarr/static/app.js").read_text(encoding="utf-8")
    source = re.sub(r"\r?\nboot\(\);\s*$", "", source)
    errors = []
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for width, height in [(1440, 1000), (390, 844)]:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.on("pageerror", lambda error: errors.append(str(error)))
            # Every asset is local; the actual app, Docker and media remain untouched.
            page.route("**/*", lambda route: route.abort())
            page.set_content('<div id="root"></div><div id="announcer"></div>')
            page.add_style_tag(path=str(ROOT / "stackarr/static/theme.css"))
            page.add_style_tag(path=str(ROOT / "stackarr/static/app.css"))
            page.add_style_tag(path=str(ROOT / "stackarr/static/control_room.css"))
            page.add_script_tag(content="""
                var setupApprovalTimer, localLauncher = false, launcherApproved = true;
                var setupDeployment = {available: false, operations: [], actions: []};
                var bindSetup = () => {}, bindAccountSetup = () => {}, bindSetupExtras = () => {};
                var bindBackupPlan = () => {}, bindStackarrUpdates = () => {};
                var bindPresets = () => {}, bindCleanupPresets = () => {};
                var bindNativeImports = () => {}, bindQualityRules = () => {}, bindMediaSetup = () => {};
                var helpPanel = () => '';
                var backupSchedulePanel = () => '<section class="panel"><input id="backup-folder" value="saved"><div id="backup-result"></div><button id="backup-review">Review backup</button></section>';
                var setupScreen = () => '<section class="panel"><h2>Installation '+window.progress+'</h2><details><summary>Folder choices</summary><input id="setup-folder" value="saved"><input id="setup-secret" type="password"><div id="setup-scroll" style="width:180px;height:60px;overflow:scroll"><div style="width:600px;height:300px">Locations</div></div></details></section><div style="height:1500px"></div>';
                window.progress = 'queued';
            """)
            page.add_script_tag(path=str(ROOT / "stackarr/static/home.js"))
            page.add_script_tag(path=str(ROOT / "stackarr/static/browser_links.js"))
            page.add_script_tag(path=str(ROOT / "stackarr/static/control_room.js"))
            page.add_script_tag(content="window.fixtureSetupScreen=setupScreen;")
            page.add_script_tag(path=str(ROOT / "stackarr/static/preferences.js"))
            page.add_script_tag(content="setupScreen=window.fixtureSetupScreen;")
            page.add_script_tag(content=source + """
                window.fixture = {state, poll, render, renderPreservingContext};
                state.config = {dashboard: {page_size: 5, refresh_seconds: 60, order: ['radarr'], appearance: 'dark'}, integrations: {radarr: {enabled: true, visible: true, url: 'http://synthetic.invalid'}}};
                state.storageChecked=Date.now();state.config.dashboard.overview_widgets=['apps','downloads'];state.catalog = {radarr: {name: 'Radarr'}}; state.savedConfig = structuredClone(state.config);
                api = async path => {if(window.refreshFailure)throw new Error('Synthetic offline');return structuredClone(window.nextStatus);};
                window.statusFor = (count, suffix = 'initial') => ({
                    summaries: {downloads: {count, state: 'complete', sources: ['Radarr']}},
                    integrations: [{id: 'radarr', name: 'Radarr', url: 'http://synthetic.invalid', visible: true,
                        state: 'ready', stale: false, error: 'Synthetic warning '+suffix, error_code: 'fixture',
                        capabilities: ['downloads', 'health'], tables: {
                            downloads: Array.from({length: 8}, (_, i) => ({title: 'Synthetic movie '+i, state: i<count?'downloading':'seeding', detail: suffix})),
                            health: Array.from({length: 8}, (_, i) => ({title: 'Synthetic check '+i, state: 'downloading', detail: suffix}))
                        }}]
                });
                window.mount = view => {state.view = view;state.error = '';state.refreshError = '';state.status = statusFor(1);window.nextStatus = statusFor(2, 'updated');render();};
            """)

            page.evaluate("mount('overview')")
            page.locator("#overview-apps summary").click()
            page.locator("#refresh").focus()
            page.evaluate("window.originalMain=document.querySelector('#main');window.originalRefresh=document.querySelector('#refresh')")
            page.evaluate("fixture.poll()")
            assert page.evaluate("document.querySelector('#main')===window.originalMain && document.querySelector('#refresh')===window.originalRefresh && document.activeElement===window.originalRefresh")
            expect(page.locator("#overview-apps details")).to_have_attribute("open", "")
            expect(page.locator("#overview-apps")).to_contain_text("Synthetic warning updated")
            expect(page.locator("#overview-stats .stat").nth(1)).to_contain_text("2")

            page.locator("#overview-apps summary").focus()
            page.evaluate("window.focusedSummary=document.activeElement;window.nextStatus=statusFor(3,'later')")
            page.evaluate("fixture.poll()")
            assert page.evaluate("window.focusedSummary.isConnected && document.activeElement===window.focusedSummary")
            expect(page.locator("#overview-apps")).to_contain_text("Synthetic warning updated")
            expect(page.locator("#overview-stats .stat").nth(1)).to_contain_text("3")
            page.locator("#refresh").focus()
            page.evaluate("fixture.poll()")
            expect(page.locator("#overview-apps")).to_contain_text("Synthetic warning later")

            page.evaluate("mount('health');document.querySelector('#audit-output').textContent='Saved audit';document.querySelector('#jobs-output').textContent='Running connection check';document.querySelector('#notification-output').textContent='Pending notification'")
            page.locator("#filter").fill("Synthetic")
            page.evaluate("document.querySelector('#filter').setSelectionRange(2,5);window.originalFilter=document.querySelector('#filter')")
            page.evaluate("fixture.poll()")
            assert page.evaluate("document.activeElement===window.originalFilter && window.originalFilter.selectionStart===2 && window.originalFilter.selectionEnd===5")
            expect(page.locator("#filter")).to_have_value("Synthetic")
            expect(page.locator("#tables")).to_contain_text("updated")
            for selector, text in [("#audit-output", "Saved audit"), ("#jobs-output", "Running connection check"), ("#notification-output", "Pending notification")]:
                expect(page.locator(selector)).to_have_text(text)
            page.locator('[data-sort="state"]').click()
            assert page.evaluate("document.activeElement.dataset.sort==='state'")
            page.locator('[data-page="health"][data-direction="1"]').click()
            expect(page.locator(".pager")).to_contain_text("Page 2 of 2")
            assert page.evaluate("document.activeElement.classList.contains('pager')")
            expect(page.locator("#audit-output")).to_have_text("Saved audit")

            page.locator("#filter").focus()
            page.evaluate("""() => {
                const text=document.querySelector('#tables tbody td:nth-child(2)').firstChild;
                const range=document.createRange();range.selectNodeContents(text);
                getSelection().removeAllRanges();getSelection().addRange(range);
                window.selectedText=text;window.nextStatus=statusFor(4,'selected');
            }""")
            page.evaluate("fixture.poll()")
            assert page.evaluate("window.selectedText.isConnected && !getSelection().isCollapsed")
            page.evaluate("getSelection().removeAllRanges()")
            page.evaluate("fixture.poll()")
            expect(page.locator("#tables")).to_contain_text("selected")

            # Refresh errors have their own banner and never discard action output.
            page.evaluate("fixture.state.error='Keep this action error';window.refreshFailure=true")
            page.evaluate("fixture.poll()")
            expect(page.locator("#status-refresh-error")).to_contain_text("Displayed data may be stale")
            expect(page.locator("#audit-output")).to_have_text("Saved audit")
            page.evaluate("window.refreshFailure=false")
            page.evaluate("fixture.poll()")
            expect(page.locator("#status-refresh-error")).to_have_count(0)
            assert page.evaluate("fixture.state.error==='Keep this action error'")

            page.evaluate("mount('backups');document.querySelector('#backup-result').textContent='Review is ready';fixture.state.dirty=true")
            page.locator("#backup-folder").fill("unsaved destination")
            page.evaluate("window.backupInput=document.querySelector('#backup-folder');window.backupOutput=document.querySelector('#backup-result')")
            page.evaluate("fixture.poll()")
            assert page.evaluate("window.backupInput.isConnected && window.backupOutput.isConnected && fixture.state.dirty")
            expect(page.locator("#backup-folder")).to_have_value("unsaved destination")
            expect(page.locator("#backup-result")).to_have_text("Review is ready")

            page.evaluate("mount('setup')")
            page.locator("summary").click()
            page.locator("#setup-folder").fill("unsaved media location")
            page.locator("#setup-secret").fill("do not retain this secret")
            page.locator("#setup-folder").focus()
            page.evaluate("document.querySelector('#setup-folder').setSelectionRange(3,9);document.querySelector('#setup-scroll').scrollLeft=80;document.querySelector('#setup-scroll').scrollTop=35;window.scrollTo(0,120);fixture.state.dirty=true;fixture.state.appDirty=true;window.progress='complete'")
            position = page.evaluate("scrollY")
            page.evaluate("window.dirtyFolder=document.querySelector('#setup-folder');window.dirtySecret=document.querySelector('#setup-secret')")
            page.evaluate("fixture.renderPreservingContext()")
            expect(page.get_by_role("heading", name="Installation queued")).to_have_count(1)
            expect(page.locator("#setup-secret")).to_have_value("do not retain this secret")
            assert page.evaluate("window.dirtyFolder.isConnected && window.dirtySecret.isConnected && document.activeElement===window.dirtyFolder && fixture.state.dirty && fixture.state.appDirty")
            assert page.evaluate("scrollY") == position
            # A later clean refresh may rebuild the screen and still keeps context.
            page.evaluate("fixture.state.dirty=false;fixture.state.appDirty=false")
            page.evaluate("fixture.renderPreservingContext()")
            expect(page.get_by_role("heading", name="Installation complete")).to_have_count(1)
            expect(page.locator("details")).to_have_attribute("open", "")
            expect(page.locator("#setup-folder")).to_have_value("unsaved media location")
            expect(page.locator("#setup-secret")).to_have_value("")
            assert page.evaluate("document.activeElement.id==='setup-folder' && document.activeElement.selectionStart===3 && document.activeElement.selectionEnd===9 && !fixture.state.dirty && !fixture.state.appDirty")
            assert page.evaluate("document.querySelector('#setup-scroll').scrollLeft===80 && document.querySelector('#setup-scroll').scrollTop===35")
            assert page.evaluate("scrollY") == position
            page.screenshot(path=str(args.output / f"refresh-{width}.png"), full_page=False)
            results.append({"width": width, "passed": True})
            page.close()
        browser.close()
    assert not errors, errors
    report = {"passed": True, "viewports": results, "scenarios": [
        "targeted overview status updates", "focused regions retained", "expanded connection details",
        "filter focus and selection", "sort and pagination focus", "selected text retained",
        "health outputs retained", "refresh failure and recovery", "backup draft and review retained",
        "dirty setup form and newly entered secret remain mounted", "clean setup context retained without passwords",
        "window and inner scroll retained",
    ], "page_errors": errors}
    (args.output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
