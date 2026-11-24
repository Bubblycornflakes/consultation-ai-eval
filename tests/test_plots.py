from src import plots, report


def test_charts_are_drawn_from_the_results(tmp_path):
    paths = plots.main(tmp_path)
    assert [p.name for p in paths] == ["counts_v1_v2.png", "facts_by_category.png", "swap_differences.png", "scorer_check.png"]
    for p in paths:
        assert p.exists() and p.stat().st_size > 10_000      # a real image, not an empty file
        assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_category_means_are_shares_between_zero_and_one():
    data = report.collect()
    for scores in (data["v1_scores"], data["v2"]["scores"]):
        means = plots.category_means(scores)
        assert means and all(0 <= v <= 1 for v in means.values())
        assert "presenting_complaint" not in means           # the opening-line fact is not scored
