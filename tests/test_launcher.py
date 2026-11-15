import pytest

from stackarr.launcher import instance_lock


def test_second_launcher_cannot_share_state_and_lock_releases(tmp_path):
    first = instance_lock(tmp_path)
    try:
        with pytest.raises(RuntimeError, match="already open"):
            instance_lock(tmp_path)
    finally:
        first.close()
    instance_lock(tmp_path).close()
