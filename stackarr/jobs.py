"""Durable, bounded read-only operations. External writes are never replayed."""

import asyncio
import time
import uuid

from .store import Conflict


class Jobs:
    KINDS = {"refresh"}

    def __init__(self, store):
        self.store = store
        with store.db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, kind TEXT, state TEXT, attempts INTEGER,
                created REAL, updated REAL, message TEXT)""")
            # Only registered read-only work may be retried after interruption.
            db.execute("""UPDATE jobs SET state=CASE WHEN attempts<3 THEN 'queued' ELSE 'failed' END,
                message='Interrupted by restart', updated=? WHERE state='running'""", (time.time(),))

    def enqueue(self, kind):
        if kind not in self.KINDS:
            raise ValueError("Unsupported operation")
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id FROM jobs WHERE kind=? AND state IN ('queued','running')", (kind,)).fetchone()
            if row:
                return row[0]
            identity = uuid.uuid4().hex
            now = time.time()
            db.execute("INSERT INTO jobs VALUES(?,?,'queued',0,?,?,?)", (identity, kind, now, now, "Waiting to start"))
            self._audit(db, identity, "queued")
            db.execute("""DELETE FROM jobs WHERE state IN ('succeeded','failed','cancelled')
                AND id NOT IN (SELECT id FROM jobs ORDER BY created DESC LIMIT 200)""")
            return identity

    @staticmethod
    def _audit(db, identity, event):
        db.execute("INSERT INTO audit(time,event,app) VALUES(?,?,?)",
                   (time.time(), "job." + event, identity))

    def rows(self):
        with self.store.db() as db:
            cursor = db.execute("SELECT * FROM jobs ORDER BY created DESC LIMIT 200")
            columns = [field[0] for field in cursor.description]
            return [dict(zip(columns, row)) for row in cursor]

    def cancel(self, identity):
        with self.store.db() as db:
            result = db.execute("UPDATE jobs SET state='cancelled',updated=?,message='Cancelled before starting' WHERE id=? AND state='queued'",
                                (time.time(), identity))
            if result.rowcount != 1:
                raise Conflict("Only waiting operations can be cancelled. Refresh the operation list.")
            self._audit(db, identity, "cancelled")

    async def run_one(self, handlers):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id,kind FROM jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            if not row:
                return False
            identity, kind = row
            db.execute("UPDATE jobs SET state='running',attempts=attempts+1,updated=?,message='Checking saved connections' WHERE id=?",
                       (time.time(), identity))
            self._audit(db, identity, "started")
        try:
            await asyncio.wait_for(handlers[kind](), timeout=120)
        except asyncio.CancelledError:
            # Keep running state: startup decides whether another attempt is safe.
            raise
        except Exception:
            state, message = "failed", "Operation failed. Check connection settings, then try again."
        else:
            state, message = "succeeded", "Finished checking connections. See Health for individual app results."
        with self.store.db() as db:
            db.execute("UPDATE jobs SET state=?,message=?,updated=? WHERE id=?", (state, message, time.time(), identity))
            self._audit(db, identity, state)
        return True

    async def work(self, handlers):
        while True:
            if not await self.run_one(handlers):
                await asyncio.sleep(0.25)
