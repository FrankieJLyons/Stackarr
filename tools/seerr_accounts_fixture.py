"""Private-network Plex identity fixture; never handles real Plex accounts."""

import json
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from xml.sax.saxutils import quoteattr

ROOT = Path("/fixture")
STATE = Path("/state/membership.json")
LOCK = threading.RLock()
MACHINE = "stackarr-permissions-fixture"


def state():
    return json.loads(STATE.read_text())


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, value, status=200, xml=False):
        raw = value.encode() if xml else json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/xml" if xml else "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urlsplit(self.path).path
        access = json.loads((ROOT / "access.json").read_text())
        with LOCK:
            saved = state()
            if self.server.server_port == 8888 and path == "/state":
                return self.reply(saved)
            if self.server.server_port == 32400:
                if path in {"/", "/identity"}:
                    return self.reply({"MediaContainer": {"machineIdentifier": MACHINE, "friendlyName": "Permissions sample fixture"}})
                if path == "/library/sections":
                    return self.reply({"MediaContainer": {"Directory": [{"key": "1", "title": "Original test library", "type": "movie", "agent": "tv.plex.agents.movie"}]}})
                return self.reply({"MediaContainer": {"Metadata": [], "totalSize": 0}})
            token = self.headers.get("X-Plex-Token")
            account = next((row for row in access["accounts"] if row["token"] == token), None)
            if not account or account["id"] in saved["revoked"]:
                return self.reply({"error": "Invalid synthetic authorization"}, 401)
            key = "accounts" if path == "/users/account.json" else "memberships" if path == "/api/users" else "other"
            saved["events"][key] = saved["events"].get(key, 0) + 1
            STATE.write_text(json.dumps(saved))
            if path == "/users/account.json":
                return self.reply({"user": {"id": account["id"], "username": account["name"],
                    "email": account["name"] + "@example.invalid", "authToken": token, "thumb": ""}})
            if path == "/api/users" and account["id"] == access["accounts"][0]["id"]:
                rows = []
                for user in access["accounts"][1:]:
                    attrs = {"id": str(user["id"]), "title": user["name"], "username": user["name"],
                             "email": user["name"] + "@example.invalid", "thumb": ""}
                    server = '<Server machineIdentifier="' + MACHINE + '" id="1" />' if user["id"] in saved["shared"] else ""
                    rows.append("<User " + " ".join(k + "=" + quoteattr(v) for k, v in attrs.items()) + ">" + server + "</User>")
                return self.reply("<MediaContainer>" + "".join(rows) + "</MediaContainer>", xml=True)
            return self.reply({"error": "Unsupported fixture endpoint"}, 404)

    def do_POST(self):
        if self.server.server_port != 8888 or self.path != "/membership":
            return self.reply({"error": "Unsupported fixture mutation"}, 404)
        body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", "0")), 8192)))
        allowed = {row["id"] for row in json.loads((ROOT / "access.json").read_text())["accounts"]}
        if set(body) != {"shared", "revoked"} or any(not isinstance(body[k], list) or set(body[k]) - allowed for k in body):
            return self.reply({"error": "Unknown test identity"}, 400)
        with LOCK:
            saved = state()
            saved.update(body)
            STATE.write_text(json.dumps(saved))
        return self.reply({"saved": True})


def main():
    secure = ThreadingHTTPServer(("0.0.0.0", 443), Handler)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(ROOT / "plex.tv.pem", ROOT / "plex.tv.key")
    secure.socket = tls.wrap_socket(secure.socket, server_side=True)
    for server in (secure, ThreadingHTTPServer(("0.0.0.0", 32400), Handler)):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8888), Handler).serve_forever()


if __name__ == "__main__":
    main()
