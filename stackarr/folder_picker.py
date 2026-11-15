"""Bridge authenticated browser requests to a user-operated native folder dialog."""

import threading
from dataclasses import dataclass, field


@dataclass
class Request:
    ready: threading.Event = field(default_factory=threading.Event)
    shown: bool = False
    path: str = ""


class FolderPicker:
    def __init__(self):
        self.lock = threading.Lock()
        self.current = None

    def request(self, timeout=120):
        ticket = Request()
        with self.lock:
            if self.current:
                raise ValueError("A folder chooser is already open. Finish that choice first.")
            self.current = ticket
        try:
            if not ticket.ready.wait(timeout):
                raise ValueError("The folder chooser timed out. Close it and choose a folder again.")
            return ticket.path
        finally:
            with self.lock:
                if self.current is ticket:
                    self.current = None

    def take(self):
        with self.lock:
            if not self.current or self.current.shown:
                return None
            self.current.shown = True
            return self.current

    def complete(self, ticket, path):
        with self.lock:
            if self.current is ticket:
                ticket.path = path or ""
                ticket.ready.set()
