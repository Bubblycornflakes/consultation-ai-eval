import copy

import pytest

from src import cases


def test_all_cases_load_and_validate():
    loaded = cases.load_all()
    assert [c["id"] for c in loaded] == sorted(c["id"] for c in loaded)
    assert len(loaded) >= 5


def test_every_case_covers_every_category_and_has_a_red_flag():
    for c in cases.load_all():
        present = {f["category"] for f in c["hidden_facts"]}
        assert present == set(cases.CATEGORIES), c["id"]
        assert c["red_flags"], c["id"]


def test_variant_changes_exactly_one_thing():
    for c in cases.load_all():
        base = cases.with_variant(c, "base")["persona"]
        for v in c["swap_variants"]:
            swapped = cases.with_variant(c, v["id"])["persona"]
            diff = [k for k in base if base[k] != swapped[k]]
            assert diff == [v["change"]], (c["id"], v["id"], diff)


def test_variant_does_not_modify_the_original_case():
    c = cases.load_all()[0]
    before = copy.deepcopy(c)
    cases.with_variant(c, "gender-swap")
    assert c == before


def test_unknown_variant_raises():
    with pytest.raises(KeyError):
        cases.with_variant(cases.load_all()[0], "height-swap")


def test_validate_catches_problems():
    good = cases.load_all()[0]
    bad = copy.deepcopy(good)
    bad["hidden_facts"][1]["category"] = "made_up"
    bad["red_flags"] = ["f99"]
    bad["swap_variants"][0]["persona"] = {"gender": good["persona"]["gender"]}  # changes nothing
    problems = " | ".join(cases.validate(bad))
    assert "unknown category" in problems
    assert "f99" in problems
    assert "must change only" in problems


def test_template_is_not_loaded_as_a_case():
    assert all(not c["id"].startswith("C00") for c in cases.load_all())
