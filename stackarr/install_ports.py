"""Reviewed port changes for the same partially started, owned installation."""

import copy
import json
import re
import time
import uuid

from .app_maintenance import AppMaintenance
from .backup_policy import direct
from .config import CATALOG, Config
from .deployment import DeploymentError
from .docker_names import app_project
from .host_recovery import canonical
from .onboarding import AppChoice, SetupDraft
from .ports import available, suggestions
from .store import Conflict

LABEL = "io.stackarr.install-ports"
ID = re.compile(r"^[a-f0-9]{32}$")


class InstallPorts:
    def __init__(self, deployments):
        self.deployments, self.store = deployments, deployments.store
        self.maintenance = AppMaintenance(deployments)

    def call(self, payload, *args):
        return self.deployments._call(["--context", payload["context"]["name"], *args])

    def read(self, identity):
        if not ID.fullmatch(identity):
            raise DeploymentError("Choose a saved installation.")
        with self.store.db() as db:
            row = db.execute("SELECT state,payload FROM deployments WHERE id=?", (identity,)).fetchone()
        if not row or row[0] not in {"failed", "interrupted"}:
            raise Conflict("Check installation progress before reviewing new ports.")
        payload = json.loads(row[1])
        canonical(payload)
        if self.deployments.context() != payload["context"]:
            raise DeploymentError("Select the installation's original local Docker context.")
        filename = direct(self.store.root / "deployments" / identity / "compose.json")
        if not filename.is_file() or filename.read_text(encoding="utf-8") != json.dumps(payload["compose"], sort_keys=True):
            raise DeploymentError("Resume the saved port change or inspect the changed installation file before choosing more ports.")
        return payload

    @staticmethod
    def target(payload, ports, generation, before):
        if set(ports) != set(payload["apps"]) or not ID.fullmatch(generation):
            raise DeploymentError("The reviewed app addresses changed.")
        result = copy.deepcopy(payload)
        result.pop("install_ports", None)
        for key, port in ports.items():
            original = int(payload["compose"]["services"][key]["ports"][0]["published"])
            result["config"]["integrations"][key]["port"] = port
            service = result["compose"]["services"][key]
            service["ports"][0]["published"] = str(port)
            if key == "qbittorrent":
                service["ports"][0]["target"] = port
                service["environment"]["WEBUI_PORT"] = str(port)
            if port != original or not before[key].get("running", False):
                service.setdefault("labels", {})[LABEL] = generation
        Config.model_validate(result["config"])
        canonical(result)
        return result

    def transition(self, payload):
        record = payload.get("install_ports")
        if not record:
            return None
        if record.get("format") != 1 or not ID.fullmatch(record.get("generation", "")):
            raise DeploymentError("The saved port recovery record changed. Keep its settings for inspection.")
        source = copy.deepcopy(payload)
        source.pop("install_ports", None)
        source.update(record["source"])
        canonical(source)
        expected = self.target(source, record["ports"], record["generation"], record["before"])
        target = copy.deepcopy(payload)
        target.pop("install_ports", None)
        if expected != target:
            raise DeploymentError("The saved recovery changes more than the reviewed app addresses. Nothing was replaced.")
        return source, record

    def inspect(self, identity, payload):
        canonical(payload)
        previous = self.transition(payload)
        project = app_project(identity, payload)
        network_ids = self.call(payload, "network", "ls", "-q", "--no-trunc", "--filter", "name=^" + project + "_control$").split()
        network = None
        if network_ids:
            if len(network_ids) != 1:
                raise DeploymentError("The installation network is ambiguous.")
            network = json.loads(self.call(payload, "network", "inspect", network_ids[0]))[0]
            labels = network.get("Labels") or {}
            if (labels.get("com.docker.compose.project") != project or labels.get("com.docker.compose.network") != "control"
                    or network.get("Driver") != "bridge"):
                raise DeploymentError("The private installation network changed. Nothing was replaced.")
        result, expected_ids = {}, set()
        for key in payload["apps"]:
            info = self.maintenance.container(identity, payload, key)
            recipe, matched = payload, "current"
            if info:
                expected_ids.add(info["Id"])
                try:
                    self.maintenance.owned(identity, payload, key, info, unstarted=True)
                except DeploymentError:
                    if not previous:
                        raise
                    recipe, matched = previous[0], "previous"
                    self.maintenance.owned(identity, recipe, key, info, unstarted=True)
            volumes = self.call(payload, "volume", "ls", "-q", "--filter", "name=^" + project + "_" + key + "-config$").split()
            if info or volumes:
                resources = self.maintenance.resources(identity, recipe, key, info, unstarted=True)
            else:
                image = json.loads(self.call(payload, "image", "inspect", payload["compose"]["services"][key]["image"]))[0]
                resources = {"image": image["Id"], "volume": None, "network": network["Id"] if network else None, "auxiliary": {}}
            result[key] = {"container": info["Id"] if info else None, "running": bool(info and info["State"].get("Running")),
                           "resources": resources, "recipe": matched}
        actual_ids = set(self.call(payload, "ps", "-aq", "--no-trunc", "--filter", "label=com.docker.compose.project=" + project).split())
        if expected_ids != actual_ids:
            raise DeploymentError("This installation has unexpected or partly renamed containers. Keep its settings and inspect Docker before resuming.")
        return result

    def review(self, identity, reserved=()):
        payload = self.read(identity)
        before = self.inspect(identity, payload)
        if any(row["recipe"] != "current" for row in before.values()):
            raise Conflict("Resume the already reviewed port change before choosing more ports.")
        ports = {key: int(payload["compose"]["services"][key]["ports"][0]["published"]) for key in payload["apps"]}
        blocked = [key for key in payload["apps"] if not before[key]["running"] and (ports[key] in reserved or not available(ports[key]))]
        if not blocked:
            raise Conflict("The unstarted app ports are available now. Choose Resume installation to keep the original addresses.")
        retained = set(reserved) | {port for key, port in ports.items() if key not in blocked}
        choices = suggestions(SetupDraft(apps=blocked, choices={key: AppChoice(port=ports[key]) for key in blocked}), retained)
        ports.update({row["app"]: row["port"] for row in choices})
        generation = uuid.uuid4().hex
        target = self.target(payload, ports, generation, before)
        return {"action": "install-ports", "deployment": identity, "source": payload, "target": target,
                "before": before, "ports": ports, "generation": generation,
                "changes": [{"app": key, "name": CATALOG[key]["name"],
                             "previous": int(payload["compose"]["services"][key]["ports"][0]["published"]), "port": ports[key]} for key in blocked]}

    @staticmethod
    def public(review):
        return {"action": "install-ports", "changes": review["changes"],
                "notice": "Use these available addresses and resume this same installation. Running apps keep their containers and addresses. Only affected or unstarted apps start again, using their retained settings volumes, images and folders. Existing services using the old ports keep running. qBittorrent's matching web port changes where selected; its saved login, downloads and media are retained."}

    def resume_original(self, identity):
        source = self.read(identity)
        before = self.inspect(identity, source)
        ports = {key: int(source["compose"]["services"][key]["ports"][0]["published"]) for key in source["apps"]}
        if any(not row["running"] and not available(ports[key]) for key, row in before.items()):
            raise Conflict("An app port is still busy. Choose Review available ports before resuming.")
        generation = uuid.uuid4().hex
        # Docker can start a previously failed-bind container without restoring
        # its network/port. A generation change recreates only unstarted apps,
        # retaining their volumes, even when the original address is now free.
        return self.approve({"action": "install-ports", "deployment": identity, "source": source,
            "target": self.target(source, ports, generation, before), "before": before,
            "ports": ports, "generation": generation, "changes": []})

    def approve(self, review):
        from .self_update import busy

        identity, source = review["deployment"], review["source"]
        if busy(self.store.root) or self.deployments.actions.busy():
            raise Conflict("Wait for Stackarr/app maintenance before changing installation ports.")
        if self.read(identity) != source or self.inspect(identity, source) != review["before"]:
            raise Conflict("The partial installation changed. Review available ports again.")
        for key, row in review["before"].items():
            if not row["running"] and not available(review["ports"][key]):
                raise Conflict("A proposed port became busy. Nothing changed; review available ports again.")
        target = self.target(source, review["ports"], review["generation"], review["before"])
        if target != review["target"]:
            raise Conflict("Review the requested port changes again.")
        target["install_ports"] = {"format": 1, "generation": review["generation"], "ports": review["ports"],
            "source": {key: source[key] for key in ("config", "compose")}, "before": review["before"]}
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state,payload FROM deployments WHERE id=?", (identity,)).fetchone()
            if not row or row[0] not in {"failed", "interrupted"} or json.loads(row[1]) != source:
                raise Conflict("Installation progress changed. Review again.")
            if db.execute("SELECT 1 FROM deployments WHERE state IN ('queued','running')").fetchone():
                raise Conflict("Wait for the other installation to finish.")
            revision, raw = db.execute("SELECT revision,data FROM settings WHERE id=1").fetchone()
            current = Config.model_validate_json(raw)
            if any(current.integrations[key].enabled or current.integrations[key].url or db.execute("SELECT 1 FROM secrets WHERE name=?", (key,)).fetchone() for key in target["apps"]):
                raise Conflict("An app now has saved connections. Those settings are retained; inspect before resuming.")
            target["config_revision"] = revision
            # One durable transaction publishes the exact approved transition
            # before any recipe or Docker mutation. Restart waits for resume.
            db.execute("UPDATE deployments SET state='queued',payload=?,message=?,updated=? WHERE id=?",
                (json.dumps(target), "Resuming the same installation with reviewed available ports", time.time(), identity))
            db.execute("INSERT INTO audit(time,event,app) VALUES(?,?,?)", (time.time(), "deployment.ports-approved", identity))
        return {"id": identity, "action": "install-ports", "ports": review["ports"]}

    def reconcile(self, identity, payload, filename):
        from .self_update import write

        source, record = self.transition(payload)
        observed = self.inspect(identity, payload)
        for key, before in record["before"].items():
            current = observed[key]
            for field in ("image", "volume", "network", "auxiliary"):
                expected = before["resources"][field]
                if field == "auxiliary" and before["container"] is None and not expected:
                    # A newly created Plex container gains its image-declared
                    # scratch volume. inspect() verifies its exact ownership,
                    # mounts and sole consumer before accepting it.
                    continue
                if expected is not None and current["resources"][field] != expected:
                    raise DeploymentError("Retained image, storage or network changed. Port recovery preserved it for inspection.")
            if current["container"] != before["container"]:
                info = self.maintenance.container(identity, payload, key)
                if not info or current["recipe"] != "current" or (info["Config"].get("Labels") or {}).get(LABEL) != record["generation"]:
                    raise DeploymentError("The reviewed container identity changed. No app was replaced.")
            elif current["running"] != before["running"] and (before["running"] or current["recipe"] == "previous"):
                raise DeploymentError("An app changed state after review. Its current state was preserved.")
        current = filename.read_text(encoding="utf-8")
        allowed = {json.dumps(source["compose"], sort_keys=True), json.dumps(payload["compose"], sort_keys=True)}
        if current not in allowed:
            raise DeploymentError("The installation file changed. The approved port recovery was not applied.")
        if current != json.dumps(payload["compose"], sort_keys=True):
            write(filename, payload["compose"])

    def start(self, identity, payload, base):
        rows = self.inspect(identity, payload)
        replace = [key for key, row in rows.items() if row["recipe"] == "previous" or row["container"] is None]
        start = [key for key, row in rows.items() if key not in replace and not row["running"]]
        common = [*base, "up", "-d", "--no-deps", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "180"]
        if replace:
            self.deployments._call([*common, *replace], timeout=240)
        if start:
            self.deployments._call([*common, "--no-recreate", *start], timeout=240)
        final = self.inspect(identity, payload)
        if any(not row["running"] or row["recipe"] != "current" for row in final.values()):
            raise DeploymentError("Some apps still need startup recovery. Their settings and media are retained.")
        for key in payload["apps"]:
            info = self.maintenance.container(identity, payload, key)
            port = payload["compose"]["services"][key]["ports"][0]
            expected = [{"HostIp": port["host_ip"], "HostPort": port["published"]}]
            if info.get("NetworkSettings", {}).get("Ports", {}).get(str(port["target"]) + "/tcp") != expected:
                raise DeploymentError("Docker did not restore the app's reviewed published address. Its settings are retained; inspect Docker before resuming.")
