"""Age and gender swap comparison: the same case, with only the patient's age or gender changed.

For each case the swap conversation is compared with the base conversation(s) of that case. The
unit of comparison is the case, so with five cases this is five pairs. Mean differences come with a
bootstrap interval over cases and the pairs themselves are listed. These are descriptive numbers
from a small pilot; they do not show bias in either direction.

    python -m src.fairness
"""
import json
import random
import statistics
import sys
from pathlib import Path

from src import score

ROOT = Path(__file__).resolve().parent.parent
BASE_DIR = "results/stage2_v2"
SWAP_DIRS = {"gender-swap": "results/fairness_gender", "age-swap": "results/fairness_age"}
METRICS = ["share_found", "share_red_flags", "interviewer_turns", "advice_flagged"]
SEED = 2026
RESAMPLES = 10000


def per_case(scores: list[dict]) -> dict[str, dict[str, float]]:
    """Mean of each metric over the runs of each case (advice_flagged becomes a 0 to 1 rate)."""
    grouped: dict[str, list[dict]] = {}
    for s in scores:
        grouped.setdefault(s["case_id"], []).append(s)
    out = {}
    for cid, rows in grouped.items():
        out[cid] = {m: statistics.mean(float(r[m]) for r in rows) for m in METRICS}
        out[cid]["runs"] = len(rows)
    return out


def bootstrap_ci(diffs: list[float], resamples: int = RESAMPLES, seed: int = SEED, level: float = 0.95) -> tuple[float, float]:
    """Percentile bootstrap interval for the mean of the per-case differences."""
    rng = random.Random(seed)
    means = sorted(statistics.mean(rng.choices(diffs, k=len(diffs))) for _ in range(resamples))
    lo = means[int(((1 - level) / 2) * resamples)]
    hi = means[min(resamples - 1, int((1 - (1 - level) / 2) * resamples))]
    return lo, hi


def compare(base: list[dict], swap: list[dict]) -> dict:
    b, s = per_case(base), per_case(swap)
    if set(b) != set(s):
        raise ValueError(f"cases differ: base {sorted(b)} vs swap {sorted(s)}")
    out = {"cases": sorted(b), "base_runs_per_case": {c: b[c]["runs"] for c in sorted(b)},
           "swap_runs_per_case": {c: s[c]["runs"] for c in sorted(s)}, "metrics": {}}
    for m in METRICS:
        diffs = [s[c][m] - b[c][m] for c in sorted(b)]
        lo, hi = bootstrap_ci(diffs)
        out["metrics"][m] = {
            "mean_difference": round(statistics.mean(diffs), 4),
            "ci95_low": round(lo, 4), "ci95_high": round(hi, 4),
            "cases_higher_in_swap": sum(d > 1e-9 for d in diffs),
            "cases_lower_in_swap": sum(d < -1e-9 for d in diffs),
            "cases_equal": sum(abs(d) <= 1e-9 for d in diffs),
            "pairs": [{"case": c, "base": round(b[c][m], 3), "swap": round(s[c][m], 3),
                       "difference": round(s[c][m] - b[c][m], 3)} for c in sorted(b)],
        }
    return out


def run() -> dict:
    base = score.score_dir(ROOT / BASE_DIR)
    result = {"base": BASE_DIR, "resamples": RESAMPLES, "seed": SEED,
              "note": "Unit of comparison is the case (5 pairs). Intervals are bootstrap over cases and are wide. "
                      "Descriptive only; no conclusion about bias.", "comparisons": {}}
    for variant, directory in SWAP_DIRS.items():
        swap = score.score_dir(ROOT / directory, glob=f"C0*__{variant}__run*.json")
        result["comparisons"][variant] = compare(base, swap) | {"swap_source": directory}
    return result


if __name__ == "__main__":
    out = run()
    (ROOT / "results" / "fairness.json").write_text(json.dumps(out, indent=2))
    for variant, comp in out["comparisons"].items():
        print(variant)
        for m, v in comp["metrics"].items():
            print(f"  {m:<18} mean diff {v['mean_difference']:+.3f}  95% CI [{v['ci95_low']:+.3f}, {v['ci95_high']:+.3f}]  "
                  f"higher {v['cases_higher_in_swap']}, lower {v['cases_lower_in_swap']}, equal {v['cases_equal']}")
    sys.exit(0)
