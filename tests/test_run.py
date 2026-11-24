import hashlib
import json
from types import SimpleNamespace as NS

from src import cases, run
from src.interviewer import MARKER
from src.simulator import prompt_file, render_patient_prompt

CASE = cases.load_all()[0]


class FakeConversationClient:
    """Plays both roles. Replies always carry thinking text, to prove it never reaches a transcript."""

    def __init__(self, finish_after=3):
        self.finish_after, self.calls, self.questions = finish_after, [], 0

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        system = kwargs["messages"][0]["content"]
        if system.startswith("You are an AI assistant taking a medical history"):
            self.questions += 1
            text = f"Question {self.questions}?"
            if self.finish_after and self.questions >= self.finish_after:
                text = f"Thank you, here is a summary.\n{MARKER}"
        else:
            text = "A short answer."
        return NS(message=NS(content=f"<think>SECRET_TAG_TEXT</think>{text}", thinking="SECRET_FIELD_TEXT"),
                  prompt_eval_count=1, eval_count=1, done_reason="stop")


class StepClock:
    def __init__(self, step):
        self.t, self.step = 0.0, step

    def __call__(self):
        self.t += self.step
        return self.t


def test_thinking_never_reaches_the_transcript_or_saved_files(tmp_path):
    record = run.run_conversation(CASE, client=FakeConversationClient(), environment={})
    path = run.save_record(record, tmp_path)
    saved = path.read_text() + (tmp_path / "transcripts" / f"{path.stem}.txt").read_text()
    for text in (json.dumps(record), saved):
        assert "SECRET" not in text
        assert "<think>" not in text
    assert record["meta"]["thinking"]["think_tags_found_in_any_reply"] is True
    assert record["meta"]["stop_reason"] == "interviewer_finished"


def test_both_roles_use_identical_settings_with_thinking_off():
    client = FakeConversationClient()
    run.run_conversation(CASE, client=client, environment={})
    assert len(client.calls) >= 4
    first = client.calls[0]
    for call in client.calls:
        assert call["think"] is False
        assert call["model"] == first["model"]
        assert call["options"] == first["options"]
        assert call["keep_alive"] == first["keep_alive"]


def test_prompt_versions_and_hashes_are_logged():
    record = run.run_conversation(CASE, client=FakeConversationClient(), environment={})
    for role in ("patient", "interviewer"):
        logged = record["meta"]["prompts"][role]
        path = prompt_file(role, logged["version"])
        assert logged["file"] == path.name
        assert logged["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_turn_cap_is_enforced():
    record = run.run_conversation(CASE, client=FakeConversationClient(finish_after=0), environment={}, max_turns=20)
    assert record["meta"]["stop_reason"] == "turn_cap"
    assert record["meta"]["interviewer_turns"] == 20
    assert sum(t["role"] == "patient" for t in record["transcript"]) == 21  # opening line plus 20 answers


def test_a_slow_conversation_stops_itself():
    record = run.run_conversation(CASE, client=FakeConversationClient(finish_after=0), environment={},
                                  slow_seconds=180, clock=StepClock(100))
    assert record["meta"]["stop_reason"] == "stopped_slow"
    assert record["meta"]["interviewer_turns"] < 20


def test_patient_prompt_has_the_facts_but_no_scoring_information():
    for case in cases.load_all():
        for variant in ["base"] + [v["id"] for v in case["swap_variants"]]:
            prompt = render_patient_prompt(cases.with_variant(case, variant))
            flat = " ".join(prompt.split())
            for fact in case["hidden_facts"]:
                assert " ".join(fact["fact"].split()) in flat, (case["id"], fact["id"])
            for secret in ("red_flag", "hidden_facts", "author_notes", "revealed_at_start",
                           "presenting_complaint", "past_medical_history", case["author_notes"].split()[0:6] and
                           " ".join(case["author_notes"].split()[:6])):
                assert secret not in flat, (case["id"], secret)
            assert "$" not in prompt  # every placeholder was filled


def test_gender_swap_changes_only_the_gender_in_the_patient_prompt():
    base = render_patient_prompt(cases.with_variant(CASE, "base")).split("\n")
    swapped = render_patient_prompt(cases.with_variant(CASE, "gender-swap")).split("\n")
    diff = [(a, b) for a, b in zip(base, swapped) if a != b]
    assert len(base) == len(swapped)
    assert diff == [("- Gender: female", "- Gender: male")]
