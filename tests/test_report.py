from src import report

README = (report.ROOT / "README.md").read_text()
DATA = report.collect()


def test_summary_renders_and_has_every_section():
    text = report.render(DATA)
    for heading in ("v1 and v2 side by side", "Age and gender swaps", "Gate misses", "Seed test"):
        assert heading in text


def test_summary_numbers_come_from_the_saved_results():
    v1, v2 = DATA["v1"], DATA["v2"]
    assert (v1["conversations"], v2["conversations"]) == (5, 15)
    assert v2["distinct"] == 7 and v1["distinct"] == 5          # repeats are identical, so 15 runs are 7 transcripts
    assert v2["hand"]["leak_clear"] == 0 and v1["clear_leaks"] == 2
    assert abs(v1["mean_seconds"] - 22.3) < 0.05 and abs(v2["mean_seconds"] - 35.6) < 0.05


def test_the_readme_quotes_the_generated_numbers():
    """Every headline number in the README table must equal what the report computes."""
    v1, v2, s1, s2 = DATA["v1"], DATA["v2"], DATA["v1"]["scorer"], DATA["v2"]["scorer"]
    expected = [
        f"{v1['mean_seconds']:.1f} s", f"{v2['mean_seconds']:.1f} s (longest {v2['max_seconds']:.1f} s)",
        f"{s1['mean_share_facts_found'] * 100:.0f}%", f"{s2['mean_share_facts_found'] * 100:.0f}%",
        f"{s1['mean_share_red_flags_found'] * 100:.0f}%", f"{s2['mean_share_red_flags_found'] * 100:.0f}%",
        f"{s1['mean_interviewer_turns']:.1f}", f"{s2['mean_interviewer_turns']:.1f}",
        f"{v2['hand']['invention']}", f"{v2['hand']['leak_borderline']}", f"{v2['hand']['gate_miss_conversations']}",
        f"**{v2['distinct']} distinct transcripts**",
    ]
    for token in expected:
        assert token in README, token
    for variant, t in DATA["swap_seconds"].items():
        assert f"{t['mean']:.1f} s" in README, variant


def test_the_readme_quotes_the_swap_differences():
    comps = DATA["fairness"]["comparisons"]
    for variant, key in (("gender-swap", "share_red_flags"), ("age-swap", "interviewer_turns")):
        m = comps[variant]["metrics"][key]
        assert f"{m['mean_difference']:+.1f}" in README or f"{m['mean_difference']:+.2f}" in README, (variant, key)
