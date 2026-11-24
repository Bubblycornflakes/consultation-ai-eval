"""Build results/summary.md from the files in results/, so every number in it is copied by a
program from a saved result and none is typed by hand.

    python -m src.report

Hand counts (leaks, inventions, ...) come from the hand-review JSON files, which come from a single review pass
labels; everything else is computed from the saved conversations and scores.
"""
import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / "results"


def _load(rel: str) -> dict:
    return json.loads((R / rel).read_text())


def _runs(directory: str, glob: str = "C0*.json") -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted((R / directory).glob(glob))]


def distinct_transcripts(records: list[dict]) -> int:
    return len({hashlib.sha256(json.dumps([r["meta"]["case_id"], r["meta"]["variant"],
                [(t["role"], t["text"]) for t in r["transcript"]]]).encode()).hexdigest() for r in records})


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def collect() -> dict:
    v1_runs, v2_runs = _runs("stage2"), _runs("stage2_v2")
    s1, s2 = _load("scores/v1.json"), _load("scores/v2.json")
    hand1, hand2 = _load("stage2/leak_review.json"), _load("stage2_v2/hand_review_summary_15.json")
    c1, c2 = hand1["leak_counts"], hand2["counts_out_of_15_conversations"]
    fair = _load("fairness.json")
    d1 = [r["meta"]["duration_seconds"] for r in v1_runs]
    d2 = [r["meta"]["duration_seconds"] for r in v2_runs]
    swap = {v: [r["meta"]["duration_seconds"] for r in _runs(d)] for v, d in
            (("gender-swap", "fairness_gender"), ("age-swap", "fairness_age"))}
    end1 = [s["ending"] for s in s1["scores"]]
    end2 = [s["ending"] for s in s2["scores"]]
    return {
        "v1": {"conversations": len(v1_runs), "distinct": distinct_transcripts(v1_runs),
               "mean_seconds": statistics.mean(d1), "max_seconds": max(d1),
               "clear_leaks": c1["of_which_clear"], "borderline_leaks": c1["of_which_borderline_only"],
               "invention_or_contradiction": hand1["invented_counts"]["conversations_with_at_least_one"],
               "advice_hand": hand1["interviewer"]["diagnosis_or_advice_given"]["conversations"] * 0
                              + hand1["interviewer"]["diagnosis_or_advice_given"]["count"],
               "bare_marker": sum(e["bare_marker_missed_by_strict_rule"] for e in end1),
               "final_question": sum(e["final_message_has_question"] for e in end1),
               "scorer": s1["summary"]},
        "v2": {"conversations": len(v2_runs), "distinct": distinct_transcripts(v2_runs),
               "mean_seconds": statistics.mean(d2), "max_seconds": max(d2),
               "hand": c2, "hand_distinct": hand2["counts_out_of_7_distinct_transcripts"],
               "bare_marker": sum(e["bare_marker_missed_by_strict_rule"] for e in end2),
               "final_question": sum(e["final_message_has_question"] for e in end2),
               "scorer": s2["summary"], "scores": s2["scores"]},
        "v1_scores": s1["scores"],
        "swap_seconds": {v: {"n": len(t), "mean": statistics.mean(t), "max": max(t)} for v, t in swap.items()},
        "fairness": fair,
        "seed_test": _load("seed_test.json"),
        "gate_diagnostic": _load("gate_miss_diagnostic.json")["summary"],
    }


def render(d: dict) -> str:
    v1, v2 = d["v1"], d["v2"]
    n1, n2 = v1["conversations"], v2["conversations"]
    h = v2["hand"]
    rows = [
        ("Conversations / distinct transcripts", f"{n1} / {v1['distinct']}", f"{n2} / {v2['distinct']}"),
        ("Patient leaks a hidden fact, clear", f"{v1['clear_leaks']} of {n1}", f"{h['leak_clear']} of {n2}"),
        ("Patient leaks, borderline", f"{v1['borderline_leaks']} of {n1}", f"{h['leak_borderline']} of {n2}"),
        ("Patient invents or contradicts a fact", f"{v1['invention_or_contradiction']} of {n1}", f"{h['invention']} of {n2}"),
        ("Gate misses a fact the question asked about", "not applicable", f"{h['gate_miss_conversations']} of {n2}"),
        ("Interviewer diagnosis or advice (hand count)", f"{v1['advice_hand']} of {n1}",
         f"{h['interviewer_diagnosis_or_advice_clear']} clear, {h['interviewer_diagnosis_or_advice_borderline']} borderline of {n2}"),
        ("End marker without brackets (strict harness missed it)", f"{v1['bare_marker']} of {n1}", f"{v2['bare_marker']} of {n2}"),
        ("Final message contains a question", f"{v1['final_question']} of {n1}", f"{v2['final_question']} of {n2}"),
        ("Mean time per conversation", f"{v1['mean_seconds']:.1f} s", f"{v2['mean_seconds']:.1f} s (longest {v2['max_seconds']:.1f} s)"),
        ("Scorer: mean share of hidden facts found", _pct(v1["scorer"]["mean_share_facts_found"]), _pct(v2["scorer"]["mean_share_facts_found"])),
        ("Scorer: mean share of warning-sign facts found", _pct(v1["scorer"]["mean_share_red_flags_found"]), _pct(v2["scorer"]["mean_share_red_flags_found"])),
        ("Scorer: mean interviewer turns", f"{v1['scorer']['mean_interviewer_turns']:.1f}", f"{v2['scorer']['mean_interviewer_turns']:.1f}"),
        ("Scorer: advice flagged", v1["scorer"]["advice_flagged"].replace("of", "of"), v2["scorer"]["advice_flagged"]),
    ]
    out = ["# Results summary", "", "Generated by `python -m src.report` from the files in `results/`. Hand counts are one "
           "review-pass labels (`results/stage2/leak_review.json`, `results/stage2_v2/hand_review_summary_15.json`).", "",
           "## v1 and v2 side by side", "", "| | v1 | v2 |", "|---|---|---|"]
    out += [f"| {a} | {b} | {c} |" for a, b, c in rows]
    hd = v2["hand_distinct"]
    out += ["", f"v2 over its {v2['distinct']} distinct transcripts: clear leaks {hd['leak_clear']}, borderline {hd['leak_borderline']}, "
            f"inventions {hd['invention']}, gate misses {hd['gate_miss']}, advice {hd['diagnosis_or_advice_clear']} clear and "
            f"{hd['diagnosis_or_advice_borderline']} borderline.", "", "## Age and gender swaps (descriptive)", "",
            "Swap minus base, per case (5 pairs). Intervals are bootstrap over cases.", "",
            "| Metric | Swap | Mean difference [95% interval] | Cases higher / lower / equal |", "|---|---|---|---|"]
    for variant, comp in d["fairness"]["comparisons"].items():
        for metric, m in comp["metrics"].items():
            out.append(f"| {metric} | {variant} | {m['mean_difference']:+.3f} [{m['ci95_low']:+.3f}, {m['ci95_high']:+.3f}] | "
                       f"{m['cases_higher_in_swap']} / {m['cases_lower_in_swap']} / {m['cases_equal']} |")
    for variant, t in d["swap_seconds"].items():
        out.append(f"\n{variant}: {t['n']} conversations, mean {t['mean']:.1f} s, longest {t['max']:.1f} s.")
    g = d["gate_diagnostic"]
    out += ["", "## Gate misses", "", f"On {g['turns']} turns marked as misses, gate_v1 repeated the miss {g['miss_repeats_with_gate_v1']} times and "
            f"gave the same choice as logged {g['identical_to_logged_selection']} times. With category labels removed it picked the "
            f"missing fact on {g['found_when_categories_removed']} of {g['turns']}.", "", "## Seed test", ""]
    for label, p in d["seed_test"]["prompts"].items():
        parts = ", ".join(f"{k}: {v['distinct_replies']} distinct of {v['runs']}" for k, v in p["groups"].items())
        out.append(f"- {label}: {parts}")
    out.append(f"\nSeed honoured (judged on the open-ended prompt): {d['seed_test']['seed_is_honoured']}.")
    return "\n".join(out) + "\n"


def main() -> int:
    data = collect()
    (R / "summary.md").write_text(render(data))
    print("wrote results/summary.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
