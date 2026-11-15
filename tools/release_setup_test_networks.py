"""Release only this task's stopped disposable containers/networks; retain all volumes."""

import json
import sqlite3
from pathlib import Path

from tools.docker_folder_ports_check import command, hashes, stop_lab

ROOTS = ("docker-folder-ports-7f71cde99aa5", "docker-folder-ports-f0c60d688688", "docker-folder-ports-82f57dcf656d",
         "docker-folder-ports-018b3c86d2dc", "docker-folder-ports-018b3c86d2dc/monitoring-only")


def main():
    running = set(command(["ps", "-q", "--no-trunc"]).splitlines())
    released = []
    partial = Path("test-results/docker-folder-ports-82f57dcf656d/monitoring-only").resolve()
    if (partial / "package-state/installation.json").exists():
        installation = json.loads((partial / "package-state/installation.json").read_text(encoding="utf-8-sig"))
        stop_lab(partial, installation, [])
    for name in ROOTS:
        root = (Path("test-results") / name).resolve()
        assert root.is_relative_to(Path("test-results").resolve())
        state = root / "package-state"
        media = root / "Media with spaces – 电影"
        before = hashes(media)
        installation = json.loads((state / "installation.json").read_text(encoding="utf-8-sig"))
        plans = [(installation["project"], state / "compose.json")]
        with sqlite3.connect(state / "controller/state/stackarr.db") as db:
            for identity, phase in db.execute("SELECT id,state FROM deployments"):
                assert phase in {"needs-setup", "superseded"}
                plans.append(("stackarr-owned-" + identity, state / "controller/state/deployments" / identity / "compose.json"))
        for project, filename in plans:
            compose = json.loads(filename.read_text(encoding="utf-8-sig"))
            identifiers = command(["ps", "-a", "-q", "--filter", "label=com.docker.compose.project=" + project]).splitlines()
            for identity in identifiers:
                info = json.loads(command(["inspect", identity, "--format", '{{json .State}}']))
                assert not info["Running"]
                labels = json.loads(command(["inspect", identity, "--format", '{{json .Config.Labels}}']))
                assert labels["com.docker.compose.project"] == project and labels["com.docker.compose.service"] in compose["services"]
            volumes = command(["volume", "ls", "-q", "--filter", "label=com.docker.compose.project=" + project]).splitlines()
            # down has no volume-removal option: receipts, databases and media remain recoverable.
            command(["compose", "--project-name", project, "-f", str(filename), "down"])
            for volume in volumes:
                assert command(["volume", "inspect", volume, "--format", "{{.Name}}"] ) == volume
            released.append(project)
        assert hashes(media) == before
    assert running <= set(command(["ps", "-q", "--no-trunc"]).splitlines())
    path = Path("test-results/setup-network-capacity-repair.json")
    path.write_text(json.dumps({"released_projects": released, "stopped_test_containers_only": True,
        "configuration_volumes_retained": True, "media_hashes_preserved": True,
        "all_running_containers_preserved": True, "no_prune_or_docker_restart": True}, indent=2))
    print("Released stopped setup-test networks only; every running container, config volume and media hash preserved.")


if __name__ == "__main__":
    main()
