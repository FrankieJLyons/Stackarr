"""Scan every reachable Git blob without printing potentially secret matching values."""

import argparse
import json
import re
import subprocess
from pathlib import Path

PATTERNS = {
    "private-key": rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "github-token": rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})",
    "credential-assignment": rb"""(?i)(?:api[_-]?key|password|token)\s*[:=]\s*["'][A-Za-z0-9_+/=-]{20,}["']""",
    "windows-path": rb"[A-Z]:\\(?:Users|ProgramData\\MediaStack|MyMediaStack|Settings Backup)",
    "private-ip": rb"\b(?:192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+)\b",
    "legacy-host": rb"MEDIA" + b"-PC|Media" + b"User",
}

# Public Docker defaults are installation constants, not a user's host address.
# Keep this exception tied to one rule, source file and exact quoted literal.
PUBLIC_LITERALS = {
    ("private-ip", "stackarr/docker_networks.py"): (b'"192.168.' + b'0.0/16"',),
    # RFC 1918 network definitions, not installation addresses. Exempt only
    # these exact quoted constants in the gateway and its broad-subnet test.
    ("private-ip", "stackarr/lan_gateway.py"): (b'"10.' + b'0.0.0/8"', b'"192.168.' + b'0.0/16"'),
    ("private-ip", "tests/test_lan_gateway.py"): (b'"10.' + b'0.0.0/8"',),
}


def source_findings(path, data):
    result = []
    for label, pattern in PATTERNS.items():
        checked = data
        for literal in PUBLIC_LITERALS.get((label, path), ()):
            checked = checked.replace(literal, b'"documented-public-default"')
        count = len(re.findall(pattern, checked))
        if count:
            result.append((label, count))
    return result


def audit(history=True):
    findings = []
    scanned = 0
    if history:
        rows = subprocess.check_output(["git", "rev-list", "--objects", "--all"], text=True).splitlines()
        for row in rows:
            sha, _, path = row.partition(" ")
            if subprocess.check_output(["git", "cat-file", "-t", sha], text=True).strip() != "blob":
                continue
            data = subprocess.check_output(["git", "cat-file", "blob", sha])
            scanned += 1
            for label, count in source_findings(path, data):
                findings.append({"blob": sha, "path": path, "rule": label, "count": count})
    else:
        if __package__:
            from .package_release import release_files
        else:
            from package_release import release_files

        for path in release_files(Path.cwd()):
            scanned += 1
            relative = path.relative_to(Path.cwd()).as_posix()
            for label, count in source_findings(relative, path.read_bytes()):
                findings.append({"path": relative, "rule": label, "count": count})
    return {
        "scope": "reachable git blobs" if history else "portable source",
        "scanned": scanned,
        "findings": findings,
        "limitations": "Heuristic scan, not proof of absence. Review binary objects and findings manually.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--working-tree", action="store_true")
    args = parser.parse_args()
    result = audit(not args.working_tree)
    print(json.dumps(result, indent=2))
    if args.working_tree and result["findings"]:
        raise SystemExit(1)
