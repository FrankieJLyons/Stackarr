import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("windows_lab", Path("tools/windows_lab.py"))
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


def complete(tmp_path):
    record = lab.template("native-windows")
    record["environment"] = "disposable-vm"
    record["versions"] = {k: "synthetic-fixture" for k in record["versions"]}
    (tmp_path / "observation.txt").write_text("Synthetic test evidence, not a real host result.")
    for check in record["checks"].values():
        check.update(status="pass", evidence=["observation.txt"])
    return record


def test_fresh_record_cannot_pass(tmp_path):
    report = lab.evaluate(lab.template("compose-desktop"), tmp_path)
    assert report["status"] == "incomplete"
    assert "signed_out_boot:not_run" in report["gaps"]


def test_evidence_completeness_is_not_certification(tmp_path):
    report = lab.evaluate(complete(tmp_path), tmp_path)
    assert report["status"] == "evidence-complete-awaiting-review"
    assert "human" in report["notice"]


@pytest.mark.parametrize("entry", ["missing.txt", "../outside.txt", "", "https://example.com/log"])
def test_missing_or_escaping_evidence_fails(tmp_path, entry):
    record = complete(tmp_path)
    record["checks"]["signed_out_boot"]["evidence"] = [entry]
    assert "signed_out_boot:invalid-evidence" in lab.evaluate(record, tmp_path)["gaps"]


@pytest.mark.parametrize("state", ["fail", "blocked", "not_run"])
def test_unproved_boot_prevents_recommendation(tmp_path, state):
    record = complete(tmp_path)
    record["checks"]["signed_out_boot"]["status"] = state
    assert lab.evaluate(record, tmp_path)["status"] == "incomplete"


def test_no_evidence_or_missing_check_cannot_pass(tmp_path):
    record = complete(tmp_path)
    record["checks"]["lan_playback"]["evidence"] = []
    assert "lan_playback:missing-evidence" in lab.evaluate(record, tmp_path)["gaps"]
    del record["checks"]["signed_out_boot"]
    with pytest.raises(ValueError):
        lab.evaluate(record, tmp_path)
