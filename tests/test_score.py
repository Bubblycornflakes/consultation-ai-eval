"""Scoring checked on tiny hand-made transcripts where the right answer is known."""
import copy

from src import cases, score

CASE = next(c for c in cases.load_all() if c["id"] == "C01-headache")
TERMS = score.load_match_terms()["C01-headache"]


def record(*pairs, gate=None, extra_after_end=False):
    """pairs: (interviewer question, patient reply or None). Builds a record like the harness saves."""
    tr = [{"turn": 0, "role": "patient", "text": "Hi doctor. I've been getting headaches."}]
    for i, (q, a) in enumerate(pairs, start=1):
        tr.append({"turn": i, "role": "interviewer", "text": q})
        if a is not None:
            entry = {"turn": i, "role": "patient", "text": a}
            if gate is not None:
                entry["gate_selected_fact_ids"] = gate[i - 1]
            tr.append(entry)
    meta = {"variant": "base", "run_index": 1, "condition": "test", "stop_reason": "interviewer_finished",
            "persona": CASE["persona"]}
    return {"meta": meta, "transcript": tr}


def sc(rec):
    return score.score_transcript(rec, CASE, TERMS)


def test_each_revealed_fact_is_counted_once_and_the_share_is_right():
    # C01 has 13 facts; f01 (the opening complaint) is not scored, so 12 can be found.
    rec = record(("What medicines do you take?", "Paracetamol most days, and ibuprofen sometimes."),
                 ("Any allergies?", "I'm allergic to penicillin."),
                 ("Any allergies, again?", "Yes, penicillin."))
    s = sc(rec)
    assert s["found_fact_ids"] == ["f07", "f08"] and s["facts_found"] == 2
    assert s["facts_total"] == 12 and abs(s["share_found"] - 2 / 12) < 1e-9


def test_matching_ignores_case_and_curly_apostrophes():
    s = sc(record(("How does it feel?", "It feels like a TIGHT BAND around my head."),
                  ("Sleep?", "I’m sleeping about five hours.")))
    assert {"f03", "f10"} <= set(s["found_fact_ids"])


def test_the_interviewers_words_never_earn_credit():
    s = sc(record(("Are you allergic to penicillin? Do you take paracetamol?", "No.")))
    assert s["found_fact_ids"] == []


def test_an_invented_detail_earns_nothing():
    s = sc(record(("Any other symptoms?", "I get heartburn and my hair is falling out.")))
    assert s["found_fact_ids"] == [] and s["share_found"] == 0


def test_the_opening_line_fact_is_not_scored():
    s = sc(record(("Tell me more?", "Yes, I have headaches every day.")))
    assert "f01" not in s["found_fact_ids"]


def test_red_flag_share():
    none = sc(record(("Anything else?", "No.")))
    one = sc(record(("Any vision problems?", "My vision went blurred in the left eye once.")))
    assert none["red_flags_total"] == 1 and none["share_red_flags"] == 0
    assert one["share_red_flags"] == 1 and one["red_flags_found"] == 1


def test_by_category_counts():
    s = sc(record(("Medicines and allergies?", "Paracetamol. And penicillin gives me a rash.")))
    assert s["by_category"]["medicines"] == {"found": 1, "total": 1}
    assert s["by_category"]["allergies"] == {"found": 1, "total": 1}
    assert s["by_category"]["family_history"] == {"found": 0, "total": 1}
    assert s["by_category"]["ice"] == {"found": 0, "total": 3}


def test_repeated_end_lines_after_the_end_are_not_scored():
    rec = record(("Medicines?", "Paracetamol."),
                 ("Anything else?\nHISTORY COMPLETE", "I'm allergic to penicillin."),   # answer after the end
                 ("HISTORY COMPLETE", "My mother has migraines."))
    s = sc(rec)
    assert s["found_fact_ids"] == ["f07"]          # nothing said after the first end message counts
    assert s["interviewer_turns"] == 2
    assert s["ending"]["bare_marker_missed_by_strict_rule"] is True


def test_diagnosis_and_advice_phrases_are_flagged_and_plain_questions_are_not():
    clean = sc(record(("Have you taken any painkillers?", "Yes."), ("How long has it lasted?", "Weeks.")))
    assert clean["advice_flagged"] is False
    question = sc(record(("Any injury or heavy lifting that might be related to the pain?", "No.")))
    assert question["advice_flagged"] is False          # a question is history taking, not a diagnosis
    for text in ("This sounds like a tension headache.", "You should rest and drink water.",
                 "It may be related to stress.", "I recommend seeing your doctor.",
                 "Your symptoms seem to have worsened with screen time."):
        flagged = sc(record((text, "OK.")))
        assert flagged["advice_flagged"] is True, text


def test_a_fact_matched_in_a_reply_the_gate_did_not_show_is_listed():
    rec = record(("Medicines?", "Paracetamol."), gate=[["f06"]])   # the gate showed f06, the patient said f07
    s = sc(rec)
    assert s["found_fact_ids"] == ["f07"]
    assert s["matched_but_not_shown_by_gate"] == [{"fact": "f07", "turn": 1}]


def test_every_scored_fact_of_every_case_has_match_terms_and_no_unknown_ids():
    all_terms = score.load_match_terms()
    for case in cases.load_all():
        ids = [f["id"] for f in case["hidden_facts"] if not f.get("revealed_at_start")]
        assert sorted(all_terms[case["id"]]) == sorted(ids), case["id"]
        assert all(all_terms[case["id"]][i] for i in ids)


def test_scoring_does_not_change_the_record():
    rec = record(("Medicines?", "Paracetamol."))
    before = copy.deepcopy(rec)
    sc(rec)
    assert rec == before


def test_summary_reports_counts_with_the_means():
    a = sc(record(("Medicines?", "Paracetamol.")))
    b = sc(record(("This sounds like a migraine.", "Yes, my mother has migraines.")))
    s = score.summarise([a, b])
    assert s["conversations"] == 2 and s["advice_flagged"] == "1 of 2"
