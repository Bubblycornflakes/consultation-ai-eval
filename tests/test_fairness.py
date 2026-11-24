import pytest

from src import fairness


def s(case, share, red=1.0, turns=8, advice=False):
    return {"case_id": case, "share_found": share, "share_red_flags": red, "interviewer_turns": turns,
            "advice_flagged": advice}


def test_pairs_are_formed_by_case_and_runs_are_averaged():
    base = [s("A", 0.4), s("A", 0.6), s("B", 0.5)]        # case A has two base runs: mean 0.5
    swap = [s("A", 0.7), s("B", 0.5)]
    c = fairness.compare(base, swap)
    m = c["metrics"]["share_found"]
    assert c["base_runs_per_case"] == {"A": 2, "B": 1}
    assert [(p["case"], p["base"], p["swap"], p["difference"]) for p in m["pairs"]] == [
        ("A", 0.5, 0.7, 0.2), ("B", 0.5, 0.5, 0.0)]
    assert m["mean_difference"] == 0.1
    assert (m["cases_higher_in_swap"], m["cases_lower_in_swap"], m["cases_equal"]) == (1, 0, 1)


def test_mean_difference_is_zero_when_the_changes_cancel():
    c = fairness.compare([s("A", 0.5), s("B", 0.5)], [s("A", 0.7), s("B", 0.3)])
    m = c["metrics"]["share_found"]
    assert m["mean_difference"] == 0 and m["ci95_low"] <= 0 <= m["ci95_high"]


def test_the_interval_collapses_when_every_difference_is_the_same():
    lo, hi = fairness.bootstrap_ci([0.1, 0.1, 0.1, 0.1, 0.1])
    assert abs(lo - 0.1) < 1e-9 and abs(hi - 0.1) < 1e-9


def test_the_interval_is_wide_with_few_cases_and_always_inside_the_data_range():
    diffs = [-0.3, 0.0, 0.1, 0.2, 0.4]
    lo, hi = fairness.bootstrap_ci(diffs)
    assert min(diffs) <= lo < hi <= max(diffs)


def test_bootstrap_is_reproducible_with_a_fixed_seed():
    assert fairness.bootstrap_ci([0.1, -0.2, 0.3]) == fairness.bootstrap_ci([0.1, -0.2, 0.3])


def test_advice_becomes_a_rate_and_turns_are_compared():
    base = [s("A", 0.5, turns=8, advice=False), s("A", 0.5, turns=10, advice=True)]
    swap = [s("A", 0.5, turns=12, advice=True)]
    m = fairness.compare(base, swap)["metrics"]
    assert m["advice_flagged"]["pairs"][0] == {"case": "A", "base": 0.5, "swap": 1.0, "difference": 0.5}
    assert m["interviewer_turns"]["pairs"][0]["difference"] == 3.0


def test_mismatched_cases_are_refused():
    with pytest.raises(ValueError):
        fairness.compare([s("A", 0.5)], [s("B", 0.5)])
