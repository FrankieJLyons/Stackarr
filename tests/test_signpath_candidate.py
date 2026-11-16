import json
import struct
from pathlib import Path

import pytest

from tools import signpath_candidate as signing
from tools.windows_version import write


def binary(*, signed=False, changed=False, magic=0x20b):
    data = bytearray(512)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 64)
    data[64:68] = b"PE\0\0"
    struct.pack_into("<H", data, 88, magic)
    data[-1] = 2 if changed else 1
    if signed:
        security = 88 + (112 if magic == 0x20b else 96) + 32
        struct.pack_into("<II", data, security, len(data), 16)
        struct.pack_into("<I", data, 88 + 64, 12345)
        data.extend(b"certificate-data")
    return bytes(data)


@pytest.mark.parametrize("magic", [0x10b, 0x20b])
def test_only_certificate_and_checksum_changes_are_allowed(magic):
    assert signing.pe_content(binary(magic=magic)) == signing.pe_content(binary(signed=True, magic=magic))
    assert signing.pe_content(binary(magic=magic)) != signing.pe_content(binary(signed=True, changed=True, magic=magic))


@pytest.mark.parametrize("data", [b"not PE", b"MZ" * 40, binary(signed=True) + b"unsigned trailing bytes"])
def test_malformed_or_non_eof_certificates_are_rejected(data):
    with pytest.raises(ValueError):
        signing.pe_content(data)


def test_changed_executable_rejected_before_trusting_publisher(tmp_path, monkeypatch):
    original, returned = tmp_path / "original.exe", tmp_path / "returned.exe"
    original.write_bytes(binary())
    returned.write_bytes(binary(signed=True, changed=True))
    monkeypatch.setattr(signing, "signature", lambda *args: pytest.fail("must reject changed code first"))
    with pytest.raises(ValueError, match="changed executable"):
        signing.accept(original, returned, "a" * 40)


def test_valid_signature_is_required_even_when_code_is_identical(tmp_path, monkeypatch):
    original, returned = tmp_path / "original.exe", tmp_path / "returned.exe"
    original.write_bytes(binary())
    returned.write_bytes(binary(signed=True))
    checked = []
    monkeypatch.setattr(signing, "signature", lambda path, signer: checked.append((path, signer)))
    signing.accept(original, returned, "a" * 40)
    assert checked == [(returned, "a" * 40)]


def test_wrong_revision_creates_no_signing_workspace(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "build-metadata.json").write_text(json.dumps({"source_revision": "b" * 40}))
    work = tmp_path / "work"
    with pytest.raises(ValueError, match="revisions differ"):
        signing.prepare(source, work, "launcher", "a" * 40)
    assert not work.exists()


def test_launcher_receipt_describes_verified_bytes_only(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "StackarrPreview.exe").write_bytes(binary())
    (source / "build-metadata.json").write_text(json.dumps({"source_revision": "a" * 40,
        "artifacts_sha256": {"StackarrPreview.exe": signing.digest(source / "StackarrPreview.exe")}}))
    (source / "extra.exe").write_bytes(b"must not sign")
    monkeypatch.setattr(signing, "metadata", lambda path: None)
    monkeypatch.setattr(signing, "signature", lambda *args: None)
    work = tmp_path / "build/work"
    signing.prepare(source, work, "launcher", "a" * 40)
    assert [p.name for p in (work / "request-launcher").iterdir()] == ["StackarrPreview.exe"]
    returned = tmp_path / "returned"
    returned.mkdir()
    (returned / "StackarrPreview.exe").write_bytes(binary(signed=True))
    signing.receive(work, returned, "launcher", "a" * 40)
    receipt = json.loads((work / "verified/signing-receipt.json").read_text())
    assert receipt["signed"] is True
    assert receipt["files"]["StackarrPreview.exe"] == signing.digest(returned / "StackarrPreview.exe")
    assert "extra.exe" not in receipt["files"]


def test_rehearsal_refuses_user_machine(monkeypatch):
    from tools.windows_signpath_check import run

    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(RuntimeError, match="disposable"):
        run()


def test_version_resource_matches_package_version(tmp_path):
    path = Path(write(tmp_path / "version.txt"))
    assert "StringStruct('ProductName', 'Stackarr')" in path.read_text()
    assert f"StringStruct('ProductVersion', '{signing.__version__}')" in path.read_text()
