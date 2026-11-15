"""Persistent, privacy-minimal webhook outbox with bounded automatic retries."""

import time
import uuid

import httpx


class Notifications:
    def __init__(self, store, transport=None):
        self.store, self.transport = store, transport
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS notification_observations (app TEXT PRIMARY KEY, state TEXT);
                CREATE TABLE IF NOT EXISTS notification_outbox (
                    app TEXT PRIMARY KEY, event_id TEXT, state TEXT, attempts INTEGER,
                    next_attempt REAL, delivery TEXT);
            """)

    def observe(self, app, state):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM notification_observations WHERE app=?", (app,)).fetchone()
            if row and row[0] == state:
                return
            db.execute("INSERT OR REPLACE INTO notification_observations VALUES(?,?)", (app, state))
            if row is not None or state != "ready":
                db.execute("INSERT OR REPLACE INTO notification_outbox VALUES(?,?,?,0,0,'pending')",
                           (app, uuid.uuid4().hex, state))

    def test(self):
        if not self.store.config()[1].maintenance.notifications_enabled:
            raise ValueError("Enable notifications and save an HTTPS webhook before sending a test.")
        with self.store.db() as db:
            db.execute("INSERT OR REPLACE INTO notification_outbox VALUES('stackarr',?,'test',0,0,'pending')", (uuid.uuid4().hex,))
        self.store.audit("notification.test-queued")

    def rows(self):
        with self.store.db() as db:
            return [dict(zip(("app", "event_id", "state", "attempts", "next_attempt", "delivery"), row))
                    for row in db.execute("SELECT * FROM notification_outbox ORDER BY app")]

    async def deliver(self, now=None):
        now = time.time() if now is None else now
        _, config = self.store.config()
        if not config.maintenance.notifications_enabled:
            with self.store.db() as db:
                db.execute("DELETE FROM notification_outbox WHERE delivery='pending'")
                db.execute("DELETE FROM notification_observations")
            return
        for row in self.rows():
            if row["delivery"] != "pending" or row["next_attempt"] > now:
                continue
            if row["attempts"] >= 3:
                with self.store.db() as db:
                    db.execute("UPDATE notification_outbox SET delivery='failed' WHERE event_id=?", (row["event_id"],))
                continue
            if row["app"] in config.integrations and not config.integrations[row["app"]].enabled:
                with self.store.db() as db:
                    db.execute("DELETE FROM notification_outbox WHERE event_id=?", (row["event_id"],))
                continue
            with self.store.db() as db:
                result = db.execute("""UPDATE notification_outbox SET attempts=attempts+1,next_attempt=?
                    WHERE event_id=? AND attempts=? AND delivery='pending' AND next_attempt<=?""",
                    (now + 60 * (row["attempts"] + 1), row["event_id"], row["attempts"], now))
                if result.rowcount != 1:
                    continue
            try:
                async with httpx.AsyncClient(timeout=5, trust_env=False, follow_redirects=False, transport=self.transport) as client:
                    response = await client.post(self.store.secret("notification").get("url", ""),
                        json={"event_id": row["event_id"], "app": row["app"], "state": row["state"]})
                    response.raise_for_status()
                delivery = "sent"
            except Exception:
                delivery = "failed" if row["attempts"] >= 2 else "pending"
            with self.store.db() as db:
                db.execute("UPDATE notification_outbox SET delivery=? WHERE event_id=?", (delivery, row["event_id"]))
            self.store.audit("notification." + ("retry-scheduled" if delivery == "pending" else delivery), row["app"])
