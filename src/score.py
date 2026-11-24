"""Rule-based scoring of one saved conversation.

Per transcript: (a) the share of hidden facts uncovered, overall and by category, (b) the share of
red-flag facts uncovered, (c) whether the interviewer gave a diagnosis or advice (candidate phrases
are flagged; the final label is checked by hand), (d) the number of interviewer turns.

A fact is uncovered only when one of its match terms (cases/match_terms.yaml) appears in a patient
reply after the opening line. Interviewer questions never earn credit. The presenting complaint,
given in the opening line, is not scored. Facts the patient invents do not count: only the
case's own facts have match terms. Transcripts are read under the lenient ending rule (harness v2.1),
so repeated "HISTORY COMPLETE" lines after the end are not scored.

    python -m src.score results/stage2 --label v1
"""
import argparse
import json
import re
import statistics
import sys
from pathlib import Path

import yaml

from src import cases as casemod
from src.endings import ending_report

ROOT = Path(__file__).resolve().parent.parent
TERMS_FILE = casemod.CASES_DIR / "match_terms.yaml"

# Phrases that suggest the interviewer is diagnosing or advising. They only flag candidates;
# the judgement is made by reading the message.
ADVICE_PATTERNS = [
    r"\byou should\b", r"\bi (?:would )?(?:recommend|suggest|advise)\b", r"\bit (?:could|might|may) be\b",
    r"\bsounds like\b", r"\bsuggests?\b", r"\bconsistent with\b", r"\blikely\b",
    r"\b(?:may|might|could) be (?:related|due|caused|linked)\b", r"\bseems? to have\b", r"\bprobably\b",
    r"\bsee (?:a|your|the) (?:doctor|gp)\b", r"\bdiagnos", r"\bthis is (?:likely|probably|just)\b",
    r"\byou (?:may|might|could) (?:have|need)\b", r"\btry (?:taking|to rest|resting)\b",
]
_ADVICE = re.compile("|".join(ADVICE_PATTERNS), re.IGNORECASE)


def _norm(text: str) -> str:
    return text.lower().replace("’", "'").replace("‘", "'")


def load_match_terms(path: Path = TERMS_FILE) -> dict[str, dict[str, list[str]]]:
    raw = yaml.safe_load(Path(path).read_text())
    return {cid: {fid: [_norm(str(t)) for t in terms] for fid, terms in facts.items()} for cid, facts in raw.items()}


def advice_candidates(transcript: list[dict]) -> list[dict]:
    """Interviewer statements that look like a diagnosis or advice. Questions are skipped: asking
    whether something "might be related" is history taking, not a diagnosis."""
    out = []
    for t in transcript:
        if t["role"] != "interviewer":
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", " ".join(t["text"].split())):
            if sentence.endswith("?"):
                continue
            for m in _ADVICE.finditer(sentence):
                out.append({"turn": t["turn"], "phrase": m.group(0), "message": sentence[:200]})
    return out


def score_transcript(record: dict, case: dict, terms: dict[str, list[str]]) -> dict:
    meta = record["meta"]
    ending = ending_report(record["transcript"])
    scored = ending["scored_transcript"]
    facts = [f for f in case["hidden_facts"] if not f.get("revealed_at_start")]
    patient_turns = [t for t in scored if t["role"] == "patient" and t["turn"] >= 1]

    found, first_turn, unshown = {}, {}, []
    for fact in facts:
        for t in patient_turns:
            reply = _norm(t["text"])
            if any(term in reply for term in terms.get(fact["id"], [])):
                found[fact["id"]] = True
                first_turn.setdefault(fact["id"], t["turn"])
                shown = t.get("gate_selected_fact_ids")
                if shown is not None and fact["id"] not in shown:
                    unshown.append({"fact": fact["id"], "turn": t["turn"]})
    ids = [f["id"] for f in facts]
    by_category = {}
    for f in facts:
        c = by_category.setdefault(f["category"], {"found": 0, "total": 0})
        c["total"] += 1
        c["found"] += f["id"] in found
    red = [r for r in case["red_flags"] if r in ids]
    cands = advice_candidates(scored)
    return {
        "case_id": case["id"], "variant": meta["variant"], "run_index": meta["run_index"],
        "condition": meta.get("condition"), "stop_reason": meta["stop_reason"],
        "persona": meta["persona"],
        "facts_total": len(ids), "facts_found": len(found), "share_found": len(found) / len(ids),
        "found_fact_ids": sorted(found), "first_turn_by_fact": first_turn,
        "by_category": by_category,
        "red_flags_total": len(red), "red_flags_found": sum(r in found for r in red),
        "share_red_flags": (sum(r in found for r in red) / len(red)) if red else None,
        "interviewer_turns": sum(1 for t in scored if t["role"] == "interviewer"),
        "advice_flagged": bool(cands), "advice_candidates": cands,
        "ending": {k: v for k, v in ending.items() if k != "scored_transcript"},
        "matched_but_not_shown_by_gate": unshown,
    }


def score_file(path: Path, all_cases: dict | None = None, terms: dict | None = None) -> dict:
    record = json.loads(Path(path).read_text())
    all_cases = all_cases or {c["id"]: c for c in casemod.load_all()}
    terms = terms or load_match_terms()
    cid = record["meta"]["case_id"]
    out = score_transcript(record, all_cases[cid], terms[cid])
    out["file"] = Path(path).name
    return out


def score_dir(directory: Path, glob: str = "C0*.json") -> list[dict]:
    all_cases = {c["id"]: c for c in casemod.load_all()}
    terms = load_match_terms()
    return [score_file(p, all_cases, terms) for p in sorted(Path(directory).glob(glob))]


def summarise(scores: list[dict]) -> dict:
    """Means over conversations, with the counts they come from."""
    n = len(scores)
    red = [s["share_red_flags"] for s in scores if s["share_red_flags"] is not None]
    return {
        "conversations": n,
        "mean_share_facts_found": round(statistics.mean(s["share_found"] for s in scores), 3),
        "mean_share_red_flags_found": round(statistics.mean(red), 3) if red else None,
        "mean_interviewer_turns": round(statistics.mean(s["interviewer_turns"] for s in scores), 2),
        "advice_flagged": f"{sum(s['advice_flagged'] for s in scores)} of {n}",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("directory")
    ap.add_argument("--label", required=True)
    args = ap.parse_args()
    scores = score_dir(ROOT / args.directory)
    out = ROOT / "results" / "scores"
    out.mkdir(exist_ok=True)
    result = {"label": args.label, "source": args.directory, "summary": summarise(scores), "scores": scores}
    (out / f"{args.label}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps(result["summary"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
