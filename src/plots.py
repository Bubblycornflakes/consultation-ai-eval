"""Charts for the README, drawn from the saved results (no number is typed by hand).

    python -m src.plots        # writes docs/*.png
"""
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src import report  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
V1, V2 = "#4C78A8", "#F58518"          # colour-blind-safe pair
CATEGORY_LABELS = {
    "onset_duration": "Onset and duration", "severity_character": "Severity and character",
    "associated_symptoms": "Associated symptoms", "red_flag_symptoms": "Warning-sign symptoms",
    "past_medical_history": "Past medical history", "medicines": "Medicines", "allergies": "Allergies",
    "family_history": "Family history", "social_history": "Social history", "ice": "Ideas, concerns, hopes",
}


def _style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(length=0)


def counts_chart(data: dict, out: Path) -> Path:
    v1, v2 = data["v1"], data["v2"]
    h = v2["hand"]
    n1, n2 = v1["conversations"], v2["conversations"]
    rows = [  # label, v1 count, v2 count
        ("Patient leaks a fact (clear)", v1["clear_leaks"], h["leak_clear"]),
        ("Patient leaks a fact (clear or borderline)", v1["clear_leaks"] + v1["borderline_leaks"], h["leak_clear"] + h["leak_borderline"]),
        ("Patient invents or contradicts a fact", v1["invention_or_contradiction"], h["invention"]),
        ("Interviewer advice or diagnosis (clear or borderline)", v1["advice_hand"],
         h["interviewer_diagnosis_or_advice_clear"] + h["interviewer_diagnosis_or_advice_borderline"]),
        ("Final message contains a question", v1["final_question"], v2["final_question"]),
    ]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    ys = list(range(len(rows)))[::-1]
    for y, (label, a, b) in zip(ys, rows):
        ax.barh(y + 0.19, 100 * a / n1, height=0.36, color=V1, label="v1" if y == ys[0] else None)
        ax.barh(y - 0.19, 100 * b / n2, height=0.36, color=V2, label="v2" if y == ys[0] else None)
        ax.text(100 * a / n1 + 1.2, y + 0.19, f"{a} of {n1}", va="center", fontsize=8.5)
        ax.text(100 * b / n2 + 1.2, y - 0.19, f"{b} of {n2}", va="center", fontsize=8.5)
    ax.set_yticks(ys, [r[0] for r in rows], fontsize=9)
    ax.set_xlim(0, 118)
    ax.set_xlabel("Share of conversations (%)")
    ax.set_title(f"Hand-counted problems\nv1: {n1} conversations.  v2: {n2} conversations, {v2['distinct']} distinct transcripts.",
                 fontsize=10.5, loc="left")
    ax.legend(frameon=False, loc="lower right")
    _style(ax)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def category_means(scores: list[dict]) -> dict[str, float]:
    cats: dict[str, list[float]] = {}
    for s in scores:
        for c, v in s["by_category"].items():
            cats.setdefault(c, []).append(v["found"] / v["total"])
    return {c: statistics.mean(v) for c, v in cats.items()}


def category_chart(data: dict, out: Path) -> Path:
    a, b = category_means(data["v1_scores"]), category_means(data["v2"]["scores"])
    order = [c for c in CATEGORY_LABELS if c in a]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ys = list(range(len(order)))[::-1]
    for y, c in zip(ys, order):
        ax.barh(y + 0.19, 100 * a[c], height=0.36, color=V1, label="v1" if y == ys[0] else None)
        ax.barh(y - 0.19, 100 * b[c], height=0.36, color=V2, label="v2" if y == ys[0] else None)
        ax.text(100 * a[c] + 1, y + 0.19, f"{100 * a[c]:.0f}%", va="center", fontsize=8)
        ax.text(100 * b[c] + 1, y - 0.19, f"{100 * b[c]:.0f}%", va="center", fontsize=8)
    ax.set_yticks(ys, [CATEGORY_LABELS[c] for c in order], fontsize=9)
    ax.set_xlim(0, 112)
    ax.set_xlabel("Mean share of hidden facts the scorer found (%)")
    ax.set_title("Facts found by category, v1 (5 conversations) and v2 (15 conversations)\n"
                 "Not comparable across conditions: the v2 patient reveals less by design.", fontsize=10, loc="left")
    ax.legend(frameon=False, loc="lower right")
    _style(ax)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def swap_chart(data: dict, out: Path) -> Path:
    comps = data["fairness"]["comparisons"]
    metrics = [("share_found", "Share of facts found"), ("share_red_flags", "Share of warning-sign facts found")]
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6), sharey=True)
    for ax, (key, title) in zip(axes, metrics):
        for y, (variant, label, color) in enumerate((("gender-swap", "Gender swap", V1), ("age-swap", "Age swap", V2))):
            m = comps[variant]["metrics"][key]
            ax.errorbar(m["mean_difference"], y, xerr=[[m["mean_difference"] - m["ci95_low"]], [m["ci95_high"] - m["mean_difference"]]],
                        fmt="o", color=color, capsize=4, markersize=7)
            for p in m["pairs"]:   # each case's own difference
                ax.plot(p["difference"], y, marker="|", color=color, alpha=0.45, markersize=11)
        ax.axvline(0, color="#999", lw=1, ls="--")
        ax.set_title(title, fontsize=10, loc="left")
        ax.set_yticks([0, 1], ["Gender swap", "Age swap"])
        ax.set_ylim(-0.6, 1.6)
        ax.set_xlabel("Swap minus base")
        _style(ax)
    fig.suptitle("Age and gender swaps: mean difference with bootstrap interval over 5 cases (small ticks: each case)",
                 fontsize=9.5, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def check_chart(out: Path) -> Path | None:
    """Scorer against hand labels, from results/human_check_agreement.json (written by `human_check agree`)."""
    import json
    f = ROOT / "results" / "human_check_agreement.json"
    if not f.exists():
        return None
    k = json.loads(f.read_text())["facts"]
    parts = [("Both say stated", k["both_yes"], "#2E7D5B"), ("Both say not stated", k["both_no"], "#9AA5B1"),
             ("Scorer says found,\nlabeller says not stated", k["labeller_no_scorer_yes"], V2),
             ("Labeller says stated,\nscorer says not found", k["labeller_yes_scorer_no"], V1)]
    fig, ax = plt.subplots(figsize=(9, 2.9))
    left = 0
    for label, n, c in parts:
        if n:
            ax.barh(0, n, left=left, color=c, height=0.5)
            ax.text(left + n / 2, 0, f"{n}", ha="center", va="center", color="white", fontsize=11, fontweight="bold")
        left += n
    ax.set_xlim(0, k["n"])
    ax.set_yticks([])
    ax.set_xlabel(f"{k['n']} hidden facts across 8 transcripts")
    ax.legend([plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in parts], [p[0].replace("\n", " ") for p in parts],
              frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.5), ncol=2, fontsize=9)
    ax.set_title(f"Scorer against hand labels: {100 * k['percent_agreement']:.0f}% agreement, kappa {k['kappa']:.2f}", fontsize=10.5, loc="left", pad=62)
    _style(ax)
    ax.spines["left"].set_visible(False)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def main(out_dir: Path | None = None) -> list[Path]:
    out_dir = Path(out_dir or ROOT / "docs")
    out_dir.mkdir(exist_ok=True)
    data = report.collect()
    return [counts_chart(data, out_dir / "counts_v1_v2.png"), category_chart(data, out_dir / "facts_by_category.png"),
            swap_chart(data, out_dir / "swap_differences.png"), check_chart(out_dir / "scorer_check.png")]


if __name__ == "__main__":
    for p in filter(None, main()):
        print("wrote", p.relative_to(ROOT))
    sys.exit(0)
