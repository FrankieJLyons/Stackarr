import json
import zipfile

import pytest

from stackarr import __version__
from stackarr.bundled_images import catalog
from stackarr.self_update import FILES
from tools import hosted_package as hosted


@pytest.fixture
def image_bundle(tmp_path):
    root = tmp_path / "images"
    root.mkdir()
    (root / "stackarr-image.tar").write_bytes(b"test image archive")
    receipt = {
        "schema": 1, "source_revision": "a" * 40, "source_dirty": False, "version": __version__,
        "image": hosted.image_name(), "image_id": "sha256:" + "b" * 64, "catalog": catalog(),
        "bundled_app_images": [{"app": key, "image": row["image"], "image_id": "sha256:" + "c" * 64}
                               for key, row in catalog().items()],
        "archive_sha256": hosted.digest(root / "stackarr-image.tar"),
    }
    hosted.write(root / "image-build.json", receipt)
    return root, receipt


def test_offline_handoff_never_invokes_docker(image_bundle, monkeypatch):
    root, receipt = image_bundle
    monkeypatch.setattr(hosted, "docker", lambda _: pytest.fail("Offline validation contacted Docker"))
    assert hosted.validate_bundle(root, "a" * 40, hosted.image_name()) == receipt


@pytest.mark.parametrize("field,value", [
    ("source_revision", "d" * 40), ("source_dirty", True), ("version", "0.0.0"),
    ("image", "stackarr:other"), ("image_id", "unverified"), ("catalog", {}),
    ("bundled_app_images", []), ("archive_sha256", "0" * 64),
])
def test_image_handoff_rejects_changed_inputs(image_bundle, field, value):
    root, receipt = image_bundle
    receipt[field] = value
    hosted.write(root / "image-build.json", receipt)
    with pytest.raises(ValueError):
        hosted.validate_bundle(root, "a" * 40, hosted.image_name())


def test_image_archive_corruption_is_rejected(image_bundle):
    root, _ = image_bundle
    (root / "stackarr-image.tar").write_bytes(b"changed")
    with pytest.raises(ValueError, match="archive changed"):
        hosted.validate_bundle(root, "a" * 40, hosted.image_name())


@pytest.mark.parametrize("system,actions,runner", [
    ("Windows", "true", "github-hosted"), ("Linux", "false", "github-hosted"),
    ("Linux", "true", "self-hosted"),
])
def test_docker_mutation_refuses_non_hosted_machine(monkeypatch, system, actions, runner):
    monkeypatch.setattr(hosted.platform, "system", lambda: system)
    monkeypatch.setenv("GITHUB_ACTIONS", actions)
    monkeypatch.setenv("RUNNER_ENVIRONMENT", runner)
    monkeypatch.setattr(hosted.subprocess, "check_output", lambda *a, **k: pytest.fail("Docker was invoked"))
    with pytest.raises(ValueError, match="disposable"):
        hosted.docker(["load", "--input", "anything"])


@pytest.fixture
def archive(tmp_path):
    payload = {name: ("fixture " + name).encode() for name in FILES}
    import hashlib

    manifest = {"schema": 1, "release": "Test", "image": "stackarr:test", "image_id": "sha256:" + "a" * 64,
                "maintenance": {"protocol": 1, "state_schema": 1},
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()}}
    payload["manifest.json"] = json.dumps(manifest).encode()
    return payload


@pytest.mark.parametrize("attack", ["extra", "traversal", "absolute", "duplicate", "symlink", "corrupt"])
def test_package_zip_rejects_unsafe_or_changed_entries(tmp_path, archive, attack):
    path = tmp_path / "package.zip"
    with zipfile.ZipFile(path, "w") as bundle:
        for name, data in archive.items():
            target = "Test/" + name
            if name == "StackarrPreview.exe":
                if attack == "traversal":
                    target = "../" + name
                elif attack == "absolute":
                    target = "/Test/" + name
                elif attack == "symlink":
                    target = zipfile.ZipInfo(target)
                    target.create_system = 3
                    target.external_attr = 0o120777 << 16
                elif attack == "corrupt":
                    data = b"changed"
            bundle.writestr(target, data)
        if attack == "extra":
            bundle.writestr("Test/extra", b"extra")
        if attack == "duplicate":
            with pytest.warns(UserWarning):
                bundle.writestr("Test/manifest.json", archive["manifest.json"])
    with pytest.raises((ValueError, RuntimeError)):
        hosted.extract(path, tmp_path / "extracted")


def test_exact_package_zip_is_verified(tmp_path, archive):
    path = tmp_path / "package.zip"
    with zipfile.ZipFile(path, "w") as bundle:
        for name, data in archive.items():
            bundle.writestr("Test/" + name, data)
    result = hosted.extract(path, tmp_path / "extracted")
    assert result["release"] == "Test"


def test_launcher_handoff_rejects_wrong_revision_and_tampering(tmp_path):
    exe = tmp_path / "StackarrPreview.exe"
    exe.write_bytes(b"fixture launcher")
    hosted.write(tmp_path / "build-metadata.json", {
        "source_revision": "a" * 40, "artifacts_sha256": {exe.name: hosted.digest(exe)}})
    hosted.validate_launcher(tmp_path, "a" * 40)
    with pytest.raises(ValueError):
        hosted.validate_launcher(tmp_path, "b" * 40)
    exe.write_bytes(b"changed")
    with pytest.raises(ValueError):
        hosted.validate_launcher(tmp_path, "a" * 40)
