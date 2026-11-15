"""Original OCI fixture with bounded interrupted-body faults; loopback in the lab only."""

import hashlib
import io
import json
import os
import socket
import tarfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path("/fixture")
LOCK = threading.Lock()
COUNTERS = {"requests": 0, "cuts": 0, "partial_bytes": 0, "held_bytes": 0}


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def build(root, binaries, variant):
    """Build tiny original fixtures from the pinned test engine's musl/busybox."""
    layer = io.BytesIO()
    with tarfile.open(fileobj=layer, mode="w") as archive:
        for name, data, mode in [
            ("bin/busybox", (binaries / "busybox").read_bytes(), 0o755),
            ("lib/ld-musl-x86_64.so.1", (binaries / "musl").read_bytes(), 0o755),
            ("original-download-test.bin", os.urandom(8 * 1024**2), 0o644),
        ]:
            entry = tarfile.TarInfo(name)
            entry.size, entry.mode = len(data), mode
            archive.addfile(entry, io.BytesIO(data))
    data = layer.getvalue()
    layer_digest = digest(data)
    config = json.dumps({"architecture": "amd64", "os": "linux", "rootfs": {"type": "layers", "diff_ids": [layer_digest]},
        "config": {"Cmd": ["/bin/busybox", "sh", "-c", "echo original-settings > /app/config/preserve.txt; exec /bin/busybox sleep 86400"],
                   "Labels": {"io.stackarr.original-fixture": variant}}}, separators=(",", ":")).encode()
    manifest = json.dumps({"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {"mediaType": "application/vnd.oci.image.config.v1+json", "digest": digest(config), "size": len(config)},
        "layers": [{"mediaType": "application/vnd.oci.image.layer.v1.tar", "digest": layer_digest, "size": len(data)}]}, separators=(",", ":")).encode()
    for blob in (data, config, manifest):
        (root / digest(blob).replace(":", "-")).write_bytes(blob)
    return {"image": "localhost:5000/original/" + variant + "@" + digest(manifest),
            "manifest": digest(manifest), "layer": layer_digest, "config": digest(config)}


def record(**changes):
    with LOCK:
        for key, value in changes.items():
            COUNTERS[key] += value
        target = ROOT / "observations.json"
        temporary = ROOT / "observations.tmp"
        temporary.write_text(json.dumps(COUNTERS))
        temporary.replace(target)


class Registry(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_HEAD(self):
        self.serve(False)

    def do_GET(self):
        self.serve(True)

    def serve(self, body):
        record(requests=1)
        if self.path in ("/v2/", "/v2"):
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.send_header("Docker-Distribution-Api-Version", "registry/2.0")
            self.end_headers()
            if body:
                self.wfile.write(b"{}")
            return
        control = json.loads((ROOT / "control.json").read_text())
        if control["mode"] == "unauthorized":
            self.send_response(401)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        kind = "manifest" if "/manifests/" in self.path else "blob" if "/blobs/" in self.path else None
        value = self.path.rsplit("/", 1)[-1]
        if not kind or not value.startswith("sha256:") or len(value) != 71 or any(c not in "0123456789abcdef" for c in value[7:]):
            self.send_error(404)
            return
        file = ROOT / value.replace(":", "-")
        if not file.is_file():
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.oci.image.manifest.v1+json" if kind == "manifest" else "application/octet-stream")
        self.send_header("Docker-Content-Digest", value)
        self.send_header("Content-Length", str(file.stat().st_size))
        self.end_headers()
        if not body:
            return
        data = file.read_bytes()
        fault = kind == "blob" and value == control.get("layer") and control["mode"] in {"hold", "cut-once"}
        try:
            if fault:
                self.wfile.write(data[:262144])
                self.wfile.flush()
                record(partial_bytes=262144)
                if control["mode"] == "cut-once":
                    (ROOT / "control.json").write_text(json.dumps({"mode": "healthy"}))
                    record(cuts=1)
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                record(held_bytes=262144)
                for _ in range(1200):
                    if json.loads((ROOT / "control.json").read_text())["mode"] != "hold":
                        break
                    time.sleep(.1)
                self.wfile.write(data[262144:])
            else:
                self.wfile.write(data)
        except (OSError, ValueError):
            pass


if __name__ == "__main__":
    record()
    # The daemon shares this namespace. The lab publishes this port to host
    # loopback only for the separate frozen-controller acceptance case.
    ThreadingHTTPServer(("0.0.0.0", 5000), Registry).serve_forever()
