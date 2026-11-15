from stackarr.server import create_app


def test_draft_requires_auth_and_csrf(client, auth):
    assert client.put("/api/onboarding", json={"revision": 1, "draft": {}}).status_code == 403
    client.post("/api/logout", headers=auth)
    assert client.get("/api/onboarding").status_code == 401


def test_resume_without_activating_apps(client, app, auth):
    original = app.state.store.config()
    body = {"revision": 1, "draft": {"apps": ["plex"], "step": 1, "data_root": "/data"}}
    assert client.put("/api/onboarding", json=body, headers=auth).status_code == 200
    assert client.put("/api/onboarding", json=body, headers=auth).status_code == 409
    from stackarr import onboarding

    restarted = create_app(app.state.store.root, origin="http://testserver", background=False)
    assert onboarding.read(restarted.state.store)["draft"] == {**body["draft"], "choices": {},
        "port_mode": "automatic", "folder_root": None, "folder_relative": ""}
    assert app.state.store.config() == original
    plan = client.get("/api/onboarding/plan").json()
    assert set(plan["plan"]["compose"]["services"]) == {"plex"}
    assert plan["installation_started"] is False
    checks = client.get("/api/onboarding/readiness").json()
    assert next(c for c in checks if c["name"] == "Installation computer")["state"] == "not-checked"


def test_draft_rejects_secrets_unknown_apps_and_missing_storage(client, auth):
    for draft in ({"apps": ["unknown"]}, {"apps": ["plex", "plex"]}, {"password": "synthetic"}):
        assert client.put("/api/onboarding", json={"revision": 1, "draft": draft}, headers=auth).status_code == 422
    assert client.put("/api/onboarding", json={"revision": 1, "draft": {"apps": ["plex"]}}, headers=auth).status_code == 200
    assert client.get("/api/onboarding/plan").status_code == 422


def test_monitor_only_plan_does_not_require_media_folder(client, auth):
    client.put("/api/onboarding", json={"revision": 1, "draft": {"apps": ["kuma"]}}, headers=auth)
    result = client.get("/api/onboarding/plan")
    assert result.status_code == 200
    assert set(result.json()["plan"]["compose"]["services"]) == {"kuma"}


def test_mixed_draft_only_installs_selected_new_apps(client, app, auth):
    original = app.state.store.config()
    draft = {"apps": ["plex", "seerr"], "choices": {
        "plex": {"mode": "connect", "url": "http://plex.example:32400"},
        "seerr": {"mode": "install", "port": 5056}}}
    assert client.put("/api/onboarding", json={"revision": 1, "draft": draft}, headers=auth).status_code == 200
    result = client.get("/api/onboarding/plan").json()
    services = result["plan"]["compose"]["services"]
    assert set(services) == {"seerr"}
    assert services["seerr"]["ports"][0]["published"] == "5056"
    assert not client.get("/api/onboarding/storage").json()["required"]
    assert result["connections"] == [{"app": "plex", "url": "http://plex.example:32400",
                                      "state": "authentication-and-identity-not-verified", "managed": False}]
    assert app.state.store.config() == original


def test_connect_only_draft_has_no_install_or_storage(client, auth):
    draft = {"apps": ["plex"], "choices": {"plex": {"mode": "connect", "url": "http://plex.example"}}}
    client.put("/api/onboarding", json={"revision": 1, "draft": draft}, headers=auth)
    result = client.get("/api/onboarding/plan")
    assert result.status_code == 200
    assert result.json()["plan"]["compose"]["services"] == {}
    assert result.json()["storage"]["mounts"] == []


def test_incomplete_connection_can_resume_but_cannot_be_planned(client, auth):
    draft = {"apps": ["plex"], "choices": {"plex": {"mode": "connect"}}}
    assert client.put("/api/onboarding", json={"revision": 1, "draft": draft}, headers=auth).status_code == 200
    assert client.get("/api/onboarding/plan").status_code == 422
    checks = client.get("/api/onboarding/readiness").json()
    assert next(c for c in checks if c["name"] == "Existing app addresses")["state"] == "needs-choice"


def test_connection_drafts_reject_secrets_and_unselected_choices(client, auth):
    for choices in ({"plex": {"mode": "connect", "url": "http://user:secret@example"}},
                    {"plex": {"mode": "connect", "url": "http://example?apikey=secret"}},
                    {"plex": {"password": "secret"}}, {"seerr": {"mode": "install"}}):
        body = {"revision": 1, "draft": {"apps": ["plex"], "choices": choices}}
        assert client.put("/api/onboarding", json=body, headers=auth).status_code == 422


def test_reviewed_connection_only_activates_existing_choice(client, app, auth):
    draft = {"apps": ["plex", "seerr"], "choices": {
        "plex": {"mode": "connect", "url": "http://plex.example:32400"}, "seerr": {"mode": "install"}}}
    client.put("/api/onboarding", json={"revision": 1, "draft": draft}, headers=auth)
    assert client.post("/api/onboarding/connections/review").status_code == 403
    review = client.post("/api/onboarding/connections/review", headers=auth).json()
    assert not app.state.store.config()[1].integrations["plex"].enabled
    token = {"review_token": review["review_token"]}
    assert client.post("/api/onboarding/connections/apply", json=token, headers=auth).json()["saved"] == 1
    config = app.state.store.config()[1]
    assert config.integrations["plex"].url == "http://plex.example:32400"
    assert config.integrations["plex"].enabled
    assert not config.integrations["seerr"].enabled
    assert client.post("/api/onboarding/connections/apply", json=token, headers=auth).status_code == 409


def test_connection_review_preserves_existing_credentials_and_settings(client, app, auth):
    revision, config = app.state.store.config()
    config.integrations["plex"].url = "http://original.example"
    app.state.store.save(config, revision, {"plex": {"api_key": "synthetic-existing"}})
    draft = {"apps": ["plex"], "choices": {"plex": {"mode": "connect", "url": "http://different.example"}}}
    client.put("/api/onboarding", json={"revision": 1, "draft": draft}, headers=auth)
    review = client.post("/api/onboarding/connections/review", headers=auth).json()
    assert review["changes"] == [] and review["notices"]
    client.post("/api/onboarding/connections/apply", json={"review_token": review["review_token"]}, headers=auth)
    assert app.state.store.config()[1].integrations["plex"].url == "http://original.example"
    assert app.state.store.secret("plex")["api_key"] == "synthetic-existing"


def test_connection_review_rejects_changed_draft(client, auth):
    draft = {"apps": ["plex"], "choices": {"plex": {"mode": "connect", "url": "http://plex.example"}}}
    client.put("/api/onboarding", json={"revision": 1, "draft": draft}, headers=auth)
    review = client.post("/api/onboarding/connections/review", headers=auth).json()
    client.put("/api/onboarding", json={"revision": 2, "draft": {}}, headers=auth)
    assert client.post("/api/onboarding/connections/apply", json={"review_token": review["review_token"]}, headers=auth).status_code == 409


def test_discovered_browser_address_survives_review_without_installing(client, app, auth):
    draft = {"apps": ["sonarr"], "choices": {"sonarr": {"mode": "connect",
        "url": "http://host.docker.internal:18989", "browser_url": "http://127.0.0.1:18989"}}}
    assert client.put('/api/onboarding', json={'revision':1, 'draft':draft}, headers=auth).status_code == 200
    review = client.post('/api/onboarding/connections/review', headers=auth).json()
    assert review['changes'][0]['browser_address'] == 'http://127.0.0.1:18989'
    assert client.post('/api/onboarding/connections/apply', json={'review_token':review['review_token']}, headers=auth).status_code == 200
    saved = app.state.store.config()[1].integrations['sonarr']
    assert saved.url == 'http://host.docker.internal:18989' and saved.browser_url == 'http://127.0.0.1:18989'
    assert saved.mode == 'connect' and not app.state.store.secret('sonarr')
    plan = client.get('/api/onboarding/plan').json()
    assert plan['plan']['compose']['services'] == {}
    assert plan['config']['integrations']['sonarr']['browser_url'] == 'http://127.0.0.1:18989'


def test_browser_address_rejects_credentials(client, auth):
    response = client.put('/api/onboarding', json={'revision':1, 'draft':{'apps':['plex'],
        'choices':{'plex':{'mode':'connect','browser_url':'http://user:private@localhost:32400'}}}}, headers=auth)
    assert response.status_code == 422 and 'private' not in response.text
