"""Check an isolated Plex preview using its private local lab access file."""

import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from stackarr.config import validate_url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lab", type=Path)
    parser.add_argument("--finish", action="store_true", help="Verify and save the owned Plex connection after its human account setup")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    access = json.loads((args.lab / "access.json").read_text(encoding="utf-8-sig"))
    original = json.loads((args.lab / "report.json").read_text(encoding="utf-8-sig"))
    origin = validate_url(access["dashboard"], origin_only=True)
    if urlsplit(origin).hostname not in {"localhost", "127.0.0.1"}:
        raise SystemExit("Lab access must use a local dashboard.")
    with httpx.Client(base_url=origin, trust_env=False, timeout=60, headers={"Origin": origin}) as client:
        login = client.post("/api/login", json={"password": access["owner_password"]})
        login.raise_for_status()
        client.headers["X-CSRF-Token"] = login.json()["csrf"]
        deployments = client.get("/api/deployments").json()
        runtime = client.post("/api/onboarding/runtime-check")
        runtime.raise_for_status()
        result = {"controller": deployments.get("controller"), "runtime": runtime.json()["state"],
                  "installation_preserved": any(row["id"] == original["deployment"] and row["state"] == "needs-setup"
                                                for row in deployments["operations"])}
        if args.finish:
            finish = client.post("/api/deployments/" + original["deployment"] + "/finish-connecting")
            finish.raise_for_status()
            result["connection"] = finish.json()
            refresh = client.post("/api/refresh")
            refresh.raise_for_status()
            for _ in range(60):
                sources = client.get("/api/status").json().get("integrations", [])
                plex = next((app for app in sources if app.get("id") == "plex"), None)
                if plex and plex.get("state") == "ready" and not plex.get("stale"):
                    result["plex_monitoring"] = "ready"
                    break
                time.sleep(.5)
            else:
                result["plex_monitoring"] = "not-ready"
        if args.report:
            with args.report.open("x", encoding="utf-8") as output:
                json.dump(result, output, indent=2)
        print(json.dumps(result, indent=2))
        passed = result["controller"] == "connected" and result["runtime"] == "ready" and result["installation_preserved"]
        if args.finish:
            passed = passed and result.get("plex_monitoring") == "ready"
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
