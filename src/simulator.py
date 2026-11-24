"""The simulated patient: a language model plays the persona and answers only what it is asked.

Version 1 shows the patient every hidden fact. Version 2 uses fact gating: a separate call first
picks which facts the interviewer's question relates to, and the patient only sees those for that
one answer.
"""
import json
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parent.parent
PROMPT_DIR = ROOT / "prompts"

GATE_SCHEMA = {
    "type": "object",
    "properties": {"relevant_fact_ids": {"type": "array", "items": {"type": "string"}}},
    "required": ["relevant_fact_ids"],
}


def prompt_file(role: str, version: int) -> Path:
    return PROMPT_DIR / f"{role}_v{version}.txt"


def _flat(text: str) -> str:
    return " ".join(text.split())


def render_patient_prompt(case: dict, version: int = 1, fact_ids: list[str] | None = None) -> str:
    """The patient's system prompt. It gets the persona and the facts it may use, never the
    categories, red-flag list or author notes. fact_ids=None shows every fact (version 1)."""
    facts = case["hidden_facts"] if fact_ids is None else [f for f in case["hidden_facts"] if f["id"] in fact_ids]
    block = "\n".join(f"- {_flat(f['fact'])}" for f in facts) or "- (nothing you know relates to this question)"
    persona = case["persona"]
    return Template(prompt_file("patient", version).read_text()).substitute(
        age=persona["age"], gender=persona["gender"], setting=case["setting"],
        style=_flat(persona["communication_style"]), opening_line=_flat(case["opening_line"]), facts=block)


def render_gate_prompt(case: dict, question: str, previous: str, version: int = 1) -> str:
    """The gating prompt: every fact with its id and category, the previous exchange and the question."""
    facts = "\n".join(f"{f['id']} [{f['category']}]: {_flat(f['fact'])}" for f in case["hidden_facts"])
    return Template(prompt_file("gate", version).read_text()).substitute(
        facts=facts, previous=previous, question=_flat(question))


def parse_gate(text: str, case: dict) -> tuple[list[str], dict]:
    """Turn the gate's JSON reply into a list of valid fact ids (in case order) plus a problem report."""
    valid = [f["id"] for f in case["hidden_facts"]]
    problems = {"parse_error": False, "unknown_ids_dropped": 0}
    try:
        ids = json.loads(text)["relevant_fact_ids"]
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            raise ValueError("relevant_fact_ids must be a list of strings")
    except (ValueError, KeyError, TypeError):
        problems["parse_error"] = True
        return [], problems
    problems["unknown_ids_dropped"] = sum(1 for i in ids if i not in valid)
    return [i for i in valid if i in ids], problems


class Patient:
    def __init__(self, case: dict, version: int = 1):
        self.case, self.version = case, version
        self.history: list[dict] = []
        self.fact_ids: list[str] | None = None  # None: show every fact

    def show_only(self, fact_ids: list[str]) -> None:
        self.fact_ids = fact_ids

    @property
    def messages(self) -> list[dict]:
        system = render_patient_prompt(self.case, self.version, self.fact_ids)
        return [{"role": "system", "content": system}, *self.history]

    def hear(self, question: str) -> None:
        self.history.append({"role": "user", "content": question})

    def said(self, reply: str) -> None:
        self.history.append({"role": "assistant", "content": reply})
