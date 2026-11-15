import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi import Path as ApiPath
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import Field

from . import __version__, native_import, onboarding, setup_handoff
from . import setup_readiness as journey_readiness
from .adapters import capabilities
from .backup_policy import BackupPolicyIntent
from .config import APP_IDS, CATALOG, Config, Model, validate_url
from .controller_transport import ControllerConnectionError, StackarrUpdateIntent
from .home import Home, HomeError, TitleRequest
from .integrations import Collector, IntegrationError
from .jobs import Jobs
from .lan import LanAccess, browser_routes, operation_links
from .native_import import NativeIntent
from .quality_rules import App as QualityApp
from .quality_rules import ReviewIntent as QualityReview
from .store import Conflict, Store


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


class Login(Model):
    password: str = Field(min_length=12, max_length=256)
    setup_token: str = ""


class SetupHandoff(Model):
    ticket: str = Field(min_length=20, max_length=128)


class InstallPortReview(Model):
    pass


class Credential(Model):
    api_key: str = Field(default="", max_length=1024)
    username: str = Field(default="", max_length=256)
    password: str = Field(default="", max_length=1024)


class Save(Model):
    revision: int
    config: Config
    credentials: dict[str, Credential | None] = Field(default_factory=dict)


class ImportDraft(Model):
    config: Config


class AppAction(Model):
    action: Literal["start", "stop", "restart", "repair", "remove", "repair-recover"]
    operation: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class UpdateAction(Model):
    action: Literal["update", "rollback", "update-recover"]
    app: Literal["plex", "sonarr", "radarr", "prowlarr", "qbittorrent", "seerr", "tautulli", "kuma", "cleanuparr"]
    update: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class BackupAction(Model):
    action: Literal["backup", "restore"]
    backup: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class CompanionSetup(Model):
    pass


class ApplyReview(Model):
    review_token: str = Field(min_length=20, max_length=128)


class FolderPreparation(Model):
    revision: int = Field(ge=1)


def create_app(root=None, origin=None, transport=None, background=True, host_checks=False, pairing=None, host_install=False, folder_picker=None, media_roots=None, storage_probe=None):
    from .folder_browser import FolderBrowser

    media_browser = FolderBrowser(media_roots if media_roots is not None else json.loads(os.environ.get("STACKARR_MEDIA_ROOTS", "[]")))
    store = Store(Path(root or os.environ.get("STACKARR_DATA", ".runtime")))
    onboarding.initialize(store)
    setup_handoff.initialize(store)
    origin = validate_url(
        origin or os.environ.get("STACKARR_ORIGIN", "http://localhost:8787"), origin_only=True
    )
    if not origin:
        raise ValueError("STACKARR_ORIGIN is required")
    lan = LanAccess(origin, os.environ)
    if folder_picker and (not host_checks or urlsplit(origin).hostname not in ("127.0.0.1", "localhost", "::1")):
        raise ValueError("Native folder selection requires the loopback launcher")
    deployments = None
    controller = None
    shared = os.environ.get("STACKARR_CONTROLLER_SHARED")
    controller_state = "not-enrolled" if shared else None
    if shared and (Path(shared) / "rpc.key").is_file():
        from .controller_enrollment import client

        try:
            controller = client(shared)
        except (OSError, ValueError):
            controller_state = "unavailable"
    if controller:
        with store.db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS controller_status_snapshot (
                id INTEGER PRIMARY KEY CHECK(id=1), checked REAL NOT NULL, operations TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS controller_connections (
                id TEXT PRIMARY KEY, revision INTEGER NOT NULL, ports TEXT NOT NULL,
                activated INTEGER NOT NULL DEFAULT 0)""")
            db.execute("""CREATE TABLE IF NOT EXISTS controller_quality_profiles (
                id TEXT PRIMARY KEY, profiles TEXT NOT NULL)""")
    deployment_reviews = {}
    existing_app_reviews = {}
    native_reviews = {}
    quality_reviews = {}
    native_importer = native_import.NativeImporter(enabled=host_checks, transport=transport)
    app_native_lock = asyncio.Lock()
    lifecycle_reviews = {}
    self_update_reviews = {}
    checking_update = os.environ.get("STACKARR_UPDATE_CHECKING") == "1"
    if host_install:
        if not host_checks or urlsplit(origin).hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("Host installation requires a loopback local launcher")
        from .deployment import Deployments

        deployments = Deployments(store)
    collector = Collector(store, transport)
    home = Home(store, transport)
    jobs = Jobs(store)
    from .import_refresh import ImportRefresh

    import_refresh = ImportRefresh(store, transport)
    setup_path = store.root / "setup-token"
    with store.db() as db:
        configured = db.execute("SELECT 1 FROM account").fetchone() is not None
    if not configured and not setup_path.exists():
        setup_path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        os.chmod(setup_path, 0o600)

    async def worker():
        while True:
            try:
                await collector.refresh()
            except Exception:
                store.audit("collector.failed")
            await asyncio.sleep(store.config()[1].dashboard.refresh_seconds)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(worker()) if background and not checking_update else None
        job_task = asyncio.create_task(jobs.work({"refresh": lambda: collector.refresh(maintenance=False)})) if not checking_update else None
        deployment_task = asyncio.create_task(deployments.work()) if deployments else None
        import_task = asyncio.create_task(import_refresh.work()) if background and not checking_update else None
        yield
        if import_task:
            import_task.cancel()
            with suppress(asyncio.CancelledError):
                await import_task
        if deployment_task:
            # Finish the bounded host operation rather than abandoning an active subprocess.
            while any(row["state"] == "running" for row in deployments.rows()) or deployments.actions.busy():
                await asyncio.sleep(.25)
            deployment_task.cancel()
            with suppress(asyncio.CancelledError):
                await deployment_task
        if job_task:
            job_task.cancel()
            with suppress(asyncio.CancelledError):
                await job_task
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(
        title="Stackarr",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.store = store
    app.state.collector = collector
    app.state.home = home
    app.state.jobs = jobs
    app.state.deployments = deployments
    app.state.origin = origin
    attempts = []
    wiring_reviews = {}
    web_login_reviews = {}
    indexer_reviews = {}
    account_reviews = {}
    wiring_lock = asyncio.Lock()
    source_check_lock = asyncio.Lock()
    runtime_check_lock = asyncio.Lock()
    discovery_lock = asyncio.Lock()
    password_lock = asyncio.Lock()
    deployment_check_lock = asyncio.Lock()

    async def hash_password(password, salt):
        # Bound concurrent memory-intensive work; never weaken the password hash.
        async with password_lock:
            try:
                return await asyncio.to_thread(password_hash, password, salt)
            except (MemoryError, ValueError):
                raise HTTPException(503, "Password verification is temporarily unavailable. This computer may be low on memory. Close unused applications and try again.", headers={"Retry-After": "5"}) from None

    def account_exists():
        with store.db() as db:
            return db.execute("SELECT 1 FROM account").fetchone() is not None

    def session(request):
        raw = request.cookies.get("stackarr_session", "")
        digest = hashlib.sha256(raw.encode()).hexdigest()
        with store.db() as db:
            row = db.execute(
                "SELECT csrf FROM sessions WHERE token=? AND expires>?", (digest, time.time())
            ).fetchone()
        if not row:
            raise HTTPException(401, "Sign in to continue")
        return row[0], digest

    def controller_intent(require_storage=True):
        snapshot = onboarding.read(store)
        draft = onboarding.SetupDraft.model_validate(snapshot["draft"])
        if require_storage:
            onboarding.plan(draft)
        apps = draft.install_apps()
        if not apps:
            raise ValueError("Choose at least one new app before reviewing installation")
        intent = {"apps": apps, "ports": {
            key: draft.choice(key).port or CATALOG[key]["port"] for key in apps
        }}
        profiles = {key: draft.choice(key).quality_profile for key in apps if draft.choice(key).quality_profile}
        if profiles and require_storage:
            intent["quality_profiles"] = profiles
        if require_storage and set(apps) & {"plex", "sonarr", "radarr", "qbittorrent"}:
            if draft.folder_root is None or not draft.data_root:
                raise ValueError("Choose a shared media folder before installing these apps")
            intent.update(folder=draft.folder_root, relative=draft.folder_relative)
        return snapshot["revision"], intent

    @app.middleware("http")
    async def security(request, call_next):
        current_origin = lan.request_origin(request.headers)
        if not current_origin:
            return JSONResponse({"detail": "Host not allowed. Check STACKARR_ORIGIN."}, status_code=400)
        request.state.browser_origin = current_origin
        remote = bool(lan.origin and current_origin == lan.origin)
        if remote and request.url.path in {"/api/setup", "/api/setup/handoff", "/api/launcher/pair",
                                          "/api/onboarding/choose-folder", "/api/backup-folder",
                                          "/api/stackarr-update-choose"}:
            return JSONResponse({"detail": "Complete this local approval on the installation computer."}, status_code=403)
        if int(request.headers.get("content-length", "0") or 0) > 131072:
            return JSONResponse({"detail": "Request too large"}, status_code=413)
        if checking_update and request.method not in {"GET", "HEAD", "OPTIONS"} and request.url.path not in {"/api/login", "/api/logout", "/api/stackarr-update-review", "/api/stackarr-update-apply"}:
            return JSONResponse({"detail": "Stackarr is checking an update. Saved settings and app changes are paused."}, status_code=503)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.headers.getlist("origin") != [current_origin]:
                return JSONResponse({"detail": "Origin rejected"}, status_code=403)
            if request.url.path not in ("/api/login", "/api/setup", "/api/launcher/pair", "/api/setup/handoff"):
                try:
                    csrf, _ = session(request)
                except HTTPException as exc:
                    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
                if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), csrf):
                    return JSONResponse({"detail": "CSRF token rejected"}, status_code=403)
        route_token = browser_routes.set(lan.links if remote else None)
        try:
            response = await call_next(request)
        finally:
            browser_routes.reset(route_token)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            }
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Never include Pydantic's input values, which could contain a password or token.
        return JSONResponse(
            {"detail": [{"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in exc.errors()]},
            status_code=422,
        )

    @app.exception_handler(Conflict)
    async def conflict_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.get("/healthz")
    def health():
        store.config()
        return {"status": "ok", "version": __version__}

    @app.get("/api/appearance")
    def public_appearance():
        dashboard = store.config()[1].dashboard
        return {"appearance": dashboard.appearance, "accent": dashboard.accent}

    @app.get("/api/appearance/icon.svg")
    def appearance_icon():
        colors = {"blue": "#78b7ff", "red": "#ff7a7a", "yellow": "#ffe477",
                  "green": "#77e3a2", "orange": "#ffb477", "purple": "#c795ff"}
        svg = (
            Path(__file__).parent / "static/favicon.svg").read_text(encoding="utf-8")
        return Response(svg.replace("#78b7ff", colors[store.config()[1].dashboard.accent]), media_type="image/svg+xml")

    @app.get("/api/overview/storage")
    async def overview_storage(request: Request):
        session(request)
        if controller is not None:
            try:
                return await controller.request("overview-storage")
            except ControllerConnectionError:
                pass
        return {"available": False, "message": "Connect the installation computer to check media storage capacity."}

    @app.get("/api/session")
    def current_session(request: Request):
        try:
            csrf, _ = session(request)
            return {"authenticated": True, "csrf": csrf, "setup_required": False}
        except HTTPException:
            return {"authenticated": False, "setup_required": not account_exists(),
                    "local_launcher": pairing is not None,
                    "setup_approved": bool((pairing and pairing.authorized(request.cookies.get("stackarr_pair", "")))
                                           or setup_handoff.authorized(store, request.cookies.get("stackarr_setup", "")))}

    @app.post("/api/launcher/pair")
    def request_local_approval():
        if pairing is None or account_exists():
            raise HTTPException(404, "Local setup approval is unavailable")
        rate_limit()
        try:
            token, code = pairing.request()
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        response = JSONResponse({"code": code, "expires_in": 120})
        response.set_cookie("stackarr_pair", token, httponly=True, samesite="strict", max_age=120,
                            secure=origin.startswith("https:"))
        return response

    def rate_limit():
        now = time.time()
        attempts[:] = [t for t in attempts if now - t < 300]
        if len(attempts) >= 10:
            raise HTTPException(429, "Too many sign-in attempts. Try again in five minutes.")
        attempts.append(now)

    @app.post("/api/setup/handoff")
    def authorize_setup(body: SetupHandoff):
        rate_limit()
        cookie = setup_handoff.exchange(store, body.ticket)
        if not cookie:
            raise HTTPException(403, "This setup invitation expired or was already used. Open Start Stackarr again on the installation computer.")
        response = JSONResponse({"approved": True})
        response.set_cookie("stackarr_setup", cookie, httponly=True, samesite="strict", max_age=setup_handoff.BROWSER_APPROVAL_SECONDS,
                            secure=origin.startswith("https:"))
        return response

    @app.post("/api/setup")
    async def setup(body: Login, request: Request):
        rate_limit()
        if account_exists():
            raise HTTPException(409, "Setup already completed")
        local_approved = pairing and pairing.authorized(request.cookies.get("stackarr_pair", ""))
        token_approved = setup_path.exists() and hmac.compare_digest(
            body.setup_token, setup_path.read_text().strip()
        )
        browser_approved = setup_handoff.authorized(store, request.cookies.get("stackarr_setup", ""))
        if not local_approved and not token_approved and not browser_approved:
            raise HTTPException(403, "Setup approval is missing or expired. Reopen Start Stackarr on this computer, then try again. Your password has not been saved.")
        salt = secrets.token_hex(16)
        hashed = await hash_password(body.password, salt)
        with store.db() as db:
            result = db.execute("INSERT OR IGNORE INTO account VALUES(1,?,?)", (salt, hashed))
            if result.rowcount != 1:
                raise HTTPException(409, "Setup already completed")
            db.execute("DELETE FROM setup_handoffs")
        setup_path.unlink(missing_ok=True)
        if pairing:
            pairing.revoke()
        store.audit("account.created")
        return {"created": True}

    @app.post("/api/login")
    async def login(body: Login, request: Request):
        rate_limit()
        with store.db() as db:
            row = db.execute("SELECT salt,hash FROM account WHERE id=1").fetchone()
        hashed = await hash_password(body.password, row[0] if row else "00" * 16)
        if not row or not hmac.compare_digest(hashed, row[1]):
            store.audit("login.failed")
            raise HTTPException(401, "Password rejected")
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with store.db() as db:
            db.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
            db.execute(
                "INSERT INTO sessions VALUES(?,?,?)",
                (hashlib.sha256(token.encode()).hexdigest(), csrf, time.time() + 43200),
            )
        response = JSONResponse({"csrf": csrf})
        response.set_cookie(
            "stackarr_session",
            token,
            httponly=True,
            samesite="strict",
            secure=request.state.browser_origin.startswith("https:"),
            max_age=43200,
        )
        store.audit("login.succeeded")
        return response

    @app.post("/api/logout")
    def logout(request: Request):
        _, token = session(request)
        with store.db() as db:
            db.execute("DELETE FROM sessions WHERE token=?", (token,))
        response = JSONResponse({"logged_out": True})
        response.delete_cookie("stackarr_session")
        return response

    @app.get("/api/config")
    def get_config(request: Request):
        session(request)
        revision, config = store.config()
        # Webhook URLs can include a secret path; never return the saved URL to browsers.
        data = config.model_dump()
        data["maintenance"]["notification_url"] = ""
        return {
            "revision": revision,
            "config": data,
            "credentials_saved": store.secret_names(),
            "notification_configured": bool(store.secret("notification").get("url")),
            "catalog": CATALOG,
            "capabilities": capabilities(),
            "network": lan.status(request.state.browser_origin),
        }

    @app.put("/api/config")
    async def save_config(body: Save, request: Request):
        session(request)
        if deployments and (any(row["state"] in ("queued", "running") for row in deployments.rows()) or deployments.actions.busy()):
            raise HTTPException(409, "Installation is in progress. Wait for it to finish before changing active settings; your form changes are still here.")
        if wiring_lock.locked():
            raise HTTPException(409, "Connections are being applied. Wait for the result before saving settings.")
        if set(body.credentials) - set(APP_IDS):
            raise HTTPException(422, "Unknown credential integration")
        old = store.config()[1]
        restart = body.config.storage != old.storage or any(
            (
                body.config.integrations[k].mode,
                body.config.integrations[k].port,
                body.config.integrations[k].enabled,
            )
            != (old.integrations[k].mode, old.integrations[k].port, old.integrations[k].enabled)
            and (body.config.integrations[k].mode == "install" or old.integrations[k].mode == "install")
            for k in APP_IDS
        )
        credentials = {k: v.model_dump() if v else None for k, v in body.credentials.items()}
        try:
            revision = store.save(body.config, body.revision, credentials)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {
            "revision": revision,
            "restart_required": restart,
            "message": "Settings saved. Regenerate and apply the Compose plan for installation or storage changes."
            if restart
            else "Settings applied; collection updates on the next refresh.",
        }

    @app.post("/api/config/validate")
    def validate_import(body: ImportDraft, request: Request):
        session(request)
        data = body.config.model_dump()
        data["maintenance"]["notification_url"] = ""
        data["maintenance"]["notifications_enabled"] = False
        return {"config": data, "saved": False,
                "message": "Review the imported settings, then Save settings. Re-enable notifications separately."}

    @app.get("/api/status")
    def status(request: Request):
        session(request)
        return collector.view()

    @app.get('/api/quality-rules/{key}')
    def quality_read(key: QualityApp, request: Request):
        session(request)
        return home.rules.read(key)

    @app.get('/api/quality-presets')
    def quality_presets(request: Request):
        session(request)
        from .quality_presets import catalog
        return catalog()

    from .download_protection import Protection
    from .library_mapping import LibraryMapping
    from .media_setup_routes import register as register_media_setup
    from .storage_topology import StorageQuery, topology

    async def inspect_storage(query):
        if storage_probe is not None:
            return await storage_probe(query)
        if controller:
            try:
                return await controller.request('storage-topology', query)
            except ControllerConnectionError:
                raise ValueError('The host could not verify shared media storage. Update or reconnect the Windows controller, then check the app installation and library folders.') from None
        native = None
        if query['plex_port'] == 32400:
            try:
                native = await native_importer.inspect('plex')
            except ValueError:
                pass
        return await asyncio.to_thread(topology, deployments, StorageQuery.model_validate(query), native)

    mapping = LibraryMapping(store, inspect_storage, transport)
    home.mapping = mapping
    app.state.library_mapping = mapping
    app.state.download_protection = Protection(store, transport)
    register_media_setup(app, session, wiring_lock, home.request_lock, app.state.download_protection, mapping)
    from .cleanup_preset_routes import register as register_cleanup_presets
    register_cleanup_presets(app, session, wiring_lock, home.request_lock, store, transport)

    @app.get('/api/quality-rules/{key}/titles')
    async def quality_titles(key: QualityApp, request: Request, query: str = Query(default='', max_length=160)):
        session(request)
        try:
            return {'titles': await home.rules.titles(key, query.strip())}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    async def quality_preview(body, owner):
        quality_reviews.pop(owner, None)
        try:
            plan = await home.rules.review(body)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        now = time.monotonic()
        for key in list(quality_reviews):
            if quality_reviews[key][1] <= now:
                del quality_reviews[key]
        if len(quality_reviews) >= 100:
            raise HTTPException(429, 'Too many pending reviews. Try again shortly.')
        token = secrets.token_urlsafe(32)
        quality_reviews[owner] = (token, now + 600, plan)
        return {**home.rules.public(plan), 'review_token': token}

    @app.post('/api/quality-rules/review')
    async def quality_review(body: QualityReview, request: Request):
        _, owner = session(request)
        async with wiring_lock:
            return await quality_preview(body, owner)

    @app.post('/api/quality-rules/{key}/restore-review')
    async def quality_restore_review(key: QualityApp, request: Request):
        _, owner = session(request)
        async with wiring_lock:
            return await quality_preview(home.rules.restore_intent(key), owner)

    @app.post('/api/quality-rules/apply')
    async def quality_apply(body: ApplyReview, request: Request):
        _, owner = session(request)
        async with wiring_lock, home.request_lock:
            review = quality_reviews.get(owner)
            if not review or not secrets.compare_digest(review[0], body.review_token) or review[1] <= time.monotonic():
                raise HTTPException(409, 'Review quality rules again before applying.')
            del quality_reviews[owner]
            try:
                return await home.rules.apply(review[2])
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from None

    @app.get('/api/quality-rules/{key}/history/{identity}')
    def quality_history(key: QualityApp, identity: str, request: Request):
        session(request)
        try:
            return home.rules.run_result(identity, home.rules.run(key, identity))
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from None

    @app.post('/api/quality-rules/{key}/history/{identity}/undo')
    async def quality_undo(key: QualityApp, identity: str, request: Request):
        session(request)
        async with wiring_lock, home.request_lock:
            try:
                return await home.rules.undo(key, identity)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from None

    @app.get('/api/home')
    async def media_home(request: Request):
        session(request)
        try:
            return await home.home()
        except HomeError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.get('/api/home/search')
    async def media_search(request: Request, query: str = Query(min_length=1, max_length=160), page: int = Query(default=1, ge=1, le=500)):
        session(request)
        try:
            if not query.strip():
                raise HomeError('Enter a movie or TV show name to search.')
            return await home.catalog(page=page, query=query.strip())
        except HomeError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.get('/api/home/requests')
    async def media_requests(request: Request, page: int = Query(default=1, ge=1, le=500)):
        session(request)
        try:
            return await home.requests(page)
        except HomeError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.get('/api/home/art/{size}/{filename}')
    async def media_art(request: Request, size: str, filename: str):
        session(request)
        if size not in ('w342', 'w1280') or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}\.(jpg|png)', filename):
            raise HTTPException(404, 'Artwork is unavailable')
        try:
            content, mime = await home.call(f'/imageproxy/tmdb/t/p/{size}/{filename}', image=True)
            return Response(content, media_type=mime)
        except HomeError:
            raise HTTPException(404, 'Artwork is unavailable') from None

    @app.get('/api/home/titles/{kind}/{identity}')
    async def media_title(request: Request, kind: Literal['movie', 'tv'], identity: int = ApiPath(ge=1, le=2_147_483_646)):
        session(request)
        try:
            return await home.detail(kind, identity, check_plex=True)
        except HomeError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.post('/api/home/titles/{kind}/{identity}/request')
    async def media_request(request: Request, body: TitleRequest, kind: Literal['movie', 'tv'], identity: int = ApiPath(ge=1, le=2_147_483_646)):
        session(request)
        try:
            return await home.request(kind, identity, body)
        except HomeError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.get("/api/onboarding")
    def setup_draft(request: Request):
        session(request)
        return onboarding.read(store)

    @app.get("/api/deployments")
    async def deployment_status(request: Request):
        session(request)
        result = {"available": deployments is not None, "operations": deployments.rows() if deployments else [],
                  "host_checks": host_checks}
        if controller_state:
            result["controller"] = controller_state
        if controller:
            try:
                remote = await controller.request("status")
                from .controller_connections import refresh_ports

                refresh_ports(store, remote["operations"])
                checked = time.time()
                with store.db() as db:
                    db.execute("INSERT OR REPLACE INTO controller_status_snapshot VALUES(1,?,?)",
                               (checked, json.dumps(remote["operations"])))
                result.update(available=True, operations=remote["operations"], controller="connected",
                              host_checks=True, actions=remote.get("actions", []), folder_browser=remote.get("folder_browser", False),
                              status_stale=False, last_checked=checked)
                result["folder_picker"] = remote.get("folder_picker", False)
                result["companion_login_apps"] = [key for key in remote.get("companion_login_apps", []) if key in {"tautulli", "kuma", "cleanuparr"}]
                with store.db() as db:
                    from .controller_connections import SUPPORTED, connected_apps, progress

                    result["finish_connecting"] = [row[0] for row in db.execute(
                        "SELECT id,ports FROM controller_connections WHERE activated=0") if set(json.loads(row[1])) & SUPPORTED]
                    bindings = list(db.execute('SELECT id,ports FROM controller_connections'))
                result['connection_progress'] = {identity: progress(store, identity) for identity, _ in bindings}
                result['login_setup'] = [identity for identity, ports in bindings
                    if (selected := set(json.loads(ports)) & {'sonarr', 'radarr', 'prowlarr'})
                    and selected <= connected_apps(store, identity)]
                from .web_logins import initialize

                initialize(store)
                with store.db() as db:
                    result["web_login_apps"] = [row[0] for row in db.execute("SELECT app FROM app_logins")]
            except ControllerConnectionError as exc:
                with store.db() as db:
                    cached = db.execute("SELECT checked,operations FROM controller_status_snapshot WHERE id=1").fetchone()
                result.update(controller="busy" if exc.status_code == 429 else "unavailable",
                              status_stale=True)
                if cached:
                    result.update(last_checked=cached[0], operations=json.loads(cached[1]))
        if media_browser.roots and not controller:
            result["folder_browser"] = True
        if deployments:
            result["actions"] = deployments.actions.rows()
            result["host_checks"] = True
        if folder_picker:
            result["folder_picker"] = True
        result["journey"] = journey_readiness.read(store, collector=collector.view(), deployment=result)
        if browser_routes.get() is not None:
            result["operations"] = operation_links(json.loads(json.dumps(result.get("operations", []))))
            result["folder_picker"] = False
        return result

    @app.get("/api/onboarding/journey")
    def setup_journey(request: Request):
        session(request)
        return journey_readiness.read(store, collector=collector.view())

    @app.post("/api/deployments/{identity}/apps/{key}/review")
    async def review_app_action(identity: str, key: str, body: AppAction, request: Request):
        _, owner = session(request)
        if controller:
            return await remote_managed_review(owner, {"id": identity, "app": key, "action": body.action,
                **({"operation": body.operation} if body.operation else {})})
        if not deployments:
            raise HTTPException(409, "Use the local launcher to manage installed apps.")
        if deployment_check_lock.locked():
            raise HTTPException(409, "An installation check is running. Wait for its results.")
        now = time.monotonic()
        for pending in list(lifecycle_reviews):
            if lifecycle_reviews[pending][1] <= now:
                del lifecycle_reviews[pending]
        if len(lifecycle_reviews) >= 100 and owner not in lifecycle_reviews:
            raise HTTPException(429, "Too many pending app reviews. Try again later.")
        async with deployment_check_lock:
            try:
                review = await asyncio.to_thread(deployments.actions.review, identity, key, body.action, body.operation)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from None
            except (OSError, KeyError, IndexError, TypeError):
                raise HTTPException(409, "The installed container could not be verified. Check its status before retrying.") from None
        token = secrets.token_urlsafe(32)
        lifecycle_reviews[owner] = (token, time.monotonic() + 300, review)
        return {**deployments.actions.public(review), "review_token": token, "expires_in": 300}

    @app.post("/api/deployments/actions/apply", status_code=202)
    async def apply_app_action(body: ApplyReview, request: Request):
        _, owner = session(request)
        if not deployments and not controller:
            raise HTTPException(409, "Use the local launcher to manage installed apps.")
        if wiring_lock.locked():
            raise HTTPException(409, "Wait for app connection setup to finish before changing an app's state.")
        review = lifecycle_reviews.pop(owner, None)
        if not review or review[1] <= time.monotonic() or not hmac.compare_digest(review[0], body.review_token):
            raise HTTPException(409, "Review the app action before applying it.")
        if controller:
            try:
                result = await controller.request("managed-apply", {"review_reference": review[2]})
                if result.get("action") == "install-ports":
                    from .controller_connections import refresh_ports

                    refresh_ports(store, [{"id": result["id"], "apps": list(result["ports"]), "ports": result["ports"], "port_recovery": True}])
                return result
            except ControllerConnectionError as exc:
                raise HTTPException(exc.status_code, str(exc)) from None
        if review[2].get("action") == "install-ports":
            from .install_ports import InstallPorts

            return InstallPorts(deployments).approve(review[2])
        return {"id": deployments.actions.enqueue(review[2]), "accepted": True}

    @app.post("/api/deployments/{identity}/ports/review")
    async def installation_port_review(identity: str, body: InstallPortReview, request: Request):
        _, owner = session(request)
        if not re.fullmatch(r"[a-f0-9]{32}", identity):
            raise HTTPException(422, "Choose a saved installation.")
        if controller:
            return await remote_managed_review(owner, {"id": identity, "action": "install-ports"})
        if not deployments:
            raise HTTPException(409, "Use the installation computer to recover app ports.")
        from .install_ports import InstallPorts

        review = await asyncio.to_thread(InstallPorts(deployments).review, identity, {int(os.environ.get("STACKARR_PORT", "8787"))})
        token = secrets.token_urlsafe(32)
        lifecycle_reviews[owner] = (token, time.monotonic() + 300, review)
        return InstallPorts.public(review) | {"review_token": token, "expires_in": 300}

    async def remote_managed_review(owner, payload):
        now = time.monotonic()
        for pending in list(lifecycle_reviews):
            if lifecycle_reviews[pending][1] <= now:
                del lifecycle_reviews[pending]
        if len(lifecycle_reviews) >= 100 and owner not in lifecycle_reviews:
            raise HTTPException(429, "Too many pending reviews.")
        try:
            review = await controller.request("managed-review", payload)
        except ControllerConnectionError as exc:
            raise HTTPException(exc.status_code, str(exc)) from None
        reference = review.pop("review_reference")
        token = secrets.token_urlsafe(32)
        lifecycle_reviews[owner] = (token, now + 300, reference)
        return review | {"review_token": token}

    @app.get("/api/app-backups")
    async def app_backup_list(request: Request):
        session(request)
        if controller:
            try:
                return await controller.request("app-backups")
            except ControllerConnectionError as exc:
                raise HTTPException(exc.status_code, str(exc)) from None
        if deployments:
            from .app_backups import AppBackups

            return {"backups": AppBackups(deployments).rows()}
        return {"backups": []}

    @app.post("/api/deployments/{identity}/companions-review")
    async def companions_review(identity: str, body: CompanionSetup, request: Request):
        _, owner = session(request)
        if not controller:
            raise HTTPException(409, "Use the packaged controller for companion setup.")
        return await remote_managed_review(owner, {"id": identity, "action": "companions"})

    async def backup_controller(operation, payload=None):
        if not controller:
            raise HTTPException(409, "Use the packaged local controller for scheduled and separate-disk backups.")
        try:
            return await controller.request(operation, payload)
        except ControllerConnectionError as exc:
            raise HTTPException(exc.status_code, str(exc)) from None

    @app.get("/api/backup-policy")
    async def backup_policy(request: Request):
        session(request)
        return await backup_controller("backup-policy")

    @app.post("/api/backup-folder")
    async def backup_folder(request: Request):
        session(request)
        return await backup_controller("backup-folder")

    @app.post("/api/backup-policy-review")
    async def backup_policy_review(body: BackupPolicyIntent, request: Request):
        _, owner = session(request)
        now = time.monotonic()
        review = await backup_controller("backup-policy-review", body.model_dump())
        reference = review.pop("review_reference")
        token = secrets.token_urlsafe(32)
        lifecycle_reviews[owner] = (token, now + 300, reference)
        return review | {"review_token": token}

    @app.post("/api/backup-plan-run")
    async def backup_plan_run(request: Request):
        session(request)
        return await backup_controller("backup-plan-run")

    @app.post("/api/host-backup-review")
    async def host_backup_review(request: Request):
        _, owner = session(request)
        review = await backup_controller("host-backup-review")
        reference = review.pop("review_reference")
        token = secrets.token_urlsafe(32)
        lifecycle_reviews[owner] = (token, time.monotonic() + 300, reference)
        return review | {"review_token": token}

    @app.get("/api/stackarr-updates")
    async def stackarr_updates(request: Request):
        session(request)
        return await backup_controller("stackarr-updates")

    @app.post("/api/stackarr-package")
    async def stackarr_package(body: CompanionSetup, request: Request):
        session(request)
        return await backup_controller("stackarr-package")

    @app.post("/api/stackarr-update-review")
    async def stackarr_update_review(body: StackarrUpdateIntent, request: Request):
        _, owner = session(request)
        review = await backup_controller("stackarr-update-review", body.model_dump())
        reference = review.pop("review_reference")
        token = secrets.token_urlsafe(32)
        self_update_reviews[owner] = (token, time.monotonic() + 300, reference)
        return review | {"review_token": token}

    @app.post("/api/stackarr-update-apply", status_code=202)
    async def stackarr_update_apply(body: ApplyReview, request: Request):
        _, owner = session(request)
        review = self_update_reviews.pop(owner, None)
        if not review or review[1] <= time.monotonic() or not hmac.compare_digest(review[0], body.review_token):
            raise HTTPException(409, "Review the Stackarr update again before approval.")
        return await backup_controller("stackarr-update-apply", {"review_reference": review[2]})

    @app.post("/api/backup-key")
    async def backup_key(body: Login, request: Request):
        session(request)
        await owner_password(body, "backup-recovery")
        value = await backup_controller("backup-key")
        store.audit("app-backup.recovery-key-exported")
        return JSONResponse(value, headers={"Cache-Control": "no-store"})

    @app.get("/api/updates")
    async def update_list(request: Request):
        session(request)
        if controller:
            try:
                return await controller.request("updates")
            except ControllerConnectionError as exc:
                raise HTTPException(exc.status_code, str(exc)) from None
        if deployments:
            from .updates import Updates

            return Updates(deployments).listing()
        return {"apps": [], "history": []}

    @app.post("/api/deployments/{identity}/update-review")
    async def update_review(identity: str, body: UpdateAction, request: Request):
        _, owner = session(request)
        if (body.action != "update") != bool(body.update):
            raise HTTPException(422, "Choose a saved update for rollback or recovery.")
        if controller:
            return await remote_managed_review(owner, {"id": identity, **body.model_dump()})
        if not deployments:
            raise HTTPException(409, "Use the local controller to update owned Docker apps.")
        from .updates import Updates

        service = Updates(deployments)
        try:
            review = await asyncio.to_thread(service.review, identity, body.app, body.action, body.update)
        except (ValueError, Conflict) as exc:
            raise HTTPException(409, str(exc)) from None
        token = secrets.token_urlsafe(32)
        lifecycle_reviews[owner] = (token, time.monotonic() + 300, review)
        return service.public(review) | {"review_token": token, "expires_in": 300}

    @app.post("/api/deployments/{identity}/backup-review")
    async def app_backup_review(identity: str, body: BackupAction, request: Request):
        _, owner = session(request)
        if (body.action == "restore") != bool(body.backup):
            raise HTTPException(422, "Choose a saved Docker backup to restore.")
        if controller:
            return await remote_managed_review(owner, {"id": identity, **body.model_dump()})
        if not deployments:
            raise HTTPException(409, "Use the local controller for Docker app backups.")
        from .app_backups import AppBackups

        service = AppBackups(deployments)
        try:
            review = await asyncio.to_thread(service.review, identity, body.backup)
        except ValueError:
            raise HTTPException(409, "Could not verify this backup or installation. Check its status.") from None
        token = secrets.token_urlsafe(32)
        lifecycle_reviews[owner] = (token, time.monotonic() + 300, review)
        return service.public(review) | {"review_token": token, "expires_in": 300}

    @app.post("/api/deployments/{identity}/accounts/review")
    async def review_accounts(identity: str, request: Request):
        _, owner = session(request)
        from .account_setup import Accounts, AccountSetupError
        try:
            if controller:
                from .controller_connections import binding
                dashboard_revision = store.config()[0]
                _, ports, _ = binding(store, identity)
                result = await controller.request("accounts-review", {"id": identity})
                if store.config()[0] != dashboard_revision:
                    raise Conflict("Settings changed while checking Plex. Review account setup again.")
                if set(result.get("apps", [])) != set(ports):
                    raise AccountSetupError("The reviewed installation changed. Check its saved status.")
                plan = {"remote": result.pop("review_reference"), "id": identity, "apps": list(ports), "dashboard_revision": dashboard_revision}
            elif deployments:
                plan = await Accounts(deployments, transport).review(identity)
                result = Accounts.public(plan)
            else:
                raise AccountSetupError("Open Stackarr on the installation computer to finish Plex setup.")
        except ControllerConnectionError as exc:
            raise HTTPException(exc.status_code, str(exc)) from None
        except (ValueError, OSError, TypeError, KeyError, AttributeError) as exc:
            raise HTTPException(409, str(exc) if isinstance(exc, (AccountSetupError, Conflict)) else "This installation could not be checked safely. Review it in Apps.") from None
        token = secrets.token_urlsafe(32)
        now = time.monotonic()
        for key in list(account_reviews):
            if account_reviews[key][1] <= now:
                del account_reviews[key]
        if len(account_reviews) >= 50 and owner not in account_reviews:
            raise HTTPException(429, "Wait before preparing another account review.")
        account_reviews[owner] = (token, now + 300, plan)
        return result | {"review_token": token, "expires_in": 300}

    @app.post("/api/accounts/apply")
    async def apply_accounts(body: ApplyReview, request: Request):
        _, owner = session(request)
        pending = account_reviews.pop(owner, None)
        if not pending or pending[1] <= time.monotonic() or not hmac.compare_digest(pending[0], body.review_token):
            raise HTTPException(409, "Review account setup again before continuing.")
        if wiring_lock.locked():
            raise HTTPException(409, "Setup is already running. Wait for its result.")
        from .account_setup import Accounts, AccountSetupError
        from .finish_setup import finish
        async with wiring_lock:
            try:
                plan = pending[2]
                if controller:
                    if store.config()[0] != plan["dashboard_revision"]:
                        raise Conflict("Settings changed. Check Plex sign-in and review setup again.")
                    result = await controller.request("accounts-apply", {"review_reference": plan["remote"]})
                    if store.config()[0] != plan["dashboard_revision"]:
                        result["message"] = "Plex setup completed, but your app settings changed. Review connection settings to continue; your changes are preserved."
                        return result
                    from .controller_connections import finish_owned
                    result["connections"] = await finish_owned(store, controller, plan["id"], transport)
                elif deployments:
                    result = await Accounts(deployments, transport).apply(plan)
                    result["connections"] = await finish(deployments, plan["id"], transport)
                else:
                    raise AccountSetupError("Reconnect the installation computer before continuing.")
                if result.get("connections", {}).get("apps") and all(row.get("state") in {"connected", "saved"} for row in result["connections"]["apps"]):
                    from .account_setup import wiring_scope
                    from .wiring import WiringError, apply_plan, build_plan
                    if controller:
                        from .controller_connections import binding, candidates
                        _, ports, _ = binding(store, plan["id"])
                        owned = await candidates(controller, plan["id"], ports)
                        scope_revision, allowed = wiring_scope(store, ports, owned)
                    else:
                        from .deployment_check import differences, inspect_container, load_receipt
                        from .docker_names import app_project
                        receipt = await asyncio.to_thread(load_receipt, deployments, plan["id"])
                        ports, targets = {}, {}
                        for key in receipt["apps"]:
                            service = receipt["compose"]["services"][key]
                            info = await asyncio.to_thread(inspect_container, deployments, plan["id"], receipt, key)
                            if not differences(info, app_project(plan["id"], receipt), key, service):
                                ports[key] = int(service["ports"][0]["published"])
                                targets[key] = int(service["ports"][0]["target"])
                        scope_revision, allowed = wiring_scope(store, ports, local_targets=targets)
                    results = []
                    try:
                        for _ in range(2):
                            if store.config()[0] != scope_revision:
                                raise Conflict("Settings changed during connection setup.")
                            wiring = await build_plan(store, transport)
                            if wiring["revision"] != scope_revision:
                                raise Conflict("Settings changed during connection setup.")
                            wiring["changes"] = [change for change in wiring["changes"] if {change.get("check", {}).get("source"), change.get("check", {}).get("target")} <= allowed]
                            wiring["checks"] = [check for check in wiring["checks"] if {check.get("source"), check.get("target")} <= allowed]
                            applied = await apply_plan(store, wiring, transport)
                            journey_readiness.remember_wiring(store, wiring, applied)
                            results.extend(applied)
                        result["app_connections"] = results
                        if allowed != set(plan["apps"]) or any(row.get("state", "").startswith("failed") for row in results):
                            result["message"] = "Plex and requests are connected. Some download or library connections need attention; review app connections before requesting a title."
                    except (WiringError, ValueError, httpx.HTTPError, Conflict):
                        result["message"] = "Plex and requests are connected. Review app connections to finish the download and library links."
                return result
            except ControllerConnectionError as exc:
                raise HTTPException(exc.status_code, str(exc)) from None
            except (ValueError, OSError, TypeError, KeyError, AttributeError) as exc:
                raise HTTPException(409, str(exc) if isinstance(exc, (AccountSetupError, Conflict)) else "Setup did not finish. Review it again; completed libraries and existing settings stay in place.") from None

    @app.post("/api/deployments/{identity}/finish-connecting")
    async def finish_connections(identity: str, request: Request):
        session(request)
        if not deployments and not controller:
            raise HTTPException(409, "Use the local launcher to finish connecting installed apps.")
        if wiring_lock.locked():
            raise HTTPException(409, "Connection setup is already running. Wait for its results.")
        from .finish_setup import finish

        async with wiring_lock:
            if controller:
                from .controller_connections import finish_owned

                try:
                    return await finish_owned(store, controller, identity, transport)
                except ControllerConnectionError as exc:
                    raise HTTPException(exc.status_code, str(exc)) from None
                except (ValueError, OSError, TypeError, KeyError):
                    raise HTTPException(409, "Could not safely connect this installation. Your saved settings are preserved.") from None
            if deployments.actions.busy() or any(row["state"] in ("queued", "running") for row in deployments.rows()):
                raise HTTPException(409, "Wait for the installation or app action to finish, then try again.")
            try:
                return await finish(deployments, identity, transport)
            except (ValueError, OSError):
                raise HTTPException(409, "Could not check this saved installation. Check it in Apps before continuing.") from None

    @app.post("/api/deployments/{identity}/check")
    async def check_deployment(identity: str, request: Request):
        session(request)
        if controller:
            try:
                return await controller.request("installation-check", {"id": identity})
            except ControllerConnectionError as exc:
                raise HTTPException(exc.status_code, str(exc)) from None
        if not deployments:
            raise HTTPException(409, "Use the local launcher to check installed containers.")
        if deployment_check_lock.locked():
            raise HTTPException(409, "An installation check is already running. Wait for its results.")
        from .deployment_check import check

        async with deployment_check_lock:
            try:
                return await asyncio.to_thread(check, deployments, identity)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from None
            except OSError:
                raise HTTPException(409, "Installation files could not be read. No repair was attempted.") from None

    @app.get("/api/onboarding/folders")
    async def browse_folders(request: Request, root: int | None = None, relative: str = ""):
        session(request)
        if controller:
            try:
                return await controller.request("folders", {"root": root, "relative": relative})
            except ControllerConnectionError as exc:
                raise HTTPException(exc.status_code, str(exc)) from None
        try:
            return media_browser.browse(root, relative)
        except (ValueError, OSError):
            raise HTTPException(422, "This shared folder is unavailable. Choose another folder.") from None

    @app.post("/api/onboarding/prepare-folders")
    def prepare_folders(body: FolderPreparation, request: Request):
        session(request)
        if controller:
            raise HTTPException(409, "Missing media folders are created on the installation computer after you approve installation.")
        snapshot = onboarding.read(store)
        if snapshot["revision"] != body.revision:
            raise HTTPException(409, "Your folder choice changed. Review it again before creating folders.")
        draft = onboarding.SetupDraft.model_validate(snapshot["draft"])
        from .managed_storage import prepare

        try:
            selected = media_browser.selected(draft.data_root)
            prepare(str(selected), draft.install_apps())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        except OSError:
            raise HTTPException(422, "The folders could not be created. Choose a writable shared folder. Existing files were preserved.") from None
        store.audit("setup.folders-created")
        return {"message": "Your media folders are ready. Existing files were left in place."}

    @app.post("/api/onboarding/choose-folder")
    async def choose_folder(request: Request):
        session(request)
        if controller:
            try:
                return await controller.request("media-folder", {})
            except ControllerConnectionError as exc:
                raise HTTPException(exc.status_code, str(exc)) from None
        if not folder_picker:
            raise HTTPException(409, "Folder selection is available in the local launcher. You can enter a full folder address here.")
        try:
            path = await asyncio.to_thread(folder_picker.request)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        return {"path": path, "cancelled": not bool(path)}

    @app.post("/api/onboarding/check-ports")
    async def check_ports(request: Request):
        session(request)
        if controller:
            try:
                _, intent = controller_intent(require_storage=False)
                result = await controller.request("ports", intent)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from None
            except ControllerConnectionError as exc:
                raise HTTPException(exc.status_code, str(exc)) from None
            return {**result, "notice": "Checked on the installation computer. Ports are checked again before installation."}
        if not deployments:
            raise HTTPException(409, "Port checks need a connection to the installation computer. This Docker preview cannot check your computer's ports yet.")
        from .ports import check

        draft = onboarding.SetupDraft.model_validate(onboarding.read(store)["draft"])
        return {"ports": await asyncio.to_thread(check, draft), "notice": "Checked on the installation computer. Ports are checked again before installation."}

    @app.post("/api/onboarding/suggest-ports")
    async def suggest_ports(request: Request):
        session(request)
        if controller:
            try:
                _, intent = controller_intent(require_storage=False)
                result = await controller.request("suggest-ports", intent)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from None
            except ControllerConnectionError as exc:
                raise HTTPException(exc.status_code, str(exc)) from None
            return {**result, "notice": "These ports were available just now. Installation review checks them again. No existing service was changed."}
        if not deployments:
            raise HTTPException(409, "Use the local launcher to check available installation ports.")
        from .ports import suggestions

        draft = onboarding.SetupDraft.model_validate(onboarding.read(store)["draft"])
        try:
            rows = await asyncio.to_thread(suggestions, draft)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return {"suggestions": rows, "notice": "These ports were available just now. The installation review checks them again. Existing services were not contacted or changed."}

    @app.post("/api/deployments/review")
    async def deployment_review(request: Request):
        _, owner = session(request)
        if not deployments and not controller:
            raise HTTPException(409, "Use the local Stackarr launcher to install apps. Container dashboards cannot control the host.")
        try:
            if controller:
                revision, intent = controller_intent()
                config_revision, current = store.config()
                if any(current.integrations[key].enabled or current.integrations[key].url or store.secret(key)
                       for key in intent["apps"]):
                    raise ValueError("A selected app already has saved settings. Review it in Apps; it will not be replaced.")
                remote = await controller.request("review", intent)
                if intent.get("folder") is not None and remote["plan"]["media_folder"] != onboarding.read(store)["draft"]["data_root"]:
                    raise ValueError("The approved media folder changed. Choose it again before installing")
                payload = {"controller_reference": remote["review_reference"], "draft_revision": revision,
                           "config_revision": config_revision, "ports": intent["ports"],
                           "quality_profiles": intent.get("quality_profiles", {})}
                public = remote["plan"]
            else:
                payload = await asyncio.to_thread(deployments.review)
                public = deployments.public(payload)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except ControllerConnectionError as exc:
            raise HTTPException(exc.status_code, str(exc)) from None
        now = time.monotonic()
        for key in list(deployment_reviews):
            if deployment_reviews[key][1] <= now:
                del deployment_reviews[key]
        if len(deployment_reviews) >= 100 and owner not in deployment_reviews:
            raise HTTPException(429, "Too many pending installation reviews. Try again later.")
        token = secrets.token_urlsafe(32)
        deployment_reviews[owner] = (token, now + 300, payload)
        return {**public, "review_token": token, "expires_in": 300}

    async def owner_password(body, key):
        rate_limit()
        with store.db() as db:
            row = db.execute("SELECT salt,hash FROM account WHERE id=1").fetchone()
        hashed = await hash_password(body.password, row[0] if row else "00" * 16)
        if not row or not hmac.compare_digest(hashed, row[1]):
            store.audit("credential.reveal-denied", key)
            raise HTTPException(403, "Enter your Stackarr owner password to view this login.")

    @app.post("/api/deployments/qbittorrent/login")
    async def generated_download_login(body: Login, request: Request):
        session(request)
        if not deployments and not controller:
            raise HTTPException(409, "Use the local launcher to view an installation-generated login.")
        await owner_password(body, "qbittorrent")
        try:
            if controller:
                from .controller_connections import generated_login

                credential = await generated_login(store, controller)
            else:
                credential = deployments.generated_login()
        except ControllerConnectionError as exc:
            raise HTTPException(exc.status_code, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        store.audit("credential.revealed", "qbittorrent")
        return credential

    @app.post("/api/deployments/{identity}/logins/review")
    def review_web_logins(identity: str, request: Request):
        _, owner = session(request)
        if not controller:
            raise HTTPException(409, "Generated Arr logins require the enrolled Docker controller.")
        from .web_logins import public, review

        try:
            plan = review(store, identity)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        token = secrets.token_urlsafe(32)
        web_login_reviews[owner] = (token, time.monotonic() + 300, plan)
        return {**public(plan), "review_token": token}

    @app.post("/api/app-logins/apply")
    async def apply_web_logins(body: ApplyReview, request: Request):
        _, owner = session(request)
        pending = web_login_reviews.pop(owner, None)
        if (not controller or not pending or pending[1] <= time.monotonic()
                or not hmac.compare_digest(pending[0], body.review_token)):
            raise HTTPException(409, "Review app logins again before applying.")
        from .web_logins import apply

        async with wiring_lock:
            try:
                return await apply(store, controller, pending[2])
            except ControllerConnectionError as exc:
                raise HTTPException(exc.status_code, str(exc)) from None
            except Conflict as exc:
                raise HTTPException(409, str(exc)) from None
            except (ValueError, OSError, TypeError, KeyError):
                raise HTTPException(409, "App logins could not be saved safely. Check the installation and review again.") from None

    @app.post("/api/apps/{key}/login")
    async def reveal_web_login(key: str, body: Login, request: Request):
        session(request)
        if not controller or key not in {"sonarr", "radarr", "prowlarr", "tautulli", "kuma", "cleanuparr"}:
            raise HTTPException(409, "Choose an installed app with a generated login.")
        await owner_password(body, key)
        from .web_logins import reveal

        try:
            if key in {"tautulli", "kuma", "cleanuparr"}:
                from .controller_connections import companion_login

                login = await companion_login(store, controller, key)
            else:
                login = await reveal(store, controller, key)
        except ControllerConnectionError as exc:
            raise HTTPException(exc.status_code, str(exc)) from None
        except (ValueError, OSError, TypeError, KeyError):
            raise HTTPException(409, "This generated login is unavailable or changed. Use your existing app login, or review app login setup.") from None
        store.audit("credential.revealed", key)
        return login

    @app.post("/api/deployments/install", status_code=202)
    async def deployment_install(body: ApplyReview, request: Request):
        _, owner = session(request)
        if wiring_lock.locked():
            raise HTTPException(409, "Wait for app connection setup to finish before installing apps.")
        review = deployment_reviews.pop(owner, None)
        if not (deployments or controller) or not review or review[1] <= time.monotonic() or not hmac.compare_digest(review[0], body.review_token):
            raise HTTPException(409, "Review your installation again before installing.")
        if controller and "controller_reference" in review[2]:
            if onboarding.read(store)["revision"] != review[2]["draft_revision"]:
                raise HTTPException(409, "Your choices changed. Review the installation again.")
            if store.config()[0] != review[2]["config_revision"]:
                raise HTTPException(409, "Settings changed. Review the installation again.")
            try:
                remote = await controller.request("install", {"review_reference": review[2]["controller_reference"]})
            except ControllerConnectionError as exc:
                raise HTTPException(exc.status_code, str(exc)) from None
            if not isinstance(remote.get("id"), str) or not re.fullmatch(r"[a-f0-9]{32}", remote["id"]):
                raise HTTPException(503, "Check installation progress before trying another action.")
            with store.db() as db:
                db.execute("INSERT INTO controller_connections(id,revision,ports) VALUES(?,?,?)",
                           (remote["id"], review[2]["config_revision"], json.dumps(review[2]["ports"])))
                db.execute("INSERT INTO controller_quality_profiles(id,profiles) VALUES(?,?)",
                           (remote["id"], json.dumps(review[2]["quality_profiles"])))
            return {"id": remote["id"], "accepted": True}
        return {"id": deployments.enqueue(review[2]), "accepted": True}

    @app.post("/api/deployments/{identity}/resume", status_code=202)
    async def deployment_resume(identity: str, request: Request):
        session(request)
        if wiring_lock.locked():
            raise HTTPException(409, "Wait for app connection setup to finish before resuming installation.")
        if controller:
            try:
                await controller.request("resume", {"id": identity})
            except ControllerConnectionError as exc:
                raise HTTPException(exc.status_code, str(exc)) from None
            return {"accepted": True}
        if not deployments:
            raise HTTPException(409, "Open the local launcher to resume installation.")
        deployments.resume(identity)
        return {"accepted": True}

    @app.put("/api/onboarding")
    def save_setup_draft(body: onboarding.SaveDraft, request: Request):
        session(request)
        return onboarding.save(store, body)

    @app.post("/api/onboarding/connections/review")
    def review_existing_connections(request: Request):
        _, owner = session(request)
        now = time.monotonic()
        for key in list(existing_app_reviews):
            if existing_app_reviews[key][1] <= now:
                del existing_app_reviews[key]
        if len(existing_app_reviews) >= 100 and owner not in existing_app_reviews:
            raise HTTPException(429, "Too many pending connection reviews. Try again later.")
        try:
            review = onboarding.connection_review(store)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        token = secrets.token_urlsafe(32)
        existing_app_reviews[owner] = (token, now + 300, review)
        return {**review, "review_token": token, "expires_in": 300}

    @app.post("/api/onboarding/connections/apply")
    def apply_existing_connections(body: ApplyReview, request: Request):
        _, owner = session(request)
        if deployments and (any(row["state"] in ("queued", "running") for row in deployments.rows()) or deployments.actions.busy()):
            raise HTTPException(409, "Wait for installation to finish before saving existing-app connections.")
        review = existing_app_reviews.pop(owner, None)
        if not review or review[1] <= time.monotonic() or not hmac.compare_digest(review[0], body.review_token):
            raise HTTPException(409, "Review the existing-app connections before saving them.")
        if wiring_lock.locked():
            raise HTTPException(409, "Wait for app connection setup to finish, then review again.")
        return onboarding.connect_reviewed(store, review[2])

    @app.get("/api/onboarding/readiness")
    def setup_readiness(request: Request):
        session(request)
        draft = onboarding.SetupDraft.model_validate(onboarding.read(store)["draft"])
        return onboarding.readiness(draft)

    @app.get("/api/onboarding/storage")
    def storage_plan(request: Request):
        session(request)
        from .storage import layout

        draft = onboarding.SetupDraft.model_validate(onboarding.read(store)["draft"])
        return layout(draft.data_root, draft.install_apps())

    @app.get("/api/onboarding/plan")
    def setup_plan(request: Request):
        session(request)
        try:
            return onboarding.plan(onboarding.SetupDraft.model_validate(onboarding.read(store)["draft"]))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/onboarding/host-check")
    async def setup_host_check(request: Request):
        session(request)
        from .readiness import report

        draft = onboarding.SetupDraft.model_validate(onboarding.read(store)["draft"])
        try:
            config = Config.model_validate(onboarding.plan(draft)["config"])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        result = await asyncio.to_thread(report, config, enabled=host_checks)
        store.audit("setup.host-check")
        return result

    @app.post("/api/onboarding/runtime-check")
    async def setup_runtime_check(request: Request):
        session(request)
        from .docker_runtime import inspect

        checked_revision = onboarding.read(store)["revision"]
        if runtime_check_lock.locked():
            raise HTTPException(409, "A Docker check is already running. Wait for its results.")
        async with runtime_check_lock:
            if controller:
                try:
                    result = await controller.request("runtime-check")
                except ControllerConnectionError as exc:
                    journey_readiness.remember_runtime(store, {"state": "not-checked"}, draft_revision=checked_revision)
                    raise HTTPException(exc.status_code, str(exc)) from None
            else:
                result = await asyncio.to_thread(inspect, enabled=host_checks)
            store.audit("setup.runtime-check")
            journey_readiness.remember_runtime(store, result, draft_revision=checked_revision)
            return result

    @app.post("/api/onboarding/discover")
    async def discover_local_apps(request: Request):
        session(request)
        from .discovery import discover

        if discovery_lock.locked():
            raise HTTPException(409, "An app check is already running. Wait for its results.")
        async with discovery_lock:
            draft = onboarding.SetupDraft.model_validate(onboarding.read(store)["draft"])
            selected = draft.apps or list(APP_IDS)
            if controller:
                try:
                    result = await controller.request("discover", {"apps": selected})
                except ControllerConnectionError as exc:
                    raise HTTPException(exc.status_code, "Existing-app discovery needs a matching updated dashboard and host controller. Reopen or update the preview; you can still enter addresses manually.") from exc
                for row in result["results"]:
                    # The browser and Docker dashboard reach the host by different addresses.
                    row["browser_address"] = row["address"]
                    row["address"] = row["address"].replace("http://127.0.0.1:", "http://host.docker.internal:", 1)
            else:
                result = await discover(selected, enabled=host_checks, transport=transport, include_docker=True)
            store.audit("setup.discovery")
            return result

    async def native_call(operation, payload=None):
        try:
            if controller:
                return await controller.request("native-" + operation, payload)
            if operation == "scan":
                return await native_importer.scan()
            if operation == "review":
                return await native_importer.review(payload["app"])
            return await native_importer.redeem(payload["review_reference"])
        except ControllerConnectionError as exc:
            raise HTTPException(exc.status_code, "Native import needs a matching updated host controller. Reopen the updated preview and try again.") from None
        except native_import.NativeImportError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/api/native-imports")
    def native_imports(request: Request):
        session(request)
        return {"apps": native_import.imported(store)}

    @app.post("/api/native-imports/scan")
    async def scan_native(request: Request):
        session(request)
        async with app_native_lock:
            result = await native_call("scan")
            store.audit("native-import.scanned")
            return result

    @app.post("/api/native-imports/review")
    async def review_native(body: NativeIntent, request: Request):
        _, owner = session(request)
        async with app_native_lock:
            native_reviews.pop(owner, None)
            result = await native_call("review", body.model_dump())
            snapshot = native_import.Snapshot.model_validate(result["snapshot"]).model_dump()
            if snapshot["app"] != body.app:
                raise HTTPException(422, "Native app identity changed. Scan again.")
            address = native_import.dashboard_address(snapshot, bool(controller))
            revision, _ = native_import.target(store, body.app, address)
            now = time.monotonic()
            for key in list(native_reviews):
                if native_reviews[key][1] <= now:
                    del native_reviews[key]
            if len(native_reviews) >= 100:
                raise HTTPException(429, "Too many pending reviews. Try again in a few minutes.")
            token = secrets.token_urlsafe(32)
            native_reviews[owner] = (token, now + 300, revision, result["review_reference"], snapshot)
            return {"review_token": token, "snapshot": snapshot, "notice": native_import.NOTICE}

    @app.post("/api/native-imports/apply")
    async def apply_native(body: ApplyReview, request: Request):
        _, owner = session(request)
        async with app_native_lock, wiring_lock:
            review = native_reviews.get(owner)
            if not review or not secrets.compare_digest(body.review_token, review[0]) or review[1] <= time.monotonic():
                raise HTTPException(409, "Review this native import again before applying it.")
            del native_reviews[owner]
            if store.config()[0] != review[2]:
                raise Conflict("Stackarr settings changed since the preview. Review again.")
            bundle = await native_call("redeem", {"review_reference": review[3]})
            try:
                return await native_import.connect(store, bundle, review[2], review[4], remote=bool(controller), transport=transport)
            except (httpx.HTTPError, IntegrationError, ValueError, KeyError, TypeError):
                raise HTTPException(422, "The native app could not be imported. Check that the dashboard can reach it, then review again. No connection was saved.") from None

    @app.post("/api/refresh", status_code=202)
    async def start_refresh(request: Request):
        session(request)
        return {"accepted": True, "job_id": jobs.enqueue("refresh")}

    @app.get("/api/jobs")
    def list_jobs(request: Request):
        session(request)
        return jobs.rows()

    @app.post("/api/jobs/{identity}/cancel")
    def cancel_job(identity: str, request: Request):
        session(request)
        jobs.cancel(identity)
        return {"cancelled": True}

    @app.get("/api/export")
    def export(request: Request):
        session(request)
        return store.export()

    @app.post("/api/backup")
    def backup(request: Request):
        session(request)
        try:
            return {"file": store.backup(store.config()[1].maintenance.backup_retention), "secrets_included": False}
        except (ValueError, OSError) as exc:
            store.audit("backup.failed")
            raise HTTPException(422, "Backup could not be created. Check free space and permissions on the data folder.") from exc

    @app.get("/api/audit")
    def audit(request: Request):
        session(request)
        return store.audit_rows()

    @app.get("/api/backups")
    def list_backups(request: Request):
        session(request)
        try:
            return store.backups()
        except (ValueError, OSError) as exc:
            raise HTTPException(422, "Backups could not be read. Check the data folder and its permissions.") from exc

    @app.get("/api/notifications")
    def notification_status(request: Request):
        session(request)
        return collector.notifications.rows()

    @app.post("/api/notifications/test")
    def test_notification(request: Request):
        session(request)
        try:
            collector.notifications.test()
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"queued": True, "message": "Test queued for the next background check. Inspect delivery status in Health."}

    @app.post("/api/backups/{name}/preview")
    def preview_backup(name: str, request: Request):
        session(request)
        try:
            config = store.backup_draft(name)
        except (ValueError, OSError) as exc:
            raise HTTPException(422, "Backup failed verification. Check its checksum and configuration format before restoring.") from exc
        store.audit("backup.restore-previewed")
        return {"config": config, "saved": False,
                "message": "Backup staged for review. Save settings to apply it. Existing credentials stay unchanged; notifications are disabled."}

    @app.get("/api/support")
    def support(request: Request):
        session(request)
        _, config = store.config()
        return {
            "version": __version__,
            "schema": config.version,
            "integrations": [
                {"id": r["id"], "state": r["state"], "stale": r["stale"]}
                for r in collector.view()["integrations"]
            ],
            "audit": store.audit_rows(),
            "notice": "No addresses, paths, media titles, credentials or raw errors included.",
        }

    @app.get("/api/plan")
    def plan(request: Request):
        session(request)
        from .installer import compose_plan

        return compose_plan(store.config()[1])

    @app.get("/api/wiring/preview")
    async def wiring_preview(request: Request):
        _, owner = session(request)
        from .wiring import build_plan, public_plan

        plan = await build_plan(store, transport)
        now = time.monotonic()
        for key in list(wiring_reviews):
            if wiring_reviews[key][1] <= now:
                del wiring_reviews[key]
        if len(wiring_reviews) >= 100 and owner not in wiring_reviews:
            raise HTTPException(429, "Too many pending reviews. Try again in five minutes.")
        token = secrets.token_urlsafe(32)
        wiring_reviews[owner] = (token, now + 300, plan)
        journey_readiness.remember_wiring(store, plan)
        return {**public_plan(plan), "review_token": token, "expires_in": 300}

    @app.get("/api/indexers/status")
    async def indexer_status(request: Request):
        session(request)
        from .indexers import status

        checked_revision = store.config()[0]
        try:
            result = await status(store, transport)
        except (ValueError, httpx.HTTPError, TypeError, KeyError):
            journey_readiness.remember_sources(store, None, config_revision=checked_revision)
            raise HTTPException(409, "Source status is unavailable. Check Prowlarr and its saved connection.") from None
        journey_readiness.remember_sources(store, result, config_revision=checked_revision)
        return result

    from .indexers import ProviderSource, Source, SourceCheck

    @app.get("/api/indexers/catalog")
    async def indexer_catalog(request: Request):
        session(request)
        from .indexers import catalog

        try:
            async with asyncio.timeout(20):
                return await catalog(store, transport)
        except (ValueError, httpx.HTTPError, TypeError, KeyError, TimeoutError):
            raise HTTPException(409, "Provider choices are unavailable. Check Prowlarr and its saved connection, or use Advanced provider setup.") from None

    def save_source_review(owner, plan):
        now = time.monotonic()
        for key in list(indexer_reviews):
            if indexer_reviews[key][1] <= now:
                del indexer_reviews[key]
        if len(indexer_reviews) >= 100 and owner not in indexer_reviews:
            raise HTTPException(429, "Too many pending source reviews. Try again in five minutes.")
        token = secrets.token_urlsafe(32)
        indexer_reviews[owner] = (token, now + 300, plan)
        return token

    @app.post("/api/indexers/providers/review")
    async def review_provider_source(body: ProviderSource, request: Request):
        _, owner = session(request)
        if store.config()[1].integrations["prowlarr"].read_only:
            raise HTTPException(409, "Imported Prowlarr is read-only. Open Prowlarr to add or test sources.")
        from .indexers import public, review_provider

        try:
            async with asyncio.timeout(25):
                plan = await review_provider(store, body, transport)
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from None
        except (ValueError, httpx.HTTPError, TypeError, KeyError, StopIteration, TimeoutError):
            raise HTTPException(409, "Could not review this provider. Check its required account details and provider key, or use Advanced provider setup. Nothing was saved.") from None
        return {**public(plan), "review_token": save_source_review(owner, plan)}

    @app.post("/api/indexers/validate")
    async def validate_source_search(body: SourceCheck, request: Request):
        session(request)
        if store.config()[1].integrations["prowlarr"].read_only:
            raise HTTPException(409, "Imported Prowlarr is read-only. Open Prowlarr to add or test sources.")
        from .indexers import validate

        if source_check_lock.locked():
            raise HTTPException(409, "A source search check is already running. Wait for its results.")
        checked_revision = store.config()[0]
        async with source_check_lock:
            try:
                async with asyncio.timeout(50):
                    result = await validate(store, body, transport)
            except TimeoutError:
                journey_readiness.remember_source_validation(store, None, media_type=body.media_type, config_revision=checked_revision)
                raise HTTPException(504, "The source check took too long. Its result is unverified; retry or check the provider in Prowlarr. No media was requested or downloaded.") from None
            except (ValueError, httpx.HTTPError, TypeError, KeyError):
                journey_readiness.remember_source_validation(store, None, media_type=body.media_type, config_revision=checked_revision)
                raise HTTPException(409, "The source search could not be verified. Check Prowlarr and the provider's account details, then retry. No media was requested or downloaded.") from None
            if result.get("sharing") is not None:
                journey_readiness.remember_sources(store, result["sharing"], config_revision=checked_revision)
            journey_readiness.remember_source_validation(store, result, media_type=body.media_type, config_revision=checked_revision)
            return result

    @app.post("/api/indexers/review")
    async def review_indexer(body: Source, request: Request):
        _, owner = session(request)
        if store.config()[1].integrations["prowlarr"].read_only:
            raise HTTPException(409, "Imported Prowlarr is read-only. Open Prowlarr to add or test sources.")
        from .indexers import public, review

        try:
            plan = await review(store, body, transport)
        except (ValueError, httpx.HTTPError, TypeError, KeyError, StopIteration):
            raise HTTPException(409, "Could not prepare this source. Check the feed address and Prowlarr connection; put the provider key in its private field.") from None
        return {**public(plan), "review_token": save_source_review(owner, plan)}

    @app.post("/api/indexers/apply")
    async def apply_indexer(body: ApplyReview, request: Request):
        _, owner = session(request)
        pending = indexer_reviews.pop(owner, None)
        if not pending or pending[1] <= time.monotonic() or not hmac.compare_digest(pending[0], body.review_token):
            raise HTTPException(409, "Review the source again before saving it.")
        from .indexers import apply

        async with wiring_lock:
            try:
                result = await apply(store, pending[2], transport)
                if result.get("state") == "connected":
                    journey_readiness.forget_source_validation(store)
                return result
            except Conflict as exc:
                raise HTTPException(409, str(exc)) from None
            except (ValueError, httpx.HTTPError, TypeError, KeyError):
                raise HTTPException(409, "The source test or save could not finish. Check provider details and its account requirements, then review again. Existing sources are preserved.") from None

    @app.post("/api/wiring/apply")
    async def wiring_apply(body: ApplyReview, request: Request):
        _, owner = session(request)
        from .wiring import apply_plan, public_plan

        async with wiring_lock:
            if deployments and (deployments.actions.busy() or any(row["state"] in ("queued", "running") for row in deployments.rows())):
                raise HTTPException(409, "Wait for the installation or app action to finish before connecting apps.")
            review = wiring_reviews.get(owner)
            if not review or not hmac.compare_digest(review[0], body.review_token) or review[1] <= time.monotonic():
                raise HTTPException(409, "Preview the connections again before applying them.")
            del wiring_reviews[owner]
            plan = review[2]
            if store.config()[0] != plan["revision"]:
                raise HTTPException(409, "Settings changed. Preview the connections again.")
            try:
                store.audit("connection.apply-started")
                results = await apply_plan(store, plan, transport)
                journey_readiness.remember_wiring(store, plan, results)
                return {"results": results, "preview": public_plan(plan)}
            except Exception as exc:
                store.audit("connection.apply-failed")
                raise HTTPException(422, "Connection plan could not be applied; review the preview and app logs.") from exc

    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")

    return app
