"""Authenticated private RPC; never a browser API or general Docker proxy.

Enrollment and network binding are deliberately separate from this ASGI factory.
The host launcher must provision a random shared key privately on both sides.
"""

import asyncio
import hashlib
import hmac
import json
import re
import secrets
import ssl
import time
from contextlib import asynccontextmanager, suppress
from typing import Literal
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import Field

from .backup_policy import BackupPolicyIntent
from .config import APP_IDS, Model
from .controller import InstallIntent, PortIntent
from .deployment import DeploymentError
from .native_import import NativeIntent
from .store import Conflict

MAX_BODY = 16384
MAX_RESPONSE = 262144


def os_checking():
    import os

    return os.environ.get("STACKARR_UPDATE_CHECKING") == "1"


def sign(key, *parts):
    return hmac.new(key, b"\n".join(parts), hashlib.sha256).hexdigest()


def key_check(key):
    if not isinstance(key, bytes) or len(key) != 32:
        raise ValueError("Controller enrollment requires a random 32-byte key")


class Approval(Model):
    review_reference: str = Field(min_length=20, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class Resume(Model):
    id: str = Field(pattern=r"^[a-f0-9]{32}$")


class OwnedLogin(Resume):
    app: Literal["sonarr", "radarr", "prowlarr"]


class CompanionLogin(Resume):
    app: Literal["tautulli", "kuma", "cleanuparr"]


class ManagedIntent(Resume):
    action: Literal["start", "stop", "restart", "repair", "remove", "repair-recover", "backup", "restore", "update", "rollback", "update-recover", "companions", "install-ports"]
    app: str | None = Field(default=None, max_length=32, pattern=r"^[a-z]+$")
    backup: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    update: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    operation: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class FolderQuery(Model):
    root: int | None = Field(default=None, ge=0)
    relative: str = Field(default="", max_length=1024)


class FolderChoice(Model):
    pass


class DiscoveryIntent(Model):
    apps: list[Literal[*APP_IDS]] = Field(max_length=len(APP_IDS))


class StackarrUpdateIntent(Model):
    action: Literal["update", "rollback", "recover", "remove", "repair"]
    id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class PrivateRPC:
    def __init__(self, app, key, authority, store, clock=time.time):
        key_check(key)
        self.app, self.key, self.authority, self.clock = app, key, authority.encode(), clock
        self.store = store
        with store.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS controller_requests (nonce BLOB PRIMARY KEY, expires REAL)")
        self.busy = False

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        nonce = b""

        async def respond(status, detail):
            body = json.dumps({"detail": detail}).encode()
            signature = sign(self.key, nonce, str(status).encode(), body)
            await send({"type": "http.response.start", "status": status, "headers": [
                (b"content-type", b"application/json"), (b"cache-control", b"no-store"),
                (b"x-stackarr-response", signature.encode()),
            ]})
            await send({"type": "http.response.body", "body": body})

        headers = {}
        for name, value in scope["headers"]:
            if name in headers:
                return await respond(400, "Duplicate headers are not accepted")
            headers[name] = value
        if (headers.get(b"host") != self.authority or b"origin" in headers
                or b"sec-fetch-site" in headers or scope.get("query_string")):
            return await respond(403, "Private controller connection required")
        if scope["method"] != "POST" or headers.get(b"content-type") != b"application/json":
            return await respond(400, "Unsupported controller request")
        stamp = headers.get(b"x-stackarr-time", b"")
        nonce = headers.get(b"x-stackarr-nonce", b"")
        signature = headers.get(b"x-stackarr-signature", b"")
        if (not re.fullmatch(rb"[0-9]{1,12}", stamp) or not re.fullmatch(rb"[a-f0-9]{32}", nonce)
                or not re.fullmatch(rb"[a-f0-9]{64}", signature)):
            return await respond(401, "Controller authentication required")
        now = self.clock()
        if abs(now - int(stamp)) > 60:
            return await respond(401, "Controller request expired; check the host clock")
        body = b""
        try:
            async with asyncio.timeout(5):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    body += message.get("body", b"")
                    if len(body) > MAX_BODY:
                        return await respond(413, "Controller request is too large")
                    if not message.get("more_body"):
                        break
        except TimeoutError:
            return await respond(408, "Controller request timed out")
        expected = sign(self.key, stamp, nonce, scope["method"].encode(), scope["path"].encode(), body)
        if not hmac.compare_digest(signature, expected.encode()):
            return await respond(401, "Controller authentication failed")
        if os_checking() and scope["path"] not in {"/v1/stackarr-probe", "/v1/stackarr-updates", "/v1/status", "/v1/stackarr-update-review", "/v1/stackarr-update-apply"}:
            return await respond(503, "Stackarr is checking an update. App changes are paused.")
        if self.busy:
            return await respond(429, "Controller is busy; check progress before trying again")
        # Persist accepted nonces so controller restart cannot replay a recent request.
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM controller_requests WHERE expires<=?", (now,))
            duplicate = db.execute("SELECT 1 FROM controller_requests WHERE nonce=?", (nonce,)).fetchone()
            full = db.execute("SELECT COUNT(*) FROM controller_requests").fetchone()[0] >= 1024
            if not duplicate and not full:
                db.execute("INSERT INTO controller_requests VALUES(?,?)", (nonce, now + 121))
        if duplicate:
            return await respond(409, "Controller request was already received; check installation progress")
        if full:
            return await respond(429, "Controller is busy; check progress before trying again")
        self.busy = True
        messages = []
        received = False

        async def replay_receive():
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        async def capture(message):
            messages.append(message)

        try:
            await self.app(scope, replay_receive, capture)
            status = next(m["status"] for m in messages if m["type"] == "http.response.start")
            result = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
            if len(result) > MAX_RESPONSE:
                raise ValueError("Oversized controller response")
            await send({"type": "http.response.start", "status": status, "headers": [
                (b"content-type", b"application/json"), (b"cache-control", b"no-store"),
                (b"x-stackarr-response", sign(self.key, nonce, str(status).encode(), result).encode()),
            ]})
            await send({"type": "http.response.body", "body": result})
        except Exception:
            await respond(503, "Controller could not finish this request; check installation progress")
        finally:
            self.busy = False


def create_controller_app(controller, key, authority, run_worker=True, clock=time.time):
    @asynccontextmanager
    async def lifespan(app):
        worker = asyncio.create_task(controller.deployments.work()) if run_worker else None
        try:
            yield
        finally:
            if worker:
                while (any(row["state"] == "running" for row in controller.deployments.rows())
                       or any(row["state"] == "running" for row in controller.deployments.actions.rows())):
                    await asyncio.sleep(.25)
                worker.cancel()
                with suppress(asyncio.CancelledError):
                    await worker

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return JSONResponse({"detail": "Invalid controller request; review your choices"}, status_code=422)

    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        from .account_setup import AccountSetupError
        from .ports import PortsUnavailable

        if isinstance(exc, AccountSetupError):
            return JSONResponse({"detail": str(exc)}, status_code=409)

        if isinstance(exc, PortsUnavailable):
            return JSONResponse({"detail": str(exc)}, status_code=409)
        if isinstance(exc, DeploymentError) and request.url.path in {"/v1/backup-folder", "/v1/backup-policy-review", "/v1/backup-plan-run", "/v1/host-backup-review"}:
            return JSONResponse({"detail": str(exc)}, status_code=422)
        if isinstance(exc, DeploymentError) and request.url.path.startswith("/v1/stackarr-"):
            return JSONResponse({"detail": str(exc)}, status_code=422)
        if request.url.path in {"/v1/managed-review", "/v1/installation-check", "/v1/app-backups"}:
            return JSONResponse({"detail": "App or backup checks failed. Check the installation and choose a saved compatible snapshot."}, status_code=422)
        return JSONResponse({"detail": "Controller checks failed; review app ports and approved folders"}, status_code=422)

    @app.post("/v1/folders")
    def folders(body: FolderQuery):
        return controller.folders(body.root, body.relative)

    @app.post("/v1/ports")
    def ports(body: PortIntent):
        return controller.ports(body)

    @app.post("/v1/suggest-ports")
    def suggest_ports(body: PortIntent):
        return controller.ports(body, suggest=True)

    @app.post("/v1/media-folder")
    def media_folder(body: FolderChoice):
        return controller.media_folder()

    @app.post("/v1/review")
    def review(body: InstallIntent):
        return controller.review(body)

    @app.post("/v1/install")
    def install(body: Approval):
        return controller.install(body.review_reference)

    @app.post("/v1/status")
    def status():
        return controller.status()

    @app.post("/v1/native-scan")
    async def native_scan():
        return await controller.native_importer.scan()

    from .storage_topology import StorageQuery, topology

    @app.post('/v1/overview-storage')
    def overview_storage():
        from .overview import owned_storage

        return owned_storage(controller.deployments)

    @app.post('/v1/storage-topology')
    async def storage_topology(body: StorageQuery):
        native = None
        if body.plex_port == 32400:
            try:
                native = await controller.native_importer.inspect('plex')
            except ValueError:
                pass
        return await asyncio.to_thread(topology, controller.deployments, body, native)

    @app.post("/v1/native-review")
    async def native_review(body: NativeIntent):
        return await controller.native_importer.review(body.app)

    @app.post("/v1/native-redeem")
    async def native_redeem(body: Approval):
        return await controller.native_importer.redeem(body.review_reference)

    @app.post("/v1/installation-check")
    def installation_check(body: Resume):
        return controller.installation_check(body.id)

    @app.post("/v1/managed-review")
    def managed_review(body: ManagedIntent):
        return controller.managed_review(body.id, body.action, body.app, body.backup, body.update, body.operation)

    @app.post("/v1/managed-apply")
    def managed_apply(body: Approval):
        return controller.managed_apply(body.review_reference)

    @app.post("/v1/app-backups")
    def app_backups():
        return controller.backups()

    @app.post("/v1/backup-policy")
    def backup_policy():
        return controller.deployments.backup_plans.listing()

    @app.post("/v1/backup-folder")
    def backup_folder():
        return controller.deployments.backup_plans.choose()

    @app.post("/v1/backup-policy-review")
    def backup_policy_review(body: BackupPolicyIntent):
        return controller.backup_policy_review(body.model_dump())

    @app.post("/v1/backup-plan-run")
    def backup_plan_run():
        return controller.deployments.backup_plans.run_now()

    @app.post("/v1/backup-key")
    def backup_key():
        return controller.backup_key()

    @app.post("/v1/host-backup-review")
    def host_backup_review():
        return controller.host_backup_review()

    @app.post("/v1/stackarr-probe")
    def stackarr_probe():
        import os
        import sys

        from .app_backups import digest
        from .self_update import PROTOCOL, fingerprint

        return {"protocol": PROTOCOL, "pid": os.getpid(), "executable": digest(__import__("pathlib").Path(sys.executable)),
                "checking": os_checking(), "fingerprint": fingerprint(controller.store.root),
                "key_fingerprint": digest(controller.store.root / "secrets.key")}

    @app.post("/v1/stackarr-updates")
    def stackarr_updates():
        from .self_update import SelfUpdates

        return SelfUpdates.controller(controller).listing()

    @app.post("/v1/stackarr-package")
    def stackarr_package(body: FolderChoice):
        from .self_update import SelfUpdates

        return SelfUpdates.controller(controller).choose()

    @app.post("/v1/stackarr-update-review")
    def stackarr_update_review(body: StackarrUpdateIntent):
        return controller.stackarr_update_review(body.action, body.id)

    @app.post("/v1/stackarr-update-apply")
    def stackarr_update_apply(body: Approval):
        return controller.stackarr_update_apply(body.review_reference)

    @app.post("/v1/updates")
    def updates():
        return controller.updates()

    @app.post("/v1/resume")
    def resume(body: Resume):
        return controller.resume(body.id)

    @app.post("/v1/runtime-check")
    def runtime_check():
        from .docker_runtime import inspect

        return inspect(enabled=True)

    @app.post("/v1/discover")
    async def discover_apps(body: DiscoveryIntent):
        from .discovery import discover

        return await discover(body.apps, enabled=True, include_docker=True)

    @app.post("/v1/accounts-review")
    def accounts_review(body: Resume):
        return controller.accounts_review(body.id)

    @app.post("/v1/accounts-apply")
    def accounts_apply(body: Approval):
        return controller.accounts_apply(body.review_reference)

    @app.post("/v1/plex-connection")
    def plex_connection(body: Resume):
        return controller.plex_connection(body.id)

    @app.post("/v1/app-connections")
    def app_connections(body: Resume):
        return controller.app_connections(body.id)

    @app.post("/v1/seerr-connection")
    def seerr_connection(body: Resume):
        return controller.seerr_connection(body.id)

    @app.post("/v1/arr-logins")
    def arr_logins(body: Resume):
        return controller.arr_logins(body.id)

    @app.post("/v1/arr-login")
    def arr_login(body: OwnedLogin):
        return controller.arr_login(body.id, body.app)

    @app.post("/v1/companion-connections")
    def companion_connections(body: Resume):
        return controller.companion_connections(body.id)

    @app.post("/v1/companion-login")
    def companion_login(body: CompanionLogin):
        return controller.companion_login(body.id, body.app)

    return PrivateRPC(app, key, authority, controller.store, clock)


class ControllerConnectionError(Exception):
    def __init__(self, message, status_code=503):
        super().__init__(message)
        self.status_code = status_code


class ControllerClient:
    def __init__(self, address, key, transport=None, certificate=None, authority=None):
        key_check(key)
        url = urlsplit(address)
        if (url.scheme not in {"http", "https"} or url.username or url.password
                or url.path not in {"", "/"} or url.query or url.fragment
                or url.hostname not in {"127.0.0.1", "localhost", "host.docker.internal"}
                or not url.port):
            raise ValueError("Controller must use an explicitly enrolled local address and port")
        if url.hostname == "host.docker.internal" and url.scheme != "https":
            raise ValueError("Docker-to-host controller traffic requires HTTPS")
        if url.scheme == "https" and not certificate:
            raise ValueError("Controller HTTPS requires the enrolled certificate")
        self.address, self.key, self.transport = address.rstrip("/"), key, transport
        self.authority = authority
        self.certificate = ssl.create_default_context(cafile=certificate) if certificate else None
        self.lock = asyncio.Lock()

    async def request(self, operation, payload=None):
        # A dashboard's status poll and user action share the single private RPC lane.
        # Serialize them rather than retrying an uncertain write or exposing transient busy errors.
        async with self.lock:
            return await self._request(operation, payload)

    async def _request(self, operation, payload=None):
        native_operations = {"native-scan", "native-review", "native-redeem", "storage-topology", "overview-storage"}
        if operation not in native_operations | {"folders", "media-folder", "ports", "suggest-ports", "review", "install", "status", "resume", "runtime-check", "discover", "accounts-review", "accounts-apply", "plex-connection", "seerr-connection", "app-connections", "arr-logins", "arr-login", "installation-check", "managed-review", "managed-apply", "app-backups", "updates", "backup-policy", "backup-folder", "backup-policy-review", "backup-plan-run", "backup-key", "companion-connections", "companion-login", "host-backup-review", "stackarr-probe", "stackarr-updates", "stackarr-package", "stackarr-update-review", "stackarr-update-apply"}:
            raise ValueError("Unsupported controller operation")
        body = json.dumps(payload or {}, separators=(",", ":")).encode()
        if len(body) > MAX_BODY:
            raise ValueError("Controller request is too large")
        stamp, nonce = str(int(time.time())).encode(), secrets.token_hex(16).encode()
        path = "/v1/" + operation
        headers = {"Content-Type": "application/json", "X-Stackarr-Time": stamp.decode(),
                   "X-Stackarr-Nonce": nonce.decode(),
                   "X-Stackarr-Signature": sign(self.key, stamp, nonce, b"POST", path.encode(), body)}
        if self.authority:
            headers["Host"] = self.authority
        try:
            async with httpx.AsyncClient(transport=self.transport, trust_env=False, follow_redirects=False,
                                         verify=self.certificate or True, timeout=3 if operation == "stackarr-probe" else 210 if operation in {"backup-folder", "media-folder", "stackarr-package"} else 45) as client:
                async with client.stream("POST", self.address + path, content=body, headers=headers) as response:
                    result = b""
                    async for chunk in response.aiter_bytes():
                        result += chunk
                        if len(result) > MAX_RESPONSE:
                            raise ControllerConnectionError("Controller returned an oversized response")
                    expected = sign(self.key, nonce, str(response.status_code).encode(), result)
                    supplied = response.headers.get("x-stackarr-response", "")
                    if not supplied.isascii() or not hmac.compare_digest(supplied, expected):
                        raise ControllerConnectionError("Controller identity could not be verified")
                    data = json.loads(result)
                    if response.status_code != 200:
                        status = response.status_code if response.status_code in {409, 422, 429} else 503
                        raise ControllerConnectionError(data.get("detail", "Controller request failed"), status)
                    return data
        except (httpx.HTTPError, ValueError) as exc:
            # No automatic POST retry: a disconnected installation may already be queued.
            raise ControllerConnectionError("Installation connection unavailable. Check progress before trying again") from exc
