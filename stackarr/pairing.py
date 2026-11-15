"""Short-lived local approval for first-run setup. Never an administrator login."""

import hashlib
import secrets
import threading
import time


class PairingGate:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.pending = None

    def request(self):
        with self.lock:
            if self.pending and self.pending["expires"] > self.clock():
                raise ValueError("A setup request is already waiting. Retry after it expires.")
            token = secrets.token_urlsafe(32)
            self.pending = {"digest": hashlib.sha256(token.encode()).hexdigest(),
                            "code": f"{secrets.randbelow(1000000):06d}",
                            "expires": self.clock() + 120, "approved": False}
            return token, self.pending["code"]

    def display_code(self):
        with self.lock:
            return self.pending["code"] if self.pending and self.pending["expires"] > self.clock() else None

    def approve(self, code):
        with self.lock:
            if not self.pending or self.pending["expires"] <= self.clock() or self.pending["code"] != code:
                return False
            self.pending["approved"] = True
            return True

    def authorized(self, token):
        with self.lock:
            return bool(self.pending and self.pending["expires"] > self.clock()
                        and self.pending["approved"]
                        and secrets.compare_digest(self.pending["digest"], hashlib.sha256(token.encode()).hexdigest()))

    def revoke(self):
        with self.lock:
            self.pending = None
