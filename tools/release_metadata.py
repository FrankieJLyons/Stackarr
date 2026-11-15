"""Record non-secret build inputs and artifact digests for private previews."""

import hashlib
import importlib.metadata
import json
import platform
import subprocess
from pathlib import Path


def metadata(root):
    artifacts = {}
    for path in sorted((root / "dist").iterdir()):
        if path.is_file() and path.name != "build-metadata.json":
            artifacts[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "schema": 1,
        "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "python": platform.python_version(),
        "system": platform.system(),
        "architecture": platform.machine(),
        "artifacts_sha256": artifacts,
        "build_environment_packages": sorted(
            [{"name": dist.metadata["Name"], "version": dist.version}
             for dist in importlib.metadata.distributions()], key=lambda row: row["name"].lower()),
        "limitations": [
            "Unsigned public beta; metadata is not a cryptographic attestation.",
            "CycloneDX inventory covers Python requirements, not native Python/Tcl/Tk libraries or upstream application images.",
            "Environment packages include build and test tools; they are not a list of all bundled executable components.",
            "A successful build does not certify a clean-host installation or startup before login.",
        ],
    }


if __name__ == "__main__":
    root = Path.cwd()
    (root / "dist" / "build-metadata.json").write_text(json.dumps(metadata(root), indent=2), encoding="utf-8")
