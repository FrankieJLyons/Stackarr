"""Host-authorized, single-use browser handoff. Never an administrator login."""

import hashlib
import secrets
import time

INVITATION_SECONDS = 5 * 60
BROWSER_APPROVAL_SECONDS = 30 * 60


def initialize(store):
    with store.db() as db:
        db.execute("CREATE TABLE IF NOT EXISTS setup_handoffs (digest TEXT PRIMARY KEY, kind TEXT, expires REAL)")


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def issue(store, origin):
    initialize(store)
    with store.db() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM account").fetchone():
            return origin + "/"
        value = secrets.token_urlsafe(32)
        db.execute("DELETE FROM setup_handoffs")
        db.execute("INSERT INTO setup_handoffs VALUES(?,?,?)", (digest(value), "ticket", time.time() + INVITATION_SECONDS))
    # Fragments never reach HTTP request logs or Referer headers. The page removes
    # this fragment immediately, before exchanging it for an HTTP-only cookie.
    return origin + "/#setup=" + value


def exchange(store, ticket):
    with store.db() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM account").fetchone():
            return None
        row = db.execute("SELECT expires FROM setup_handoffs WHERE digest=? AND kind='ticket'", (digest(ticket),)).fetchone()
        if not row or row[0] <= time.time():
            return None
        db.execute("DELETE FROM setup_handoffs WHERE digest=?", (digest(ticket),))
        cookie = secrets.token_urlsafe(32)
        # Give the approved browser time to choose a password. The one-use
        # invitation's short claim deadline is not the password-entry deadline.
        db.execute("INSERT INTO setup_handoffs VALUES(?,?,?)", (digest(cookie), "browser", time.time() + BROWSER_APPROVAL_SECONDS))
        return cookie


def authorized(store, cookie):
    with store.db() as db:
        return not db.execute("SELECT 1 FROM account").fetchone() and bool(db.execute(
            "SELECT 1 FROM setup_handoffs WHERE digest=? AND kind='browser' AND expires>?",
            (digest(cookie), time.time()),
        ).fetchone())
