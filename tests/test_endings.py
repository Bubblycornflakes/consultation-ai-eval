from types import SimpleNamespace as NS

from src import cases, run
from src.endings import ending_report
from src.interviewer import MARKER, Interviewer

CASE = cases.load_all()[0]


def turns(*pairs):
    out = [{"turn": 0, "role": "patient", "text": "Hi."}]
    for i, (q, a) in enumerate(pairs, start=1):
        out.append({"turn": i, "role": "interviewer", "text": q})
        if a is not None:
            out.append({"turn": i, "role": "patient", "text": a})
    return out


def test_strict_and_lenient_rules_differ_only_on_the_bare_marker():
    assert Interviewer.finished(f"Thanks.\n{MARKER}") and Interviewer.finished_lenient(f"Thanks.\n{MARKER}")
    assert not Interviewer.finished("Thanks.\nHISTORY COMPLETE")
    assert Interviewer.finished_lenient("Thanks.\nHISTORY COMPLETE")
    assert Interviewer.finished_lenient("history complete")
    assert not Interviewer.finished_lenient("The history is not yet complete.")


def test_bare_marker_is_missed_by_strict_and_the_run_on_is_cut_for_scoring():
    tr = turns(("Q1?", "A1"), ("Any more?\nHISTORY COMPLETE", "No."), ("HISTORY COMPLETE", "I don't know."))
    rep = ending_report(tr)
    assert rep["strict_end_turn"] is None and rep["lenient_end_turn"] == 2
    assert rep["bare_marker_missed_by_strict_rule"] and rep["ran_on_after_lenient_end"]
    assert rep["final_message_has_question"]
    last = rep["scored_transcript"][-1]
    assert last["role"] == "interviewer" and last["turn"] == 2   # the patient's answer after it is not scored


def test_a_clean_bracketed_ending_is_unchanged():
    tr = turns(("Q1?", "A1"), (f"Thank you, summary.\n{MARKER}", None))
    rep = ending_report(tr)
    assert rep["strict_end_turn"] == rep["lenient_end_turn"] == 2
    assert not rep["bare_marker_missed_by_strict_rule"] and not rep["final_message_has_question"]
    assert rep["scored_transcript"] == tr


def test_no_marker_at_all_keeps_the_whole_transcript():
    tr = turns(("Q1?", "A1"), ("Q2?", "A2"))
    rep = ending_report(tr)
    assert rep["lenient_end_turn"] is None and rep["scored_transcript"] == tr


class BareMarkerClient:
    """Interviewer asks one question then writes the marker without brackets, forever."""

    def __init__(self):
        self.q = 0

    def chat(self, **kwargs):
        first = kwargs["messages"][0]["content"]
        if first.startswith("You are an AI assistant"):
            self.q += 1
            text = "A question?" if self.q == 1 else "HISTORY COMPLETE"
        else:
            text = "An answer."
        return NS(message=NS(content=text, thinking=None), prompt_eval_count=1, eval_count=1, done_reason="stop")


def test_harness_v2_0_runs_to_the_cap_but_v2_1_stops_at_the_bare_marker():
    strict = run.run_conversation(CASE, client=BareMarkerClient(), environment={})
    lenient = run.run_conversation(CASE, client=BareMarkerClient(), environment={}, lenient_end=True)
    assert strict["meta"]["stop_reason"] == "turn_cap" and strict["meta"]["interviewer_turns"] == 20
    assert strict["meta"]["harness"]["version"] == "v2.0"
    assert lenient["meta"]["stop_reason"] == "interviewer_finished" and lenient["meta"]["interviewer_turns"] == 2
    assert lenient["meta"]["harness"] == {**lenient["meta"]["harness"], "version": "v2.1", "lenient_end": True}
    # the model's prompt and settings are identical in both
    assert strict["meta"]["prompts"] == lenient["meta"]["prompts"]
    assert strict["meta"]["settings"] == lenient["meta"]["settings"]
