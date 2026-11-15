"""Prepare a reversible LAN cutover dossier without writing to the installation."""

import argparse
import json
from pathlib import Path

from stackarr.lan_gateway import prepare
from stackarr.self_update import digest, package, read


def prepare_cutover(state, candidate, output, gateway_request, caddy, source_package=None):
    state, candidate, output = (Path(value).resolve() for value in (state, candidate, output))
    if output.exists() or output == state or output.is_relative_to(state) or state.is_relative_to(output):
        raise ValueError("Use a new review directory outside the existing installation.")
    # Deliberately avoid SelfUpdates(state): its constructor/adoption can write.
    source_paths = [state / name for name in ("compose.json", "installation.json")]
    if (state / "stackarr-runtime.json").is_file():
        source = read(state / "stackarr-runtime.json")
        source_paths.append(state / "stackarr-runtime.json")
        source_release = read(state / "stackarr-maintenance" / "releases" / source["release"] / "manifest.json")
        adoption_pending = False
    else:
        # Older previews acquire ownership receipts on the first reviewed
        # maintenance operation. Preparation must not perform that adoption.
        installation = read(state / "installation.json")
        if not source_package or installation.get("owner") != "stackarr-docker-preview-v1":
            raise ValueError("Select the original verified package for this unadopted preview.")
        source_release = package(Path(source_package).resolve())
        source = {"format": 1, "project": installation["project"], "port": installation["port"],
                  "release": digest(Path(source_package) / "manifest.json")}
        adoption_pending = True
    if source.get("format") != 1 or source["port"] != gateway_request["dashboard_port"]:
        raise ValueError("Select an existing managed installation with matching local port.")
    before = {path.name: digest(path) for path in source_paths}
    manifest = package(candidate)
    if manifest.get("lan_access") != 1:
        raise ValueError("Select a tested package with LAN capability.")
    output.mkdir(parents=True, mode=0o700)
    gateway = prepare(output / "gateway", gateway_request | {"state_root": str(state)}, caddy)
    record = {"schema": 1, "status": "prepared-not-approved", "source": {
        "state_root": str(state), "project": source["project"], "local_port": source["port"],
        "release": source_release["release"], "files": before, "adoption_pending": adoption_pending,
        "source_package": str(Path(source_package).resolve()) if source_package else None},
        "candidate": {"directory": str(candidate), "release": manifest["release"], "manifest_sha256": digest(candidate / "manifest.json")},
        "network": gateway["network"], "gateway_sha256": digest(output / "gateway" / "gateway.json"),
        "required_gates": ["second-client-trusted-https", "plex-browser-playback-and-app-link-acceptance",
                           "disposable-host-signed-out-cold-boot", "complete-encrypted-recovery-backup-and-separate-key",
                           "review-source-app-identities-and-selected-plex", "exact-older-preview-adoption-and-update-rehearsal", "owner-cutover-approval"],
        "sequence": ["Verify source files still match this dossier and no maintenance is pending.",
                     "Create and verify a whole-host recovery file; keep the recovery key separately.",
                     "Use the existing reviewed Stackarr update to install the exact candidate, preserving media apps.",
                     "Check local owner sign-in, all existing integrations, backup schedules and Plex playback.",
                     "On the server, review the gateway bundle with --lan-review and inspect the saved review.",
                     "Apply that review with --lan-apply; wait for the encrypted checkpoint and verified success.",
                     "Approve the separate exact DNS/client-trust/firewall/startup plan only after its lab gates pass.",
                     "Run the verified gateway, check the second device and observe normal operation before retirement of any old entry point."],
        "rollback": ["Stop only this bundle's gateway through its owning process/supervisor. Keep its private CA files.",
                     "Open the preserved local dashboard and roll back the LAN operation through Settings.",
                     "Verify the LAN origin is rejected and the local session and app settings still work.",
                     "If necessary, separately roll back the preceding Stackarr package update using its checkpoint.",
                     "Reverse only new task/firewall/DNS/trust entries whose exact receipts match the cutover. Never reset existing network settings."],
        "scope": "Dashboard/controller and a separate gateway only. Native apps, media, databases, app lifecycle ownership and existing startup registrations are not migrated."}
    after = {path.name: digest(path) for path in source_paths}
    if before != after:
        raise ValueError("The source changed during preparation; discard this review and prepare again.")
    (output / "cutover-private.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return {"status": record["status"], "source_unchanged": True, "required_gates": record["required_gates"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--caddy", type=Path, required=True)
    parser.add_argument("--source-package", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare_cutover(args.state, args.candidate, args.output, read(args.request), args.caddy, args.source_package), indent=2))


if __name__ == "__main__":
    main()
