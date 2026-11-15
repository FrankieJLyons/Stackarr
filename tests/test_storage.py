import pytest

from stackarr.storage import layout


@pytest.mark.parametrize("path", ["", "media", "C:", "/", "/data/../etc", "C:/"])
def test_unsafe_or_ambiguous_paths_are_not_approved(path):
    assert not layout(path, ["plex"])["valid"]


def test_windows_layout_is_portable_on_any_test_host():
    result = layout("D:/Media Library", ["plex", "sonarr", "qbittorrent"])
    assert result["valid"] and not result["host_verified"]
    assert {row["container"] for row in result["mounts"]} == {"/data"}
    assert next(row for row in result["mounts"] if row["app"] == "plex")["access"] == "read-only"
    assert result["folders"][0]["host"] == "D:\\Media Library\\media\\movies"


def test_monitoring_does_not_require_storage():
    result = layout("", ["kuma", "prowlarr"])
    assert result["valid"] and not result["required"]
    assert result["mounts"] == []


def test_network_share_is_identified_but_not_certified():
    result = layout("//nas.example/media/library", ["sonarr"])
    assert result["valid"] and not result["host_verified"]
    assert any("Network shares" in warning for warning in result["warnings"])
