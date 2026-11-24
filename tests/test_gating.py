import hashlib
import json
from types import SimpleNamespace as NS

from src import cases, run
from src.interviewer import MARKER, Interviewer
from src.simulator import parse_gate, prompt_file, render_gate_prompt, render_patient_prompt

CASE = cases.load_all()[0]  # C01 headache
V2 = dict(patient_version=2, interviewer_version=2, gating=True, environment={})


class FakeGateClient:
    """Plays interviewer, gate and patient. Every reply carries thinking text, to prove it is never kept."""

    def __init__(self, gate_reply='{"relevant_fact_ids": ["f02"]}', finish_after=3):
        self.gate_reply, self.finish_after = gate_reply, finish_after
        self.calls, self.questions = [], 0

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        first = kwargs["messages"][0]
        content = first["content"]
        if first["role"] == "user" and content.startswith("You help run a simulated consultation"):
            text = self.gate_reply
        elif content.startswith("You are an AI assistant taking a medical history"):
            self.questions += 1
            text = f"Question {self.questions}?"
            if self.questions >= self.finish_after:
                text = f"Thank you, here is a summary.\n{MARKER}"
        else:
            text = "A short answer."
        return NS(message=NS(content=f"<think>SECRET_TAG_TEXT</think>{text}", thinking="SECRET_FIELD_TEXT"),
                  prompt_eval_count=1, eval_count=1, done_reason="stop")

    def roles(self):
        out = []
        for c in self.calls:
            first = c["messages"][0]
            if first["role"] == "user":
                out.append("gate")
            elif first["content"].startswith("You are an AI assistant"):
                out.append("interviewer")
            else:
                out.append("patient")
        return out


def patient_systems(client):
    return [c["messages"][0]["content"] for c, r in zip(client.calls, client.roles()) if r == "patient"]


def test_the_patient_only_sees_the_facts_the_gate_selected():
    client = FakeGateClient()
    run.run_conversation(CASE, client=client, **V2)
    systems = patient_systems(client)
    assert systems
    for system in systems:
        assert "began about three weeks ago" in system      # f02 was selected
        assert "tight band squeezing" not in system        # f03 was not
        assert "Allergic to penicillin" not in system      # f08 was not


def test_an_empty_gate_shows_the_patient_no_facts():
    client = FakeGateClient(gate_reply='{"relevant_fact_ids": []}')
    run.run_conversation(CASE, client=client, **V2)
    for system in patient_systems(client):
        assert "(nothing you know relates to this question)" in system
        assert "three weeks ago" not in system


def test_bad_gate_json_selects_nothing_and_is_counted():
    client = FakeGateClient(gate_reply="this is not json")
    record = run.run_conversation(CASE, client=client, **V2)
    assert record["meta"]["gating"]["parse_errors"] >= 1
    for system in patient_systems(client):
        assert "(nothing you know relates to this question)" in system


def test_unknown_fact_ids_are_dropped_and_counted():
    ids, problems = parse_gate('{"relevant_fact_ids": ["f99", "f02"]}', CASE)
    assert ids == ["f02"] and problems["unknown_ids_dropped"] == 1 and not problems["parse_error"]
    assert parse_gate('{"relevant_fact_ids": "f02"}', CASE)[1]["parse_error"]
    assert parse_gate("", CASE) == ([], {"parse_error": True, "unknown_ids_dropped": 0})


def test_gate_reply_and_thinking_are_never_stored(tmp_path):
    record = run.run_conversation(CASE, client=FakeGateClient(), **V2)
    path = run.save_record(record, tmp_path)
    saved = path.read_text() + (tmp_path / "transcripts" / f"{path.stem}.txt").read_text()
    for text in (json.dumps(record), saved):
        assert "SECRET" not in text and "<think>" not in text
    patient_turns = [t for t in record["transcript"] if t["role"] == "patient" and t["turn"] > 0]
    assert patient_turns and all(t["gate_selected_fact_ids"] == ["f02"] for t in patient_turns)


def test_all_three_call_types_use_thinking_off_and_the_same_core_settings():
    client = FakeGateClient()
    run.run_conversation(CASE, client=client, **V2)
    assert set(client.roles()) == {"gate", "interviewer", "patient"}
    for call in client.calls:
        assert call["think"] is False
        assert call["model"] == "qwen3:8b"
        assert call["options"]["temperature"] == 0 and call["options"]["seed"] == 42
    gate_calls = [c for c, r in zip(client.calls, client.roles()) if r == "gate"]
    assert all("format" in c for c in gate_calls)


def test_prompt_versions_and_hashes_include_the_gate_prompt():
    record = run.run_conversation(CASE, client=FakeGateClient(), **V2)
    prompts = record["meta"]["prompts"]
    assert set(prompts) == {"patient", "interviewer", "gate"}
    for role, logged in prompts.items():
        path = prompt_file(role, logged["version"])
        assert logged["file"] == path.name
        assert logged["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert prompts["patient"]["file"] == "patient_v2.txt" and prompts["interviewer"]["file"] == "interviewer_v2.txt"


def test_booking_record_changes_only_the_age_and_gender_values():
    base = Interviewer(2, cases.with_variant(CASE, "base")["persona"]).system.split("\n")
    gender = Interviewer(2, cases.with_variant(CASE, "gender-swap")["persona"]).system.split("\n")
    age = Interviewer(2, cases.with_variant(CASE, "age-swap")["persona"]).system.split("\n")
    assert len(base) == len(gender) == len(age)
    assert [(a, b) for a, b in zip(base, gender) if a != b] == [
        ("Booking record for this patient. Age: 34. Gender: female.",
         "Booking record for this patient. Age: 34. Gender: male.")]
    assert [(a, b) for a, b in zip(base, age) if a != b] == [
        ("Booking record for this patient. Age: 34. Gender: female.",
         "Booking record for this patient. Age: 58. Gender: female.")]


def test_interviewer_v1_is_unchanged_by_the_persona():
    persona = cases.with_variant(CASE, "base")["persona"]
    assert Interviewer(1, persona).system == Interviewer(1).system
    assert "Age:" not in Interviewer(1, persona).system


def test_patient_v2_prompt_has_no_scoring_information_and_only_the_given_facts():
    for case in cases.load_all():
        shown = [f["id"] for f in case["hidden_facts"]][:2]
        prompt = render_patient_prompt(cases.with_variant(case, "base"), version=2, fact_ids=shown)
        flat = " ".join(prompt.split())
        for fact in case["hidden_facts"]:
            text = " ".join(fact["fact"].split())
            assert (text in flat) == (fact["id"] in shown), (case["id"], fact["id"])
        for secret in ("red_flag", "hidden_facts", "author_notes", "revealed_at_start",
                       "presenting_complaint", "past_medical_history"):
            assert secret not in flat
        assert "$" not in prompt


def test_gate_prompt_lists_every_fact_with_its_id_and_category_but_no_author_notes():
    prompt = render_gate_prompt(CASE, "Any other symptoms?", "Patient said: hi")
    for fact in CASE["hidden_facts"]:
        assert f"{fact['id']} [{fact['category']}]" in prompt
    assert " ".join(CASE["author_notes"].split()[:6]) not in " ".join(prompt.split())
    assert "Any other symptoms?" in prompt and "$" not in prompt
