"""Local preparation of a separate Caddy gateway and bounded runtime resume.

No service, firewall, DNS, trust-store or router changes are performed here.
The gateway runs in the foreground for an explicitly selected supervisor.
"""

import argparse
import ipaddress
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

from .backup_policy import direct
from .lan import LanAccess
from .self_update import SelfUpdates, digest, read, write

PRIVATE = tuple(ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def private_address(value, lab=False):
    address = ipaddress.ip_address(value)
    if address.version != 4 or not (any(address in network for network in PRIVATE)
                                    or (lab and address == ipaddress.ip_address("127.0.0.1"))):
        raise ValueError("Bind to one private IPv4 LAN address; loopback is available only in lab mode.")
    return str(address)


def gateway_config(origin, bind, clients, dashboard_port, apps=None, lab=False):
    """Generate only fixed reverse-proxy routes to loopback. No injected secrets."""
    if type(dashboard_port) is not int or not 1 <= dashboard_port <= 65535:
        raise ValueError("Choose a valid local dashboard port.")
    apps = apps or {}
    links = {key: row["origin"] for key, row in apps.items()}
    LanAccess(f"http://localhost:{dashboard_port}", {"STACKARR_LAN_ORIGIN": origin,
                                                   "STACKARR_LAN_LINKS": json.dumps(links)})
    bind = private_address(bind, lab)
    if not isinstance(clients, list) or not 1 <= len(clients) <= 8:
        raise ValueError("Choose the specific client subnet or addresses allowed to connect.")
    networks = []
    for value in clients:
        network = ipaddress.ip_network(value, strict=True)
        if (network.version != 4 or network.prefixlen < 16
                or not (any(network.subnet_of(item) for item in PRIVATE)
                        or (lab and str(network) == "127.0.0.1/32"))):
            raise ValueError("Use a private client subnet of /16 or narrower, or individual /32 clients.")
        networks.append(str(network))
    sites = [(origin, dashboard_port)]
    for key, row in apps.items():
        if set(row) != {"origin", "port"} or type(row["port"]) is not int or not 1 <= row["port"] <= 65535:
            raise ValueError("App routes need only a verified HTTPS origin and local port.")
        sites.append((row["origin"], row["port"]))
    listeners = {urlsplit(address).port or 443 for address, _ in sites}
    if listeners & {port for _, port in sites}:
        raise ValueError("Gateway and upstream ports must differ.")
    # JSON strings are also valid Caddyfile quoted tokens; validated addresses
    # contain no placeholders, credentials, paths, quotes or newlines.
    sections = ["{\n admin off\n auto_https disable_redirects\n skip_install_trust\n servers {\n  protocols h1 h2\n }\n}"]
    for address, port in sites:
        sections.append(f'''{address} {{
 bind {bind}
 tls internal
 @allowed remote_ip {" ".join(networks)}
 handle @allowed {{
  reverse_proxy 127.0.0.1:{port} {{
   header_up -Forwarded
   header_up -X-Forwarded-Host
   header_up -X-Forwarded-Proto
   header_up -X-Forwarded-For
  }}
 }}
 handle {{
  respond "Access is limited to the reviewed home network." 403
 }}
}}''')
    # Caddy's default for an unmatched Host can be an empty HTTP 200. Make
    # rejection explicit so a spoofed Host cannot look like a healthy service.
    for port in sorted(listeners):
        sections.append(f'''https://:{port} {{
 bind {bind}
 respond "Host not allowed." 421
}}''')
    return "\n\n".join(sections) + "\n"


def environment(root):
    env = dict(os.environ)
    # Keep CA keys/config away from any pre-existing Caddy installation.
    for name in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME"):
        env[name] = str(root / "private" / name.lower())
    return env


def prepare(output, request, caddy):
    """Produce a reviewable bundle without contacting Docker or a media app."""
    if set(request) - {"origin", "bind", "clients", "dashboard_port", "apps", "lab", "state_root"}:
        raise ValueError("Unexpected gateway settings.")
    config = gateway_config(**{key: value for key, value in request.items() if key != "state_root"})
    root = direct(Path(output).absolute())
    executable = direct(Path(caddy).absolute())
    if not executable.is_file() or not root.parent.is_dir() or root.exists():
        raise ValueError("Choose a Caddy executable and a new gateway bundle directory.")
    root.mkdir(mode=0o700)
    (root / "private").mkdir(mode=0o700)
    binary = root / ("caddy.exe" if os.name == "nt" else "caddy")
    shutil.copyfile(executable, binary)
    binary.chmod(0o700)
    (root / "Caddyfile").write_text(config, encoding="utf-8")
    result = subprocess.run([str(binary), "validate", "--config", str(root / "Caddyfile"), "--adapter", "caddyfile"],
                            env=environment(root), capture_output=True, timeout=30,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    if result.returncode:
        raise ValueError("Caddy rejected the generated configuration. The bundle is retained for inspection.")
    manifest = {"schema": 1, "request": request, "files": {name: digest(root / name) for name in (binary.name, "Caddyfile")},
                "network": {"origin": request["origin"], "links": {key: row["origin"] for key, row in request.get("apps", {}).items()}},
                "startup": "manual-only-until-signed-out-boot-acceptance"}
    write(root / "gateway.json", manifest)
    return manifest


def verified(root):
    root = direct(Path(root).absolute())
    manifest = read(root / "gateway.json")
    binary = "caddy.exe" if os.name == "nt" else "caddy"
    if manifest.get("schema") != 1 or set(manifest.get("files", {})) != {binary, "Caddyfile"}:
        raise ValueError("Unsupported gateway bundle.")
    if any(digest(direct(root / name)) != value for name, value in manifest["files"].items()):
        raise ValueError("Gateway files changed. Prepare and review a new bundle.")
    request = manifest["request"]
    expected = gateway_config(**{key: value for key, value in request.items() if key != "state_root"})
    if (root / "Caddyfile").read_text(encoding="utf-8") != expected:
        raise ValueError("Gateway configuration differs from the reviewed addresses.")
    expected_network = {"origin": request["origin"], "links": {key: row["origin"] for key, row in request.get("apps", {}).items()}}
    if manifest["network"] != expected_network:
        raise ValueError("Gateway and dashboard addresses differ.")
    return root, manifest


def review(bundle, output):
    root, manifest = verified(bundle)
    state = direct(Path(manifest["request"]["state_root"]))
    if not state.is_absolute():
        raise ValueError("Select the absolute installation state directory.")
    value = SelfUpdates(state).review("lan", manifest["network"])
    value = {"bundle": str(root), "bundle_hash": digest(root / "gateway.json"), "state_root": str(state), "review": value}
    with Path(output).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
    return {"notice": value["review"]["notice"], "origin": manifest["network"]["origin"]}


def apply(review_file):
    value = read(direct(Path(review_file)))
    root, manifest = verified(value["bundle"])
    if digest(root / "gateway.json") != value["bundle_hash"] or manifest["request"]["state_root"] != value["state_root"]:
        raise ValueError("Gateway review changed. Review again.")
    if value["review"].get("action") != "lan" or value["review"].get("network") != manifest["network"]:
        raise ValueError("The saved review is not this gateway's LAN operation.")
    return SelfUpdates(Path(value["state_root"])).approve(value["review"])


def resume(bundle, *, readiness=None, start=None, sleep=time.sleep, attempts=6):
    """Bounded dependency wait. Never launch Docker Desktop or enable autologon."""
    from .docker_runtime import inspect

    root, manifest = verified(bundle)
    state = Path(manifest["request"]["state_root"])
    if not state.is_absolute():
        raise ValueError("Select the absolute installation state directory.")
    readiness = readiness or (lambda: inspect(enabled=True))
    start = start or (lambda: SelfUpdates(state).start())
    if type(attempts) is not int or not 1 <= attempts <= 6:
        raise ValueError("Startup needs between one and six bounded attempts.")
    for attempt in range(attempts):
        write(root / "startup-status.json", {"phase": "waiting-for-runtime", "attempt": attempt + 1})
        if readiness().get("state") == "ready":
            # Once Docker is ready, an ownership/port/storage failure is not
            # retried blindly. Existing start() performs signed RPC and receipts.
            try:
                address = start()
                write(root / "startup-status.json", {"phase": "dashboard-started", "attempt": attempt + 1,
                                                      "signed_out_boot": "not-certified"})
                return address
            except Exception:
                write(root / "startup-status.json", {"phase": "needs-attention", "reason": "runtime-start-rejected"})
                raise
        if attempt + 1 < attempts:
            sleep(min(2 ** (attempt + 1), 30))
    write(root / "startup-status.json", {"phase": "needs-attention", "reason": "docker-unavailable",
                                        "signed_out_boot": "not-certified"})
    raise ValueError("Docker did not become ready. Existing services were preserved. Check the supported host startup mechanism.")


def serve(bundle, *, resume_runtime=True):
    root, manifest = verified(bundle)
    if resume_runtime:
        resume(root)
        runtime = SelfUpdates(Path(manifest["request"]["state_root"])).active()
        env = runtime["plan"]["services"]["stackarr"]["environment"]
        access = LanAccess(env["STACKARR_ORIGIN"], env)
        if {"origin": access.origin, "links": access.links} != manifest["network"]:
            raise ValueError("Enable this gateway's reviewed addresses in Stackarr before starting it.")
    binary = root / ("caddy.exe" if os.name == "nt" else "caddy")
    # A foreground child keeps the launcher/supervisor responsible for its own
    # process. No PID-based termination of an existing Caddy process is used.
    with (root / "private" / "gateway.log").open("ab") as output:
        child = subprocess.Popen([str(binary), "run", "--config", str(root / "Caddyfile"), "--adapter", "caddyfile"],
                                 env=environment(root), stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            return child.wait()
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=15)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("request", type=Path)
    prepare_parser.add_argument("output", type=Path)
    prepare_parser.add_argument("--caddy", type=Path, required=True)
    review_parser = sub.add_parser("review")
    review_parser.add_argument("bundle", type=Path)
    review_parser.add_argument("output", type=Path)
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("review", type=Path)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.output, read(args.request), args.caddy)
        print("Gateway bundle prepared and validated. No network or startup settings were changed.")
    elif args.command == "review":
        print(json.dumps(review(args.bundle, args.output)))
    elif args.command == "apply":
        print(json.dumps(apply(args.review)))
    else:
        return serve(args.bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
