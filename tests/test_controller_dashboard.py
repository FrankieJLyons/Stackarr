import pytest
from fastapi.testclient import TestClient

from stackarr.config import APP_IDS
from stackarr.controller_transport import ControllerConnectionError
from stackarr.server import create_app


class Remote:
    def __init__(self):
        self.calls = []
        self.connected = True
        self.operations = []
        self.media_path = ""

    async def request(self, operation, payload=None):
        if not self.connected:
            raise ControllerConnectionError("Installation connection unavailable. Check progress before trying again")
        self.calls.append((operation, payload))
        if operation == "status":
            return {"operations": self.operations, "folder_browser": bool(self.media_path)}
        if operation == "folders":
            if payload["root"] is None:
                return {"roots": [{"id": 0, "name": "Approved media"}]}
            return {"root": 0, "relative": payload["relative"], "host_path": self.media_path,
                    "name": "Approved media", "folders": []}
        if operation == "ports":
            return {"ports": [{"app": "kuma", "name": "Uptime Kuma", "port": 28009, "status": "available"}]}
        if operation == "suggest-ports":
            return {"suggestions": [{"app": "kuma", "name": "Uptime Kuma", "previous": 28009, "port": 28009}]}
        if operation == "review":
            return {"review_reference": "host-secret-reference-value-1234567890", "plan": {
                "apps": [{"id": "kuma", "name": "Uptime Kuma", "port": 28009}],
                "media_folder": self.media_path, "create_folders": [], "library_setup": [], "notice": "Reviewed on host",
            }}
        if operation == "install":
            assert payload == {"review_reference": "host-secret-reference-value-1234567890"}
            self.operations = [{"id": "a" * 32, "state": "queued", "apps": ["kuma"], "message": "Waiting"}]
            return {"id": "a" * 32}
        if operation == "resume":
            return {"id": payload["id"]}
        if operation == "installation-check":
            return {"apps": [{"app": "plex", "state": "running"}]}
        if operation == "managed-review":
            return {"review_reference": "host-secret-reference-value-1234567890", "deployment": payload["id"],
                    "action": payload["action"], "name": "Plex", "notice": "Reviewed operation", "apps": ["Plex"]}
        if operation == "managed-apply":
            assert payload == {"review_reference": "host-secret-reference-value-1234567890"}
            return {"id": "b" * 32}
        if operation == "app-backups":
            return {"backups": []}
        raise AssertionError(operation)


def dashboard(tmp_path, monkeypatch):
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "rpc.key").write_bytes(b"x" * 32)
    monkeypatch.setenv("STACKARR_CONTROLLER_SHARED", str(shared))
    remote = Remote()
    monkeypatch.setattr("stackarr.controller_enrollment.client", lambda path: remote)
    app = create_app(tmp_path / "dashboard", origin="http://testserver", background=False)
    return app, remote


def authorize(browser, app):
    headers = {"Origin": "http://testserver"}
    password = "synthetic test password"
    assert browser.post("/api/setup", json={"password": password,
        "setup_token": (app.state.store.root / "setup-token").read_text()}, headers=headers).status_code == 200
    login = browser.post("/api/login", json={"password": password}, headers=headers)
    assert login.status_code == 200
    return {**headers, "X-CSRF-Token": login.json()["csrf"]}


def test_discovery_runs_on_host_and_returns_separate_api_and_browser_addresses(tmp_path, monkeypatch):
    app, remote = dashboard(tmp_path, monkeypatch)
    async def discover(operation, payload=None):
        assert operation == 'discover' and payload['apps'] == list(APP_IDS)
        return {'scope':'localhost-and-docker-ports', 'message':'Hints only', 'results':[
            {'app':'sonarr', 'address':'http://127.0.0.1:18989','state':'credentials-required','adopted':False}]}
    monkeypatch.setattr(remote, 'request', discover)
    with TestClient(app) as browser:
        headers = authorize(browser, app)
        assert browser.post('/api/onboarding/discover').status_code == 403
        result = browser.post('/api/onboarding/discover', headers=headers)
        assert result.status_code == 200
        row = result.json()['results'][0]
        assert row['address'] == 'http://host.docker.internal:18989'
        assert row['browser_address'] == 'http://127.0.0.1:18989'
        assert not app.state.store.config()[1].integrations['sonarr'].enabled


def test_connection_only_launcher_exposes_discovery_without_install_permission(tmp_path):
    app = create_app(tmp_path, origin='http://testserver', host_checks=True, background=False)
    with TestClient(app) as browser:
        authorize(browser, app)
        status = browser.get('/api/deployments').json()
        assert status['host_checks'] and not status['available'] and status['operations'] == []


def test_install_approval_retains_quality_independently_of_later_draft_changes(tmp_path, monkeypatch):
    import json

    app, remote = dashboard(tmp_path, monkeypatch)
    remote.media_path = "C:/Alpha Media"
    with TestClient(app) as browser:
        headers = authorize(browser, app)
        draft = {"apps": ["sonarr"], "data_root": remote.media_path, "folder_root": 0,
                 "choices": {"sonarr": {"port": 28989, "quality_profile": "HD-1080p"}}}
        assert browser.put("/api/onboarding", json={"revision": 1, "draft": draft}, headers=headers).status_code == 200
        review = browser.post("/api/deployments/review", headers=headers)
        assert review.status_code == 200
        intent = next(payload for operation, payload in remote.calls if operation == "review")
        assert intent["quality_profiles"] == {"sonarr": "HD-1080p"}
        installed = browser.post("/api/deployments/install", json={"review_token": review.json()["review_token"]}, headers=headers)
        assert installed.status_code == 202
    with app.state.store.db() as db:
        saved = db.execute("SELECT profiles FROM controller_quality_profiles WHERE id=?", (installed.json()["id"],)).fetchone()
    assert json.loads(saved[0]) == {"sonarr": "HD-1080p"}


def test_remote_lifecycle_backup_restore_are_reviewed_session_bound_and_single_use(tmp_path, monkeypatch):
    app, remote = dashboard(tmp_path, monkeypatch)
    with TestClient(app) as browser:
        headers = authorize(browser, app)
        identity = "a" * 32
        for path, payload in [(f"deployments/{identity}/apps/plex/review", {"action": "restart"}),
                              (f"deployments/{identity}/backup-review", {"action": "backup"}),
                              (f"deployments/{identity}/backup-review", {"action": "restore", "backup": "c" * 32})]:
            assert browser.post("/api/" + path, json=payload).status_code == 403
            reviewed = browser.post("/api/" + path, json=payload, headers=headers)
            assert reviewed.status_code == 200
            assert "host-secret-reference" not in reviewed.text
            token = reviewed.json()["review_token"]
            assert browser.post("/api/deployments/actions/apply", json={"review_token": token}, headers=headers).status_code == 202
            assert browser.post("/api/deployments/actions/apply", json={"review_token": token}, headers=headers).status_code == 409
        assert browser.get("/api/app-backups").json() == {"backups": []}
        assert browser.post(f"/api/deployments/{identity}/check", headers=headers).json()["apps"][0]["state"] == "running"
        assert sum(name == "managed-apply" for name, _ in remote.calls) == 3


def test_partial_install_port_review_uses_fixed_owner_csrf_and_single_use_protocol(tmp_path, monkeypatch):
    app, remote = dashboard(tmp_path, monkeypatch)
    with TestClient(app) as browser:
        headers = authorize(browser, app)
        path = "/api/deployments/" + "a" * 32 + "/ports/review"
        assert browser.post(path, json={}).status_code == 403
        assert browser.post(path, json={"ports": {"plex": 1234}}, headers=headers).status_code == 422
        assert browser.post("/api/deployments/unknown/ports/review", json={}, headers=headers).status_code == 422
        response = browser.post(path, json={}, headers=headers)
        assert response.status_code == 200 and "host-secret-reference" not in response.text
        assert remote.calls[-1] == ("managed-review", {"id": "a" * 32, "action": "install-ports"})
        token = response.json()["review_token"]
        assert browser.post("/api/deployments/actions/apply", json={"review_token": token}, headers=headers).status_code == 202
        assert browser.post("/api/deployments/actions/apply", json={"review_token": token}, headers=headers).status_code == 409


@pytest.mark.parametrize("app_id", APP_IDS)
def test_updates_require_session_review_and_reject_browser_supplied_images(tmp_path, monkeypatch, app_id):
    app, remote = dashboard(tmp_path, monkeypatch)
    with TestClient(app) as browser:
        headers = authorize(browser, app)
        path = "/api/deployments/" + "a" * 32 + "/update-review"
        for payload in ({"action": "update", "app": app_id},
                        {"action": "rollback", "app": app_id, "update": "b" * 32},
                        {"action": "update-recover", "app": app_id, "update": "b" * 32}):
            assert browser.post(path, json=payload).status_code == 403
            assert browser.post(path, json=payload | {"image": "untrusted:latest"}, headers=headers).status_code == 422
            response = browser.post(path, json=payload, headers=headers)
            assert response.status_code == 200 and "host-secret-reference" not in response.text
            token = response.json()["review_token"]
            assert browser.post("/api/deployments/actions/apply", json={"review_token": token}, headers=headers).status_code == 202
            assert browser.post("/api/deployments/actions/apply", json={"review_token": token}, headers=headers).status_code == 409


def test_backup_policy_is_reviewed_and_key_requires_owner_password(tmp_path, monkeypatch):
    app, remote = dashboard(tmp_path, monkeypatch)
    original = remote.request
    key_calls = []
    async def backup_remote(operation, payload=None):
        if operation == "backup-policy":
            return {"policy": {"enabled": False}, "destinations": []}
        if operation == "backup-policy-review":
            return {"review_reference": "host-secret-reference-value-1234567890", "action": "backup-policy", "apps": ["Plex"], "notice": "Nightly backup"}
        if operation == "backup-key":
            key_calls.append(True)
            return {"key": "synthetic recovery key"}
        if operation in {"backup-folder", "backup-plan-run"}:
            return {"id": "a" * 32}
        return await original(operation, payload)
    remote.request = backup_remote
    with TestClient(app) as browser:
        assert browser.get("/api/backup-policy").status_code == 401
        headers = authorize(browser, app)
        assert browser.get("/api/backup-policy").json()["policy"]["enabled"] is False
        value = {"enabled": True, "time": "03:00", "keep": 7, "deployments": ["a" * 32]}
        assert browser.post("/api/backup-policy-review", json=value).status_code == 403
        assert browser.post("/api/backup-policy-review", json=value | {"path": "C:/arbitrary"}, headers=headers).status_code == 422
        reviewed = browser.post("/api/backup-policy-review", json=value, headers=headers)
        assert reviewed.status_code == 200 and "host-secret-reference" not in reviewed.text
        token = reviewed.json()["review_token"]
        assert browser.post("/api/deployments/actions/apply", json={"review_token": token}, headers=headers).status_code == 202
        assert browser.post("/api/deployments/actions/apply", json={"review_token": token}, headers=headers).status_code == 409
        assert browser.post("/api/backup-folder").status_code == 403
        assert browser.post("/api/backup-plan-run").status_code == 403
        assert browser.post("/api/backup-key", json={"password": "incorrect password"}, headers=headers).status_code == 403
        assert not key_calls
        exported = browser.post("/api/backup-key", json={"password": "synthetic test password"}, headers=headers)
        assert exported.status_code == 200 and exported.headers["cache-control"] == "no-store"
        assert len(key_calls) == 1


def choose_kuma(browser, headers, port=28009):
    saved = browser.get("/api/onboarding").json()
    draft = {"step": 2, "port_mode": "custom", "apps": ["kuma"],
             "choices": {"kuma": {"mode": "install", "port": port, "url": ""}}, "data_root": ""}
    response = browser.put("/api/onboarding", json={"revision": saved["revision"], "draft": draft},
                           headers=headers)
    assert response.status_code == 200, response.text


def test_review_install_uses_scoped_controller_and_binds_draft(tmp_path, monkeypatch):
    app, remote = dashboard(tmp_path, monkeypatch)
    with TestClient(app) as browser:
        headers = authorize(browser, app)
        choose_kuma(browser, headers)
        status = browser.get("/api/deployments").json()
        assert status["available"] is True and status["controller"] == "connected"
        assert browser.post("/api/onboarding/check-ports", headers=headers).json()["ports"][0]["port"] == 28009
        assert browser.post("/api/onboarding/suggest-ports", headers=headers).json()["suggestions"][0]["port"] == 28009
        first = browser.post("/api/deployments/review", headers=headers)
        assert first.status_code == 200
        assert "host-secret-reference" not in first.text
        assert ("review", {"apps": ["kuma"], "ports": {"kuma": 28009}}) in remote.calls
        choose_kuma(browser, headers, port=28008)
        assert browser.post("/api/deployments/install", json={"review_token": first.json()["review_token"]},
                            headers=headers).status_code == 409
        assert not any(name == "install" for name, _ in remote.calls)
        second = browser.post("/api/deployments/review", headers=headers).json()
        accepted = browser.post("/api/deployments/install", json={"review_token": second["review_token"]},
                                headers=headers)
        assert accepted.status_code == 202 and accepted.json()["id"] == "a" * 32
        assert browser.post("/api/deployments/install", json={"review_token": second["review_token"]},
                            headers=headers).status_code == 409
        remote.operations[0].update(state="needs-setup", links=[{"app": "kuma", "url": "http://localhost:28009"}])
        assert browser.get("/api/deployments").json()["operations"][0]["links"][0]["url"] == "http://localhost:28009"


def test_disconnected_controller_keeps_install_unavailable(tmp_path, monkeypatch):
    app, remote = dashboard(tmp_path, monkeypatch)
    with TestClient(app) as browser:
        headers = authorize(browser, app)
        choose_kuma(browser, headers)
        remote.connected = False
        status = browser.get("/api/deployments").json()
        assert status["available"] is False and status["controller"] == "unavailable"
        response = browser.post("/api/deployments/review", headers=headers)
        assert response.status_code == 503
        assert "host-secret" not in response.text


def test_last_signed_progress_survives_disconnection_and_dashboard_restart(tmp_path, monkeypatch):
    app, remote = dashboard(tmp_path, monkeypatch)
    remote.operations = [{"id": "a" * 32, "state": "running", "apps": ["kuma"], "message": "Downloading"}]
    with TestClient(app) as browser:
        authorize(browser, app)
        fresh = browser.get("/api/deployments").json()
        assert fresh["controller"] == "connected" and fresh["status_stale"] is False
        checked = fresh["last_checked"]
        remote.connected = False
        stale = browser.get("/api/deployments").json()
        assert stale["controller"] == "unavailable" and stale["available"] is False
        assert stale["status_stale"] is True and stale["last_checked"] == checked
        assert stale["operations"] == remote.operations
    restarted = create_app(tmp_path / "dashboard", origin="http://testserver", background=False)
    with TestClient(restarted) as browser:
        headers = {"Origin": "http://testserver"}
        assert browser.post("/api/login", json={"password": "synthetic test password"},
                            headers=headers).status_code == 200
        assert browser.get("/api/deployments").json()["operations"] == remote.operations
        remote.connected = True
        remote.operations[0].update(state="needs-setup", message="Started")
        current = browser.get("/api/deployments").json()
        assert current["status_stale"] is False and current["operations"] == remote.operations


def test_signed_busy_response_keeps_last_progress_without_reporting_connection_loss(tmp_path, monkeypatch):
    app, remote = dashboard(tmp_path, monkeypatch)
    remote.operations = [{"id": "a" * 32, "state": "running", "apps": ["kuma"], "message": "Downloading"}]
    with TestClient(app) as browser:
        authorize(browser, app)
        browser.get("/api/deployments")
        original = remote.request
        async def busy(operation, payload=None):
            if operation == "status":
                raise ControllerConnectionError("Controller is busy; check progress before trying again", 429)
            return await original(operation, payload)
        remote.request = busy
        status = browser.get("/api/deployments").json()
        assert status["controller"] == "busy" and status["available"] is False
        assert status["status_stale"] is True and status["operations"] == remote.operations


def test_lost_install_response_reconciles_from_controller_status(tmp_path, monkeypatch):
    app, remote = dashboard(tmp_path, monkeypatch)
    with TestClient(app) as browser:
        headers = authorize(browser, app)
        choose_kuma(browser, headers)
        review = browser.post("/api/deployments/review", headers=headers).json()
        original = remote.request
        async def lost_response(operation, payload=None):
            result = await original(operation, payload)
            if operation == "install":
                raise ControllerConnectionError("Installation connection unavailable. Check progress before trying again")
            return result
        remote.request = lost_response
        response = browser.post("/api/deployments/install", json={"review_token": review["review_token"]},
                                headers=headers)
        assert response.status_code == 503
        assert browser.get("/api/deployments").json()["operations"][0]["state"] == "queued"
        assert browser.post("/api/deployments/install", json={"review_token": review["review_token"]},
                            headers=headers).status_code == 409


def test_controller_review_conflict_is_recoverable(tmp_path, monkeypatch):
    app, remote = dashboard(tmp_path, monkeypatch)
    with TestClient(app) as browser:
        headers = authorize(browser, app)
        choose_kuma(browser, headers)
        async def conflict(operation, payload=None):
            if operation == "review":
                raise ControllerConnectionError("An installation needs attention. Resume it before reviewing another.", 409)
            return await Remote.request(remote, operation, payload)
        remote.request = conflict
        response = browser.post("/api/deployments/review", headers=headers)
        assert response.status_code == 409
        assert "Resume" in response.json()["detail"]


def test_dashboard_browses_host_folder_and_reviews_approved_reference(tmp_path, monkeypatch):
    app, remote = dashboard(tmp_path, monkeypatch)
    remote.media_path = str(tmp_path / "approved-media")
    with TestClient(app) as browser:
        headers = authorize(browser, app)
        assert browser.get("/api/deployments").json()["folder_browser"] is True
        assert browser.get("/api/onboarding/folders").json()["roots"][0]["name"] == "Approved media"
        selected = browser.get("/api/onboarding/folders?root=0").json()
        assert selected["host_path"] == remote.media_path
        saved = browser.get("/api/onboarding").json()
        draft = {"step": 2, "apps": ["plex"], "data_root": remote.media_path,
                 "folder_root": 0, "folder_relative": "", "choices": {"plex": {"port": 28001}}}
        assert browser.put("/api/onboarding", json={"revision": saved["revision"], "draft": draft},
                           headers=headers).status_code == 200
        assert browser.post("/api/onboarding/prepare-folders", json={"revision": 2},
                            headers=headers).status_code == 409
        assert browser.post("/api/deployments/review", headers=headers).status_code == 200
        assert ("review", {"apps": ["plex"], "ports": {"plex": 28001},
                           "folder": 0, "relative": ""}) in remote.calls


def test_dashboard_rejects_folder_changed_on_host(tmp_path, monkeypatch):
    app, remote = dashboard(tmp_path, monkeypatch)
    remote.media_path = str(tmp_path / "approved-media")
    with TestClient(app) as browser:
        headers = authorize(browser, app)
        saved = browser.get("/api/onboarding").json()
        draft = {"step": 2, "apps": ["plex"], "data_root": str(tmp_path / "different-media"),
                 "folder_root": 0, "folder_relative": "", "choices": {"plex": {"port": 28001}}}
        assert browser.put("/api/onboarding", json={"revision": saved["revision"], "draft": draft},
                           headers=headers).status_code == 200
        response = browser.post("/api/deployments/review", headers=headers)
        assert response.status_code == 422
        assert "changed" in response.json()["detail"]
        assert not any(name == "install" for name, _ in remote.calls)



def test_account_setup_review_is_private_owner_bound_and_cannot_be_applied_twice(tmp_path,monkeypatch):
    import json
    app,remote=dashboard(tmp_path,monkeypatch)
    identity='a'*32
    with app.state.store.db() as db:
        db.execute('INSERT INTO controller_connections(id,revision,ports,activated) VALUES(?,?,?,?)',
                   (identity,app.state.store.config()[0],json.dumps({'plex':54800,'seerr':54801}),1))
    original=remote.request
    async def request(operation,payload=None):
        if operation=='accounts-review':
            return {'review_reference':'PRIVATE-HOST-CAPABILITY','apps':['plex','seerr'],
                    'libraries':[{'name':'Movies','state':'create'},{'name':'TV Shows','state':'create'}],
                    'notice':'Synthetic reviewed setup'}
        if operation=='accounts-apply':
            assert payload=={'review_reference':'PRIVATE-HOST-CAPABILITY'}
            remote.calls.append((operation,payload))
            return {'state':'connected','message':'Ready'}
        return await original(operation,payload)
    remote.request=request
    with TestClient(app) as browser:
        headers=authorize(browser,app)
        path=f'/api/deployments/{identity}/accounts/review'
        assert browser.post(path,json={}).status_code==403
        review=browser.post(path,json={},headers=headers)
        assert review.status_code==200 and 'PRIVATE-HOST' not in review.text
        token=review.json()['review_token']
        with TestClient(app) as other:
            other_login=other.post('/api/login',json={'password':'synthetic test password'},headers={'Origin':'http://testserver'})
            other_headers={'Origin':'http://testserver','X-CSRF-Token':other_login.json()['csrf']}
            assert other.post('/api/accounts/apply',json={'review_token':token},headers=other_headers).status_code==409
        saved=browser.post('/api/accounts/apply',json={'review_token':token},headers=headers)
        assert saved.status_code==200 and saved.json()['state']=='connected'
        assert browser.post('/api/accounts/apply',json={'review_token':token},headers=headers).status_code==409
        assert sum(operation=='accounts-apply' for operation,_ in remote.calls)==1



@pytest.mark.parametrize('foreign',[False,True])
def test_account_automation_wires_only_unchanged_receipt_bound_endpoints(tmp_path,monkeypatch,foreign):
    import json

    from stackarr import wiring
    app,remote=dashboard(tmp_path,monkeypatch)
    ports={'plex':54800,'seerr':54801}
    credentials={key:{'api_key':'synthetic-key-'+key} for key in ports}
    revision,config=app.state.store.config()
    for key,port in ports.items():
        config.integrations[key].enabled=True
        config.integrations[key].url=config.integrations[key].peer_url=f'http://host.docker.internal:{port}'
    if foreign:
        config.integrations['plex'].url='http://main-installation.invalid'
    app.state.store.save(config,revision,credentials)
    identity='a'*32
    with app.state.store.db() as db:
        db.execute('INSERT INTO controller_connections(id,revision,ports,activated) VALUES(?,?,?,1)',
                   (identity,app.state.store.config()[0],json.dumps(ports)))
    async def request(operation,payload=None):
        if operation=='accounts-review':
            return {'review_reference':'PRIVATE-HOST-CAPABILITY','apps':list(ports),'libraries':[],'notice':'Synthetic'}
        if operation=='accounts-apply':
            return {'state':'connected','message':'Ready'}
        if operation in ('plex-connection','seerr-connection'):
            key=operation.split('-')[0]
            return {'id':identity,'port':ports[key],'credential':credentials[key]}
        raise AssertionError('Unexpected private operation '+operation)
    remote.request=request
    applied=[]
    async def build(store,transport):
        checks=[{'source':'plex','target':'seerr','state':'proposed'},
                {'source':'radarr','target':'seerr','state':'proposed'},
                {'source':'prowlarr','target':'sonarr','state':'proposed'}]
        return {'revision':store.config()[0],'checks':checks,'notices':[],
                'changes':[{'source':row['source'],'target':row['target'],'check':row} for row in checks]}
    async def apply(store,plan,transport):
        applied.append([(row['check']['source'],row['check']['target']) for row in plan['changes']])
        return [{'target':row['target'],'state':'created'} for row in plan['changes']]
    monkeypatch.setattr(wiring,'build_plan',build)
    monkeypatch.setattr(wiring,'apply_plan',apply)
    with TestClient(app) as browser:
        headers=authorize(browser,app)
        review=browser.post(f'/api/deployments/{identity}/accounts/review',json={},headers=headers)
        assert review.status_code==200
        result=browser.post('/api/accounts/apply',json={'review_token':review.json()['review_token']},headers=headers)
        assert result.status_code==200
        assert applied==([[],[]] if foreign else [[('plex','seerr')],[('plex','seerr')]])
        assert app.state.store.config()[1].integrations['plex'].url==('http://main-installation.invalid' if foreign else 'http://host.docker.internal:54800')
