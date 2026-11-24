import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
import yaml

from src import human_check as hc


@pytest.fixture()
def hcdir(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "HC", tmp_path)
    hc.build(8)
    return tmp_path


def blank_payload(hcdir):
    return {s["id"]: {"patient_stated": {}, "interviewer_gave_diagnosis_or_advice": None}
            for s in hc.sheet_data(hcdir)["sheets"]}


def test_the_page_data_is_blind(hcdir):
    text = json.dumps(hc.sheet_data(hcdir)).lower()
    for forbidden in ("stage2", ".json", "v1", "v2", "\"condition\"", "condition v", "gate", "run1", "red_flag", "category",
                      "match_terms", "author_notes", "share_found"):
        assert forbidden not in text, forbidden
    data = hc.sheet_data(hcdir)
    assert len(data["sheets"]) == 8 and all(s["turns"] and s["facts"] for s in data["sheets"])
    assert all(t["role"] in ("patient", "interviewer") for s in data["sheets"] for t in s["turns"])


def test_saved_answers_round_trip_into_the_agreement_check(hcdir):
    payload = blank_payload(hcdir)
    sheets = {s["id"]: s for s in hc.sheet_data(hcdir)["sheets"]}
    for sid, s in sheets.items():
        payload[sid]["patient_stated"] = {f["id"]: False for f in s["facts"]}
        payload[sid]["interviewer_gave_diagnosis_or_advice"] = False
    path = hc.save_labels(payload, hcdir)
    saved = yaml.safe_load(path.read_text())
    assert saved["T1"]["interviewer_gave_diagnosis_or_advice"] is False
    result = hc.agree(path)
    assert result["unlabelled_or_missing"] == [] and result["facts"]["n"] > 0
    assert result["facts"]["both_yes"] == 0 and result["facts"]["labeller_yes_scorer_no"] == 0
    reloaded = hc.sheet_data(hcdir)["labels"]              # the page picks up earlier answers when reopened
    assert reloaded["T1"]["interviewer_gave_diagnosis_or_advice"] is False


def test_unanswered_items_stay_null_and_are_reported_not_scored(hcdir):
    payload = blank_payload(hcdir)
    first = next(iter(hc.sheet_data(hcdir)["sheets"]))
    payload[first["id"]]["patient_stated"] = {first["facts"][0]["id"]: True}
    path = hc.save_labels(payload, hcdir)
    result = hc.agree(path)
    assert result["facts"]["n"] == 1 and result["unlabelled_or_missing"]


def test_unknown_fact_ids_and_bad_values_are_refused(hcdir):
    payload = blank_payload(hcdir)
    payload["T1"]["patient_stated"] = {"f99": True}
    with pytest.raises(ValueError):
        hc.save_labels(payload, hcdir)
    payload = blank_payload(hcdir)
    payload["T1"]["interviewer_gave_diagnosis_or_advice"] = "maybe"
    with pytest.raises(ValueError):
        hc.save_labels(payload, hcdir)


def test_the_local_server_serves_the_page_saves_and_rejects(hcdir):
    server = ThreadingHTTPServer(("127.0.0.1", 0), hc.make_handler(hcdir))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        page = urllib.request.urlopen(base + "/").read().decode()
        assert "Label the transcripts" in page
        data = json.loads(urllib.request.urlopen(base + "/data").read())
        assert len(data["sheets"]) == 8
        payload = blank_payload(hcdir)
        req = urllib.request.Request(base + "/save", data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        assert urllib.request.urlopen(req).status == 200
        assert (hcdir / "labels_human.yaml").exists()
        bad = urllib.request.Request(base + "/save", data=b'{"T1": {"patient_stated": {"f99": true}}}', method="POST")
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(bad)
        assert err.value.code == 400
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(base + "/key.json")
        assert err.value.code == 404                         # the key is never served
    finally:
        server.shutdown()
