"""Writable, atomic local storage checks before Stackarr runtime downtime."""

import os
import shutil
import tempfile
from pathlib import Path

from .backup_policy import direct
from .deployment import DeploymentError

RESERVE = 64 * 1024**2


def check(directory, required=RESERVE):
    directory = direct(Path(directory))
    try:
        if not directory.is_dir():
            raise OSError("Missing state storage")
        if shutil.disk_usage(directory).free < required:
            raise DeploymentError("Free more space on Stackarr's storage, then review repair again. No runtime was paused and existing data is retained.")
        # Exercise creation, durable writes and replacement; a writable existing
        # database alone does not prove that checkpoints can be committed.
        with tempfile.TemporaryDirectory(prefix="storage-check-", dir=directory) as name:
            source, target = Path(name) / "new", Path(name) / "committed"
            with source.open("xb") as output:
                output.write(b"Stackarr storage check")
                output.flush()
                os.fsync(output.fileno())
            os.replace(source, target)
            assert target.read_bytes() == b"Stackarr storage check"
    except DeploymentError:
        raise
    except OSError:
        raise DeploymentError("Stackarr storage is unavailable or does not allow safe writes. Restore folder access or free space, then review repair again. Existing apps and data are retained.") from None
