import shutil

from src import cases


def make_dir(tmp_path):
    for name in ("TEMPLATE.yaml", "match_terms.yaml", "C01-headache.yaml"):
        shutil.copy(cases.CASES_DIR / name, tmp_path / name)
    return tmp_path


def test_the_real_cases_pass_the_check():
    assert cases.check_all() == []


def test_new_case_takes_the_next_number_and_fills_in_the_id(tmp_path):
    d = make_dir(tmp_path)
    path = cases.new_case("Back pain 2!", d)
    assert path.name == "C02-back-pain-2.yaml"
    assert "id: C02-back-pain-2" in path.read_text()
    assert cases.new_case("another", d).name == "C03-another.yaml"


def test_a_fresh_scaffold_is_reported_as_unfinished_not_accepted(tmp_path):
    d = make_dir(tmp_path)
    cases.new_case("draft", d)
    problems = " | ".join(cases.check_all(d))
    assert "C02-draft.yaml" in problems and "no fact in category" in problems


def test_missing_and_unknown_match_terms_are_reported(tmp_path):
    import yaml

    d = make_dir(tmp_path)
    terms = yaml.safe_load((d / "match_terms.yaml").read_text())
    del terms["C01-headache"]["f07"]
    terms["C01-headache"]["f99"] = ["x"]
    (d / "match_terms.yaml").write_text(yaml.safe_dump(terms))
    problems = " | ".join(cases.check_all(d))
    assert "no match terms for f07" in problems and "unknown fact f99" in problems


def test_an_empty_name_is_refused(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        cases.new_case("!!!", make_dir(tmp_path))
