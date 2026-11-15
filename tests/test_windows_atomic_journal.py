import json

import pytest

from stackarr.self_update import write


def test_transient_windows_sharing_lock_retries_atomic_replace(tmp_path, monkeypatch):
    import os

    target = tmp_path / 'job.json'
    target.write_text('{"phase":"checkpoint-saved"}')
    replace = os.replace
    attempts, delays = [], []

    def locked(source, destination):
        attempts.append(1)
        if len(attempts) < 3:
            assert json.loads(target.read_text()) == {'phase': 'checkpoint-saved'}
            error = PermissionError('Windows sharing lock')
            error.winerror = 32
            raise error
        replace(source, destination)

    monkeypatch.setattr('stackarr.self_update.os.replace', locked)
    monkeypatch.setattr('stackarr.self_update.time.sleep', delays.append)
    write(target, {'phase': 'succeeded'})
    assert len(attempts) == 3 and delays == [.05, .1]
    assert json.loads(target.read_text()) == {'phase': 'succeeded'}


def test_persistent_windows_denial_keeps_previous_record(tmp_path, monkeypatch):
    target = tmp_path / 'job.json'
    original = '{"phase":"checkpoint-saved"}'
    target.write_text(original)
    attempts, delays = [], []

    def denied(*args):
        attempts.append(1)
        error = PermissionError('Persistent Windows access denial')
        error.winerror = 5
        raise error

    monkeypatch.setattr('stackarr.self_update.os.replace', denied)
    monkeypatch.setattr('stackarr.self_update.time.sleep', delays.append)
    with pytest.raises(PermissionError):
        write(target, {'phase': 'succeeded'})
    assert target.read_text() == original
    assert len(attempts) == 6 and sum(delays) == pytest.approx(.75)
    assert not target.with_suffix('.tmp').exists()
