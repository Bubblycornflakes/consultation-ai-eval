"""The model under test: takes a history from the simulated patient."""
import re
from string import Template

from src.simulator import prompt_file

MARKER = "[HISTORY COMPLETE]"
BARE_MARKER = re.compile(r"\bHISTORY COMPLETE\b", re.IGNORECASE)


def load_interviewer_prompt(version: int = 1, persona: dict | None = None) -> str:
    """Version 2 contains a booking record line, filled from the persona's age and gender.
    Version 1 has no placeholders, so the persona changes nothing in it."""
    text = prompt_file("interviewer", version).read_text()
    if persona is None:
        return text
    return Template(text).substitute(age=persona["age"], gender=persona["gender"])


class Interviewer:
    def __init__(self, version: int = 1, persona: dict | None = None):
        self.system = load_interviewer_prompt(version, persona)
        self.messages = [{"role": "system", "content": self.system}]

    def hear(self, patient_text: str) -> None:
        self.messages.append({"role": "user", "content": patient_text})

    def said(self, text: str) -> None:
        self.messages.append({"role": "assistant", "content": text})

    @staticmethod
    def finished(text: str) -> bool:
        """Strict rule (harness v2.0): the exact bracketed marker."""
        return MARKER in text

    @staticmethod
    def finished_lenient(text: str) -> bool:
        """Lenient rule (harness v2.1): the bracketed marker, or the same words without brackets.
        This changes how the harness reads the ending, not what the model is told."""
        return MARKER in text or bool(BARE_MARKER.search(text))
