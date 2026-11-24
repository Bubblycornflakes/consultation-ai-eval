"""One-off diagnostic: why did the gate miss a fact on turns the hand review marked as misses?

Re-runs the gate on those exact questions in two ways: as it was (gate_v1) and with the category
labels removed from the fact list. It does not change any prompt or any result; the output only
says whether the miss repeats and whether hiding the categories could explain it.
"""
import json
import re
import sys

from src import cases as casemod
from src import llm
from src.simulator import GATE_SCHEMA, parse_gate, render_gate_prompt

from src.run import ROOT

# (result file, turn, the fact the gate should have selected), from results/stage2_v2/hand_review_batch1.json
MISSES = [("C03-back-pain__base__run1", 3, "f02"), ("C04-tiredness__base__run1", 2, "f03"),
          ("C04-tiredness__base__run1", 4, "f08"), ("C04-tiredness__base__run1", 5, "f12"),
          ("C04-tiredness__base__run2", 2, "f03"), ("C04-tiredness__base__run2", 4, "f12"),
          ("C04-tiredness__base__run2", 8, "f08")]


def previous_exchange(transcript, turn):
    if turn == 1:
        return f'Patient said: "{transcript[0]["text"]}"'
    q = next(t for t in transcript if t["role"] == "interviewer" and t["turn"] == turn - 1)["text"]
    a = next(t for t in transcript if t["role"] == "patient" and t["turn"] == turn - 1)["text"]
    return f'Interviewer asked: "{q}"\nPatient answered: "{a}"'


def run() -> dict:
    cases = {c["id"]: c for c in casemod.load_all()}
    rows = []
    for name, turn, expected in MISSES:
        rec = json.loads((ROOT / "results/stage2_v2" / f"{name}.json").read_text())
        case = casemod.with_variant(cases[rec["meta"]["case_id"]], "base")
        tr = rec["transcript"]
        question = next(t for t in tr if t["role"] == "interviewer" and t["turn"] == turn)["text"]
        logged = next(t for t in tr if t["role"] == "patient" and t["turn"] == turn)["gate_selected_fact_ids"]
        prompt = render_gate_prompt(case, question, previous_exchange(tr, turn))
        no_cat = re.sub(r"^(f\d+) \[[a-z_]+\]:", r"\1:", prompt, flags=re.MULTILINE)
        row = {"file": name, "turn": turn, "question": question, "should_have_selected": expected,
               "logged_selection": logged}
        for label, p in (("rerun_gate_v1", prompt), ("rerun_without_categories", no_cat)):
            r = llm.chat([{"role": "user", "content": p}], settings=llm.GATE_SETTINGS, format=GATE_SCHEMA)
            ids, _ = parse_gate(r["text"], case)
            row[label] = ids
            row[label + "_includes_expected"] = expected in ids
        rows.append(row)
    summary = {
        "turns": len(rows),
        "miss_repeats_with_gate_v1": sum(not r["rerun_gate_v1_includes_expected"] for r in rows),
        "found_when_categories_removed": sum(r["rerun_without_categories_includes_expected"] for r in rows),
        "identical_to_logged_selection": sum(r["rerun_gate_v1"] == r["logged_selection"] for r in rows),
    }
    return {"summary": summary, "rows": rows}


if __name__ == "__main__":
    out = run()
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "gate_miss_diagnostic.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps(out["summary"], indent=2))
    sys.exit(0)
