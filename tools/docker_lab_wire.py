"""Explicit fresh-lab fixture setup, not the consumer installation workflow."""

import argparse
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from tools.docker_lab_check import docker, verified_lab

# Runs only inside the verified lab Stackarr container; secrets travel on stdin.
SCRIPT = '''
import asyncio,json,secrets,sys
from pathlib import Path
import httpx
from stackarr.config import Config
from stackarr.store import Store
from stackarr.wiring import build_plan,public_plan,apply_plan

async def main():
    payload=json.load(sys.stdin)
    store=Store(Path('/var/lib/stackarr'))
    revision,existing=store.config()
    if any(app.enabled for app in existing.integrations.values()):
        raise ValueError('Lab already configured; preserve existing settings')
    credentials=payload['credentials']
    config=Config().model_dump()
    for app in ('sonarr','radarr','prowlarr','qbittorrent'):
        port=payload['internal_ports'][app]
        config['integrations'][app].update(enabled=True,mode='connect',url=f'http://{app}:{port}',
            browser_url=f"http://localhost:{payload['ports'][app]}")
    qbit=config['integrations']['qbittorrent']['url']
    async with httpx.AsyncClient(timeout=10,trust_env=False) as client:
        login=await client.post(qbit+'/api/v2/auth/login',data=credentials['qbittorrent'],headers={'Referer':qbit})
        if not (login.status_code==204 or (login.status_code==200 and login.text.strip()=='Ok.')):
            raise ValueError('Fresh lab qBittorrent credential rejected')
        password=secrets.token_urlsafe(32)
        # Set a durable password on this new owned fixture, never on an existing app.
        response=await client.post(qbit+'/api/v2/app/setPreferences',
            data={'json':json.dumps({'web_ui_password':password,'save_path':'/data/downloads'})},
            headers={'Referer':qbit})
        response.raise_for_status()
        credentials['qbittorrent']['password']=password
    store.save(Config.model_validate(config),revision,credentials)
    plan=await build_plan(store)
    result={'preview':public_plan(plan),'results':await apply_plan(store,plan)}
    repeat=await build_plan(store)
    result['repeat_proposes_changes']=len(repeat['changes'])
    print(json.dumps(result))

asyncio.run(main())
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--context", required=True)
    parser.add_argument("--apply", action="store_true", help="Configure only a fresh verified disposable lab")
    args = parser.parse_args()
    if not args.apply:
        parser.error("Explicit --apply is required for fresh-lab credential and connection fixtures")
    receipt, containers = verified_lab(args.directory, args.context)
    required = {"sonarr", "radarr", "prowlarr", "qbittorrent"}
    if not required.issubset(containers):
        parser.error("The connection fixture requires Sonarr, Radarr, Prowlarr and qBittorrent")
    credentials = {}
    for app in ("sonarr", "radarr", "prowlarr"):
        xml = docker(args.context, "exec", containers[app]["name"], "cat", "/config/config.xml")
        credentials[app] = {"api_key": ET.fromstring(xml).findtext("ApiKey")}
    logs = docker(args.context, "logs", containers["qbittorrent"]["name"])
    matches = re.findall(r"temporary password is provided for this session: (\S+)", logs)
    if not matches:
        parser.error("Fresh temporary credential not available; preserve existing app configuration")
    credentials["qbittorrent"] = {"username": "admin", "password": matches[-1]}
    payload = {"credentials": credentials, "ports": receipt["ports"],
               "internal_ports": {"sonarr": 8989, "radarr": 7878, "prowlarr": 9696,
                                  "qbittorrent": receipt["ports"]["qbittorrent"]}}
    result = subprocess.run(["docker", "--context", args.context, "exec", "-i",
                             containers["stackarr"]["name"], "python", "-c", SCRIPT],
                            input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8", timeout=120)
    if result.returncode:
        # Avoid leaking exception payloads or upstream bodies containing credentials.
        raise SystemExit("Lab setup failed. No raw credential-bearing output was saved. Inspect the lab privately.")
    report = json.loads(result.stdout)
    (args.directory / "wiring-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if len(report["results"]) != 4 or any(row["state"] != "created" for row in report["results"]) or report["repeat_proposes_changes"]:
        raise SystemExit("Fresh-lab wiring incomplete; inspect the redacted wiring report.")


if __name__ == "__main__":
    main()
