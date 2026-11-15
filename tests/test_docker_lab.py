import json

import pytest

from tools.docker_lab import PORTS, lab_plan, prepare


def test_lab_isolates_names_ports_storage_and_privilege(tmp_path):
    directory = prepare(tmp_path, "sha256:" + "a" * 64, ["plex", "seerr"])
    compose = json.loads((directory / "compose.json").read_text())
    assert compose["networks"] == {"control": {}}
    assert all(value == {} for value in compose["volumes"].values())
    assert set(compose["services"]) == {"plex", "seerr", "stackarr"}
    for name, service in compose["services"].items():
        assert "container_name" not in service and "privileged" not in service
        assert service["restart"] == "no"
        if name != "stackarr":
            assert "@sha256:" in service["image"]
            assert service["platform"] == "linux/amd64"
        assert all(p["host_ip"] == "127.0.0.1" and int(p["published"]) == PORTS[name] for p in service["ports"])
        for mount in service["volumes"]:
            if mount["type"] == "bind":
                assert mount["source"] == str(directory / "media")
                assert mount["read_only"]
    assert "docker.sock" not in json.dumps(compose)
    assert (directory / "media" / "preserve.txt").exists()
    second = prepare(tmp_path, "sha256:" + "a" * 64, ["plex"])
    assert second != directory


def test_lab_rejects_mutable_dashboard_and_unknown_apps(tmp_path):
    with pytest.raises(ValueError):
        lab_plan(tmp_path, "stackarr:latest", ["plex"])
    with pytest.raises(ValueError):
        lab_plan(tmp_path, "sha256:" + "a" * 64, ["unknown"])


@pytest.mark.parametrize("fault", ["network", "bind", "volume", "privileged", "port"])
def test_lab_inspection_rejects_resources_outside_its_scope(tmp_path, monkeypatch, fault):
    from tools import docker_lab_check

    directory = prepare(tmp_path, "sha256:" + "a" * 64, ["plex"])
    compose = json.loads((directory / "compose.json").read_text())

    def inspect(context, *args):
        if args[0] == "context":
            return "npipe:////./pipe/dockerDesktopLinuxEngine"
        app = "stackarr" if "stackarr-1" in args[1] else "plex"
        service = compose["services"][app]
        mounts = [{"Type": m["type"], "Destination": m["target"], "Source": m["source"],
                   "Name": directory.name + "_" + m["source"], "RW": not m.get("read_only", False)}
                  for m in service["volumes"]]
        info = {"Config": {"Labels": {"com.docker.compose.project": directory.name,
                                      "com.docker.compose.service": app}},
                "NetworkSettings": {"Networks": {directory.name + "_control": {}},
                    "Ports": {str(service["ports"][0]["target"]) + "/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(PORTS[app])}]}},
                "HostConfig": {"Privileged": False}, "Mounts": mounts,
                "Image": service["image"], "State": {"Running": True}}
        if app == "plex":
            if fault == "network":
                info["NetworkSettings"]["Networks"] = {"production": {}}
            elif fault == "bind":
                mounts[-1]["Source"] = str(tmp_path / "production-media")
            elif fault == "volume":
                mounts[0]["Name"] = "production-config"
            elif fault == "privileged":
                info["HostConfig"]["Privileged"] = True
            else:
                info["NetworkSettings"]["Ports"]["32400/tcp"][0]["HostIp"] = "0.0.0.0"
        return json.dumps([info])

    monkeypatch.setattr(docker_lab_check, "docker", inspect)
    with pytest.raises(ValueError):
        docker_lab_check.verified_lab(directory, "desktop-linux")
