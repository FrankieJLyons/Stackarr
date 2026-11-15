import os
import zipfile

import pytest

from tools.package_release import package, release_files


def source(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "pyproject.toml").write_text('version = "0.0.0"\n')
    (root / "stackarr").mkdir()
    (root / "stackarr" / "app.py").write_text("# synthetic source\n")
    return root


def test_archive_is_reproducible_and_excludes_runtime(tmp_path):
    root = source(tmp_path)
    for name in ("private.db", "private.db-wal", ".env", ".env.local", "private.pem", "private.pyc", "private.log", "session-private.json", "events-private.jsonl"):
        (root / "stackarr" / name).write_text("must not ship")
    for name in ('.aws', '.ssh', '.codex', '.agents'):
        directory = root / 'stackarr' / name
        directory.mkdir()
        (directory / 'credentials').write_text('must not ship')
    (root / ".github").mkdir()
    (root / ".github" / "test.yml").write_text("# workflow\n")
    first, _, digest = package(root, tmp_path / "one")
    os.utime(root / "stackarr" / "app.py", (1000000000, 1000000000))
    second, _, other = package(root, tmp_path / "two")
    assert digest == other and first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert any(name.endswith(".github/test.yml") for name in archive.namelist())
        assert all(b"must not ship" not in archive.read(name) for name in archive.namelist())


def test_linked_inputs_are_rejected(tmp_path):
    root = source(tmp_path)
    target = tmp_path / "outside.txt"
    target.write_text("not a release input")
    try:
        (root / "stackarr" / "linked.txt").symlink_to(target)
    except OSError:
        pytest.skip("This Windows account cannot create symbolic links")
    with pytest.raises(ValueError, match="filesystem links"):
        list(release_files(root))


def test_audit_blocks_secrets_in_root_files(tmp_path):
    root = source(tmp_path)
    (root / "README.md").write_text("gh" + "p_" + "x" * 40)
    with pytest.raises(ValueError, match="audit failed"):
        package(root, tmp_path / "release")
    assert not list((tmp_path / "release").glob("*.zip"))


def test_only_exact_public_docker_pool_literal_is_exempt_from_ip_audit():
    from tools.audit_source import source_findings

    public = b'"192.168.' + b'0.0/16"'
    assert not source_findings("stackarr/docker_networks.py", public)
    assert source_findings("README.md", public) == [("private-ip", 1)]
    assert source_findings("stackarr/docker_networks.py", public + b' 10.' + b'23.45.67') == [("private-ip", 1)]
    assert source_findings("stackarr/docker_networks.py", public + b' gh' + b'p_' + b'x' * 40) == [("github-token", 1)]


def test_gateway_network_constants_do_not_allow_private_installation_addresses():
    from tools.audit_source import source_findings

    public = b'"10.' + b'0.0.0/8" "192.168.' + b'0.0/16"'
    assert not source_findings("stackarr/lan_gateway.py", public)
    assert source_findings("README.md", public) == [("private-ip", 2)]
    assert source_findings("stackarr/lan_gateway.py", public + b' "192.168.' + b'50.10"') == [("private-ip", 1)]
