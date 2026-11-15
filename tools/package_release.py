"""Create a portable source-release zip without runtime state or legacy scripts."""

import argparse
import hashlib
import json
import os
import re
import zipfile
from pathlib import Path

INCLUDE = (
    "Start Stackarr.cmd",
    "Start Stackarr.sh",
    ".env.example",
    ".gitattributes",
    ".gitignore",
    ".gitleaks.toml",
    ".github",
    ".dockerignore",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "Dockerfile",
    "LICENSE",
    "MANIFEST.in",
    "README.md",
    "SECURITY.md",
    "compose.yaml",
    "pyproject.toml",
    "requirements.lock",
    "docs",
    "platform",
    "stackarr",
    "tests",
    "tools",
)
EXCLUDED_PARTS = {"outputs", ".git", ".venv", "dist", "build", "test-results", "__pycache__", ".runtime", "node_modules", ".pytest_cache", ".ruff_cache", ".aws", ".ssh", ".codex", ".agents"}
EXCLUDED_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".key", ".pem", ".pfx", ".pyc", ".p12", ".log", ".bak"}
EXCLUDED_NAMES = {".env", "history-audit.json"}


def release_files(root: Path):
    root = root.resolve()

    def checked(path):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError("Release inputs must not contain filesystem links")
        if not path.resolve().is_relative_to(root):
            raise ValueError("Release input escapes the source directory")
        return path

    def allowed(path):
        return (path.suffix.lower() not in EXCLUDED_SUFFIXES
                and path.name not in EXCLUDED_NAMES
                and not path.name.startswith(".env.")
                and not path.name.endswith(("-private.json", "-private.jsonl"))
                and not path.name.endswith(("-wal", "-shm", "-journal")))

    for item in INCLUDE:
        path = checked(root / item)
        if not path.exists():
            continue
        if path.is_file():
            yield path
            continue
        for directory, dirs, files in os.walk(path, followlinks=False):
            dirs[:] = [name for name in dirs if name not in EXCLUDED_PARTS]
            for name in dirs:
                checked(Path(directory) / name)
            for name in files:
                candidate = checked(Path(directory) / name)
                if allowed(candidate):
                    yield candidate


def package(root: Path, output: Path):
    root = root.resolve()
    version = re.search(r'^version = "([^"]+)"', (root / "pyproject.toml").read_text(), re.M).group(1)
    archive = output / f"stackarr-{version}-source.zip"
    output.mkdir(parents=True, exist_ok=True)
    prefix = archive.stem
    entries = sorted(set(release_files(root)))
    if __package__:
        from .audit_source import source_findings
    else:
        from audit_source import source_findings
    for source in entries:
        if source_findings(source.relative_to(root).as_posix(), source.read_bytes()):
            raise ValueError("Source audit failed; run the audit tool before packaging")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for source in entries:
            info = zipfile.ZipInfo((Path(prefix) / source.relative_to(root)).as_posix(), (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, source.read_bytes())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(archive.suffix + ".sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    return archive, len(entries), digest


def main():
    parser = argparse.ArgumentParser(description="Build a clean Stackarr source-release zip")
    parser.add_argument("--output", type=Path, default=Path("dist"))
    args = parser.parse_args()
    archive, count, digest = package(Path.cwd(), args.output)
    print(json.dumps({"archive": str(archive), "files": count, "sha256": digest}, indent=2))


if __name__ == "__main__":
    main()
