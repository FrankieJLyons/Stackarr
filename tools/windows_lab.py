"""Evidence ledger for the Windows runtime spike; never installs or probes a host."""

import argparse
import json
from pathlib import Path

CHECKS = {
    "clean_install": "Install the five selected apps in a disposable Windows environment",
    "signed_out_boot": "Cold boot, remain signed out; observe all apps from a second LAN device",
    "account_storage": "Read/write the approved fixture paths under the actual startup identities",
    "credential_restart": "Authenticate app connections after restart without interactive profile unlock",
    "lan_playback": "Play an owned synthetic sample on another LAN device for five minutes",
    "import_path": "Import a lawful fixture from the download path without copying outside lab storage",
    "https_trust": "Verify gateway TLS from a separately enrolled client, without bypassing validation",
    "quiet_operation": "Confirm no flashing windows or focus stealing during startup and recovery",
    "resource_baseline": "Record idle and playback CPU/RAM with device class and measurement interval",
    "recovery": "Stop a lab-owned app; verify bounded recovery and audit without altering downloads",
    "preserving_uninstall": "Remove the lab installation while preserving sentinel media and foreign state",
}
TOPOLOGIES = ("compose-desktop", "native-windows", "hybrid")


def template(topology):
    if topology not in TOPOLOGIES:
        raise ValueError("Unsupported topology")
    return {
        "schema": 1,
        "topology": topology,
        "environment": "unassigned",
        "versions": {k: "" for k in ("windows", "stackarr", "plex", "qbittorrent", "sonarr", "caddy", "runtime")},
        "checks": {k: {"status": "not_run", "evidence": []} for k in CHECKS},
    }


def evaluate(record, evidence_root):
    """Validate completeness of human observations, not their authenticity.

    Evidence is local, relative, non-empty files. No arbitrary URLs, commands,
    or personal values are echoed in the returned report.
    """
    if not isinstance(record, dict) or record.get("schema") != 1:
        raise ValueError("Unsupported evidence schema")
    if record.get("topology") not in TOPOLOGIES:
        raise ValueError("Unsupported topology")
    root = evidence_root.resolve()
    gaps = []
    if record.get("environment") not in ("disposable-vm", "spare-test-pc"):
        gaps.append("environment-not-qualified")
    versions = record.get("versions", {})
    if not isinstance(versions, dict) or any(
        not isinstance(versions.get(k), str) or not versions[k].strip()
        for k in template(record["topology"])["versions"]
    ):
        gaps.append("versions-incomplete")
    checks = record.get("checks", {})
    if not isinstance(checks, dict) or set(checks) != set(CHECKS):
        raise ValueError("Evidence must include exactly the required checks")
    for name, check in checks.items():
        if not isinstance(check, dict) or check.get("status") not in ("not_run", "pass", "fail", "blocked"):
            raise ValueError("Invalid check status")
        if check["status"] != "pass":
            gaps.append(name + ":" + check["status"])
            continue
        entries = check.get("evidence")
        if not isinstance(entries, list) or not entries:
            gaps.append(name + ":missing-evidence")
            continue
        for entry in entries:
            if not isinstance(entry, str) or not entry or Path(entry).is_absolute():
                gaps.append(name + ":invalid-evidence")
                break
            path = (root / entry).resolve()
            if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size == 0:
                gaps.append(name + ":invalid-evidence")
                break
    return {
        "topology": record["topology"],
        "status": "evidence-complete-awaiting-review" if not gaps else "incomplete",
        "gaps": gaps,
        "notice": "Completeness check only. A human must verify observations and approve a topology.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("template")
    create.add_argument("topology", choices=TOPOLOGIES)
    create.add_argument("output", type=Path)
    check = sub.add_parser("evaluate")
    check.add_argument("record", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "template":
            # Exclusive creation: never replace earlier lab results.
            with args.output.open("x", encoding="utf-8") as stream:
                json.dump(template(args.topology), stream, indent=2)
        else:
            result = evaluate(json.loads(args.record.read_text(encoding="utf-8-sig")), args.record.parent)
            print(json.dumps(result, indent=2))
            return 0 if not result["gaps"] else 1
    except (ValueError, OSError):
        print("Lab record could not be processed. Check the schema, evidence files, and output location.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
