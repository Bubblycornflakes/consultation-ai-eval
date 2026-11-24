"""Load and check the fictional case files in cases/."""
import copy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = ROOT / "cases"

CATEGORIES = [
    "presenting_complaint", "onset_duration", "severity_character", "associated_symptoms",
    "red_flag_symptoms", "past_medical_history", "medicines", "allergies", "family_history",
    "social_history", "ice",
]
REQUIRED = ["id", "case_version", "title", "setting", "persona", "opening_line", "hidden_facts",
            "red_flags", "swap_variants", "author_notes"]


def validate(case: dict, expected_id: str | None = None) -> list[str]:
    """Return a list of problems; an empty list means the case is well formed."""
    problems = [f"missing key: {k}" for k in REQUIRED if k not in case]
    if problems:
        return problems
    if expected_id and case["id"] != expected_id:
        problems.append(f"id {case['id']!r} does not match file name {expected_id!r}")
    facts = case["hidden_facts"]
    ids = [f.get("id") for f in facts]
    if len(ids) != len(set(ids)):
        problems.append("duplicate fact ids")
    for f in facts:
        if f.get("category") not in CATEGORIES:
            problems.append(f"fact {f.get('id')}: unknown category {f.get('category')!r}")
    present = {f.get("category") for f in facts}
    problems += [f"no fact in category {c}" for c in CATEGORIES if c not in present]
    problems += [f"red flag {r} is not a fact id" for r in case["red_flags"] if r not in ids]
    starters = [f["id"] for f in facts if f.get("revealed_at_start")]
    if starters != [facts[0]["id"]]:
        problems.append("exactly the first fact (the presenting complaint) must be revealed_at_start")
    persona = case["persona"]
    for v in case["swap_variants"]:
        changed = [k for k, val in v["persona"].items() if persona.get(k) != val]
        if changed != [v["change"]] or len(v["persona"]) != 1:
            problems.append(f"variant {v['id']} must change only {v['change']}, changes {changed}")
    return problems


def load_case(path: Path) -> dict:
    path = Path(path)
    case = yaml.safe_load(path.read_text())
    problems = validate(case, expected_id=path.stem)
    if problems:
        raise ValueError(f"{path.name}: " + "; ".join(problems))
    return case


def load_all(directory: Path = CASES_DIR) -> list[dict]:
    """Every real case (C01, C02, ...), not the template, sorted by id."""
    return [load_case(p) for p in sorted(Path(directory).glob("C[0-9]*.yaml"))]


def with_variant(case: dict, variant_id: str = "base") -> dict:
    """A copy of the case with one swap variant applied. 'base' leaves the persona unchanged."""
    out = copy.deepcopy(case)
    out["variant"] = variant_id
    if variant_id == "base":
        return out
    match = [v for v in case["swap_variants"] if v["id"] == variant_id]
    if not match:
        raise KeyError(f"{case['id']} has no variant {variant_id!r}")
    out["persona"].update(match[0]["persona"])
    return out


# ---------- command line: check the cases, or start a new one ----------

import re
import sys


def next_case_number(directory: Path = CASES_DIR) -> int:
    nums = [int(m.group(1)) for p in Path(directory).glob("C[0-9]*.yaml") if (m := re.match(r"C(\d+)-", p.stem))]
    return max(nums, default=0) + 1


def new_case(name: str, directory: Path = CASES_DIR) -> Path:
    """Copy the template to cases/CNN-name.yaml with the id filled in. The copy is not valid until edited."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        raise ValueError("give the case a short name, for example: back-pain")
    case_id = f"C{next_case_number(directory):02d}-{slug}"
    target = Path(directory) / f"{case_id}.yaml"
    text = (Path(directory) / "TEMPLATE.yaml").read_text().replace("id: C00-example", f"id: {case_id}", 1)
    target.write_text(text)
    return target


def check_all(directory: Path = CASES_DIR, terms_file: Path | None = None) -> list[str]:
    """Every problem found in the case files and in the scorer's match terms. Empty list means all good."""
    import yaml

    problems = []
    cases = []
    for path in sorted(Path(directory).glob("C[0-9]*.yaml")):
        try:
            cases.append(yaml.safe_load(path.read_text()))
            problems += [f"{path.name}: {p}" for p in validate(cases[-1], expected_id=path.stem)]
        except Exception as e:  # noqa: BLE001  a broken file is a problem to report, not a crash
            problems.append(f"{path.name}: cannot be read ({e})")
    terms_path = terms_file or Path(directory) / "match_terms.yaml"
    terms = yaml.safe_load(terms_path.read_text()) if terms_path.exists() else {}
    for case in cases:
        if not isinstance(case, dict) or "hidden_facts" not in case:
            continue
        scored = [f["id"] for f in case["hidden_facts"] if not f.get("revealed_at_start")]
        have = terms.get(case["id"], {})
        problems += [f"{case['id']}: no match terms for {fid} (add them to match_terms.yaml)" for fid in scored if not have.get(fid)]
        problems += [f"{case['id']}: match terms for unknown fact {fid}" for fid in have if fid not in scored]
    return problems


def main(argv: list[str]) -> int:
    if argv[:1] == ["new"] and len(argv) == 2:
        path = new_case(argv[1])
        print(f"Created {path.relative_to(ROOT)}. Edit it, add match terms for each fact in cases/match_terms.yaml,"
              " then run: python -m src.cases check")
        return 0
    if argv[:1] == ["check"] or not argv:
        problems = check_all()
        loaded = [load_case(p) for p in sorted(CASES_DIR.glob("C[0-9]*.yaml")) if not check_all_for(p)]
        for c in loaded:
            print(f"{c['id']:<22} {c['persona']['age']:>3} {c['persona']['gender']:<7} "
                  f"{len(c['hidden_facts']):>2} facts, {len(c['red_flags'])} warning sign(s), "
                  f"variants: {', '.join(v['id'] for v in c['swap_variants'])}")
        print("\nAll cases are well formed." if not problems else "\nProblems:\n  " + "\n  ".join(problems))
        return 1 if problems else 0
    print("usage: python -m src.cases check | python -m src.cases new <short-name>")
    return 2


def check_all_for(path: Path) -> list[str]:
    try:
        return validate(__import__("yaml").safe_load(Path(path).read_text()), expected_id=Path(path).stem)
    except Exception as e:  # noqa: BLE001
        return [str(e)]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
