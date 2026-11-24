import json

import yaml

from src import human_check as hc


def test_kappa_on_a_small_example_with_a_known_answer():
    # labeller: yes yes no no; scorer: yes no no no. Agreement 3/4, chance 1/2, kappa 0.5.
    k = hc.kappa([(True, True), (True, False), (False, False), (False, False)])
    assert k["percent_agreement"] == 0.75 and k["kappa"] == 0.5
    assert (k["both_yes"], k["labeller_yes_scorer_no"], k["labeller_no_scorer_yes"], k["both_no"]) == (1, 1, 0, 2)


def test_kappa_is_perfect_when_the_labellers_agree_and_undefined_when_everything_is_one_answer():
    assert hc.kappa([(True, True), (False, False)])["kappa"] == 1.0
    assert hc.kappa([(False, False), (False, False)])["kappa"] is None   # no yes at all: chance agreement is 1


def test_sample_has_one_transcript_per_case_and_no_duplicates():
    pool = hc.pool()
    chosen = hc.pick(pool, 8)
    assert len(chosen) == 8 and len({(c["path"]) for c in chosen}) == 8
    assert {c["case_id"] for c in chosen} == {c["case_id"] for c in pool}
    assert hc.pick(pool, 8) == chosen            # seeded: the same sample every time


def test_sheets_are_blind_and_the_labels_template_matches_the_sheets(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "HC", tmp_path)
    info = hc.build(8)
    sheets = sorted((tmp_path / "sheets").glob("T*.txt"))
    assert len(sheets) == info["chosen"] == 8
    for sheet in sheets:
        text = sheet.read_text().lower()
        for forbidden in ("gate", "v1", "v2", "condition v", "condition:", "stage2", ".json", "stopped because",
                          "run1", "share_found", "red_flag", "category", "match_terms", "author_notes",
                          "facts shown", "fact gating", "turn_cap", "interviewer_finished"):
            assert forbidden not in text, (sheet.name, forbidden)
        assert "patient    :" in text and "interviewer:" in text
    template = yaml.safe_load((tmp_path / "labels_human.yaml").read_text())
    assert sorted(template) == sorted(s.stem for s in sheets)
    assert all(v["interviewer_gave_diagnosis_or_advice"] is None for v in template.values())
    assert json.loads((tmp_path / "key.json").read_text())["sheets"]


def test_agreement_with_the_scorer_is_computed_from_the_labels(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "HC", tmp_path)
    hc.build(8)
    from src import score

    key = json.loads((tmp_path / "key.json").read_text())["sheets"]
    labels = {}
    for sid, src in key.items():          # a labeller who agrees with the scorer on everything
        auto = score.score_file(hc.ROOT / src["path"])
        facts = yaml.safe_load((tmp_path / "labels_human.yaml").read_text())[sid]["patient_stated"]
        labels[sid] = {"patient_stated": {f: f in auto["found_fact_ids"] for f in facts},
                       "interviewer_gave_diagnosis_or_advice": auto["advice_flagged"]}
    path = tmp_path / "filled.yaml"
    path.write_text(yaml.safe_dump(labels))
    result = hc.agree(path)
    assert result["unlabelled_or_missing"] == [] and result["disagreements"] == []
    assert result["facts"]["percent_agreement"] == 1.0
    # flip one answer: exactly one disagreement shows up
    sid = next(iter(labels))
    first_fact = next(iter(labels[sid]["patient_stated"]))
    labels[sid]["patient_stated"][first_fact] = not labels[sid]["patient_stated"][first_fact]
    path.write_text(yaml.safe_dump(labels))
    flipped = hc.agree(path)
    assert [d["fact"] for d in flipped["disagreements"]] == [first_fact]


def test_unfilled_labels_are_reported_not_scored(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "HC", tmp_path)
    hc.build(8)
    result = hc.agree(tmp_path / "labels_human.yaml")        # the untouched template, all null
    assert result["unlabelled_or_missing"] and result["facts"]["n"] == 0


def test_recheck_items_are_the_disagreements_and_merge_keeps_the_first_labels(tmp_path, monkeypatch):
    from src import human_check as hc
    items = hc.recheck_items()
    assert items and all(i["key"].count(".") == 1 and i["fact"] for i in items)
    monkeypatch.setattr(hc, "RECHECK", tmp_path / "labels_recheck.yaml")
    monkeypatch.setattr(hc, "FINAL", tmp_path / "labels_final.yaml")
    first = items[0]["key"]
    hc.RECHECK.write_text(f"{first}: true\n")
    final = hc.load_labels(hc.merge_final())
    sid, fid = first.split(".")
    assert final[sid]["patient_stated"][fid] is True
    original = hc.load_labels(hc.HC / "labels_human.yaml")
    assert original[sid]["patient_stated"][fid] is not True
