"""Transactional state: a failed write never exposes a partial configuration."""

import hashlib
import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from cryptography.fernet import Fernet

from .config import Config


class Conflict(Exception):
    pass


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        keyfile = root / "secrets.key"
        if not keyfile.exists():
            with keyfile.open("xb") as file:
                file.write(Fernet.generate_key())
            os.chmod(keyfile, 0o600)
        self.cipher = Fernet(keyfile.read_bytes())
        os.chmod(keyfile, 0o600)
        self.path = root / "stackarr.db"
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER, data TEXT);
                CREATE TABLE IF NOT EXISTS secrets (name TEXT PRIMARY KEY, value BLOB);
                CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY CHECK(id=1), salt TEXT, hash TEXT);
                CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, csrf TEXT, expires REAL);
                CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, time REAL, event TEXT, app TEXT);
                CREATE TABLE IF NOT EXISTS maintenance_schedule (name TEXT PRIMARY KEY, attempted REAL);
            """)
            db.execute("INSERT OR IGNORE INTO settings VALUES(1,1,?)", (Config().model_dump_json(),))
            db.execute("PRAGMA secure_delete=ON")
            revision, raw = db.execute("SELECT revision,data FROM settings WHERE id=1").fetchone()
            config = Config.model_validate_json(raw)
            webhook = config.maintenance.notification_url
            if webhook:
                db.execute("INSERT OR REPLACE INTO secrets VALUES(?,?)", (
                    "notification", self.cipher.encrypt(json.dumps({"url": webhook}).encode())))
                config.maintenance.notification_url = ""
            if json.loads(raw).get("version") != config.version or webhook:
                db.execute("UPDATE settings SET revision=?,data=? WHERE id=1",
                           (revision + 1, config.model_dump_json()))
                db.execute("INSERT INTO audit(time,event,app) VALUES(?,?,?)",
                           (time.time(), "settings.migrated", "stackarr"))
        os.chmod(self.path, 0o600)

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def config(self):
        with self.db() as db:
            revision, data = db.execute("SELECT revision,data FROM settings WHERE id=1").fetchone()
        return revision, Config.model_validate_json(data)

    def save(self, config: Config, expected: int, secrets: dict | None = None, *, complete_controller=None, native_app=None,
             connection_progress=None):
        config = config.model_copy(deep=True)
        secrets = dict(secrets or {})
        if config.maintenance.notification_url:
            secrets["notification"] = {"url": config.maintenance.notification_url}
            config.maintenance.notification_url = ""
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = Config.model_validate_json(db.execute("SELECT data FROM settings WHERE id=1").fetchone()[0])
            for key, integration in previous.integrations.items():
                if integration.read_only and not config.integrations[key].read_only:
                    raise ValueError("Imported native apps must remain read-only. Open the original app to change its settings.")
            if config.maintenance.notifications_enabled and not (
                secrets.get("notification") or db.execute(
                    "SELECT 1 FROM secrets WHERE name='notification'").fetchone()
            ):
                raise ValueError("Enter an HTTPS webhook address before enabling notifications.")
            result = db.execute(
                "UPDATE settings SET revision=revision+1,data=? WHERE id=1 AND revision=?",
                (config.model_dump_json(), expected),
            )
            if result.rowcount != 1:
                raise Conflict("Settings changed in another session. Reload before saving.")
            for name, values in secrets.items():
                if values is None:
                    db.execute("DELETE FROM secrets WHERE name=?", (name,))
                else:
                    db.execute(
                        "INSERT OR REPLACE INTO secrets VALUES(?,?)",
                        (name, self.cipher.encrypt(json.dumps(values).encode())),
                    )
            if complete_controller is not None:
                result = db.execute("UPDATE controller_connections SET activated=1 WHERE id=? AND activated=0",
                                    (complete_controller,))
                if result.rowcount != 1:
                    raise Conflict("Installation connection changed. Reload before connecting.")
            if connection_progress is not None:
                initialize_connection_progress(db)
                identity, progress = connection_progress
                for row in progress:
                    receipt = None
                    if row['state'] == 'connected':
                        key = row['app']
                        receipt = self.cipher.encrypt(json.dumps({
                            'integration': config.integrations[key].model_dump(), 'credential': secrets[key]}).encode())
                    db.execute("""INSERT INTO connection_progress VALUES(?,?,?,?,?)
                        ON CONFLICT(deployment,app) DO UPDATE SET state=excluded.state,detail=excluded.detail,
                        receipt=COALESCE(excluded.receipt,connection_progress.receipt)""",
                               (identity, row['app'], row['state'], row['detail'], receipt))
            if native_app is not None:
                from .onboarding import AppChoice, SetupDraft

                draft_row = db.execute("SELECT data FROM setup_draft WHERE id=1").fetchone()
                draft = SetupDraft.model_validate_json(draft_row[0])
                connection = config.integrations[native_app]
                if native_app not in draft.apps:
                    draft.apps.append(native_app)
                draft.choices[native_app] = AppChoice(mode="connect", url=connection.url, browser_url=connection.browser_url)
                db.execute("UPDATE setup_draft SET revision=revision+1,data=? WHERE id=1", (draft.model_dump_json(),))
            db.execute(
                "INSERT INTO audit(time,event,app) VALUES(?,?,?)", (time.time(), "settings.saved", "stackarr")
            )
        return expected + 1

    def secret(self, name):
        with self.db() as db:
            row = db.execute("SELECT value FROM secrets WHERE name=?", (name,)).fetchone()
        return json.loads(self.cipher.decrypt(row[0])) if row else {}

    def secret_names(self):
        with self.db() as db:
            return [r[0] for r in db.execute("SELECT name FROM secrets")]

    def audit(self, event, app="stackarr"):
        with self.db() as db:
            db.execute("INSERT INTO audit(time,event,app) VALUES(?,?,?)", (time.time(), event, app))
            db.execute("DELETE FROM audit WHERE id NOT IN (SELECT id FROM audit ORDER BY id DESC LIMIT 2000)")

    def audit_rows(self):
        with self.db() as db:
            return [
                dict(zip(("time", "event", "app"), row))
                for row in db.execute("SELECT time,event,app FROM audit ORDER BY id DESC LIMIT 200")
            ]

    def export(self):
        _, config = self.config()
        data = config.model_dump()
        data["maintenance"]["notification_url"] = ""
        data["maintenance"]["notifications_enabled"] = False
        return data

    def backup(self, retention):
        """Portable redacted configuration only; excludes sessions, credentials and media."""
        directory = self.root / "backups"
        if directory.is_symlink() or (hasattr(directory, "is_junction") and directory.is_junction()):
            raise ValueError("Backup directory must not be a filesystem link")
        directory.mkdir(exist_ok=True, mode=0o700)
        target = directory / f"config-{time.time_ns()}.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.export(), indent=2), encoding="utf-8")
        os.replace(temporary, target)
        target.with_suffix(".json.sha256").write_text(hashlib.sha256(target.read_bytes()).hexdigest(), encoding="ascii")
        for old in sorted(directory.glob("config-*.json"))[:-retention]:
            old.unlink()
            old.with_suffix(".json.sha256").unlink(missing_ok=True)
        self.audit("backup.redacted-created")
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO maintenance_schedule VALUES('backup',?)", (time.time(),))
        return target.name

    def claim_backup_schedule(self, now=None):
        now = time.time() if now is None else now
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT attempted FROM maintenance_schedule WHERE name='backup'").fetchone()
            if row and now - row[0] < 86400:
                return False
            db.execute("INSERT OR REPLACE INTO maintenance_schedule VALUES('backup',?)", (now,))
            return True

    def backup_draft(self, name):
        if not re.fullmatch(r"config-[0-9]+\.json", name):
            raise ValueError("Choose a backup from the saved backup list.")
        directory = self.root / "backups"
        path = directory / name
        checksum = path.with_suffix(".json.sha256")
        if any(p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction()) for p in (directory, path, checksum)):
            raise ValueError("Linked backup files cannot be restored.")
        if not path.is_file() or path.stat().st_size > 131072 or not checksum.is_file():
            raise ValueError("Backup is missing, too large or has no recorded checksum. Review it manually.")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != checksum.read_text(encoding="ascii").strip():
            raise ValueError("Backup checksum does not match. Do not restore this file.")
        config = Config.model_validate_json(content).model_dump()
        config["maintenance"].update(notification_url="", notifications_enabled=False)
        return config

    def backups(self):
        directory = self.root / "backups"
        if directory.is_symlink() or (hasattr(directory, "is_junction") and directory.is_junction()):
            raise ValueError("Backup directory must not be a filesystem link")
        rows = []
        for path in sorted(directory.glob("config-*.json"), reverse=True)[:90]:
            try:
                self.backup_draft(path.name)
                verified, message = True, "Checksum and configuration format verified"
            except (ValueError, OSError):
                verified, message = False, "Backup needs attention; checksum or configuration validation failed"
            rows.append({"file": path.name, "verified": verified, "message": message,
                         "contents": "Stackarr settings only; no credentials, app databases or media",
                         "restore_test": "not performed"})
        return rows


def initialize_connection_progress(db):
    """Create additive feature state only on an explicit save, never a health probe."""
    db.execute('''CREATE TABLE IF NOT EXISTS connection_progress (
        deployment TEXT, app TEXT, state TEXT, detail TEXT, receipt BLOB,
        PRIMARY KEY(deployment,app))''')
