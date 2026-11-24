"""How a conversation ended, read from the saved transcript.

Harness v2.0 only recognised the bracketed marker [HISTORY COMPLETE]. Some interviewers wrote the
words without brackets and then repeated them until the 20-turn cap. Harness v2.1 accepts both.
This module applies either rule to an existing transcript, so older runs can be re-read under the
same rule as newer ones without being rerun.
"""
from src.interviewer import BARE_MARKER, MARKER


def ending_report(transcript: list[dict]) -> dict:
    """Strict and lenient reading of the ending, plus the transcript cut at the lenient end."""
    strict_turn = lenient_turn = None
    for t in transcript:
        if t["role"] != "interviewer":
            continue
        if strict_turn is None and MARKER in t["text"]:
            strict_turn = t["turn"]
        if lenient_turn is None and (MARKER in t["text"] or BARE_MARKER.search(t["text"])):
            lenient_turn = t["turn"]
    cut = lenient_turn
    scored = [t for t in transcript if cut is None or t["turn"] < cut or (t["turn"] == cut and t["role"] == "interviewer")]
    final = next((t for t in transcript if t["role"] == "interviewer" and t["turn"] == cut), None)
    interviewer_turns = sum(1 for t in transcript if t["role"] == "interviewer")
    return {
        "strict_end_turn": strict_turn,
        "lenient_end_turn": lenient_turn,
        "bare_marker_missed_by_strict_rule": strict_turn is None and lenient_turn is not None,
        "ran_on_after_lenient_end": lenient_turn is not None and interviewer_turns > lenient_turn,
        "final_message_has_question": bool(final and "?" in final["text"].replace(MARKER, "")),
        "scored_transcript": scored,
    }
