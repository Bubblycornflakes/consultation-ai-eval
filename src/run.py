"""Run simulated consultations and save raw transcripts together with every setting used.

    python -m src.run conversations --cases C01 C02 C03                  # v1: base version, one run each
    python -m src.run conversations --patient-version 2 --interviewer-version 2 --gating \
        --runs 3 --condition v2 --out results/stage2_v2                  # v2: gated patient, booking record
    python -m src.run seed-test                                          # does Ollama honour the seed?

A conversation that runs longer than --slow-seconds (default 180) stops the whole run so that
a person can decide whether to continue.
"""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from src import cases as casemod
from src import llm, system
from src.interviewer import Interviewer
from src.simulator import (GATE_SCHEMA, Patient, parse_gate, prompt_file, render_gate_prompt,
                           render_patient_prompt)

ROOT = Path(__file__).resolve().parent.parent
MAX_TURNS = 20
SLOW_SECONDS = 180


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prompt_meta(patient_version: int, interviewer_version: int, gating: bool = False,
                gate_version: int = 1) -> dict:
    out = {}
    roles = [("patient", patient_version), ("interviewer", interviewer_version)]
    if gating:
        roles.append(("gate", gate_version))
    for role, version in roles:
        path = prompt_file(role, version)
        out[role] = {"file": path.name, "version": version, "sha256": _sha256(path)}
    return out


def environment_meta(client=None) -> dict:
    return {
        "model": llm.model_info(client=client),
        "ollama_server_version": llm.server_version(),
        "ollama_python_library": importlib.metadata.version("ollama"),
        "python": platform.python_version(),
        "machine": platform.machine(),
    }


def run_conversation(case: dict, variant_id: str = "base", run_index: int = 1, *, client=None,
                     settings: dict = llm.SETTINGS, patient_version: int = 1,
                     interviewer_version: int = 1, gating: bool = False, gate_version: int = 1,
                     condition: str | None = None, lenient_end: bool = False, max_turns: int = MAX_TURNS,
                     slow_seconds: float = SLOW_SECONDS, environment: dict | None = None,
                     clock=time.perf_counter) -> dict:
    """One full conversation. Returns the record (transcript, calls, meta); nothing is written."""
    case_v = casemod.with_variant(case, variant_id)
    patient = Patient(case_v, patient_version)
    interviewer = Interviewer(interviewer_version, persona=case_v["persona"])

    opening = " ".join(case_v["opening_line"].split())
    transcript = [{"turn": 0, "role": "patient", "text": opening}]
    interviewer.hear(opening)
    calls: list[dict] = []
    gate_log = {"calls": 0, "parse_errors": 0, "unknown_ids_dropped": 0}
    previous = f'Patient said: "{opening}"'
    started = clock()
    stop_reason = "turn_cap"

    def ask(role: str, messages: list[dict], turn: int, *, call_settings: dict = settings, fmt=None) -> dict:
        r = llm.chat(messages, settings=call_settings, client=client, format=fmt)
        calls.append({"turn": turn, "role": role, "seconds": r["seconds"],
                      "prompt_tokens": r["prompt_tokens"], "reply_tokens": r["reply_tokens"],
                      "done_reason": r["done_reason"],
                      "think_tags_in_content": r["think_tags_in_content"],
                      "thinking_field_returned": r["thinking_field_returned"]})
        return r

    for turn in range(1, max_turns + 1):
        q = ask("interviewer", interviewer.messages, turn)
        transcript.append({"turn": turn, "role": "interviewer", "text": q["text"]})
        if not q["text"]:
            stop_reason = "empty_reply"
            break
        interviewer.said(q["text"])
        is_end = Interviewer.finished_lenient if lenient_end else Interviewer.finished
        if is_end(q["text"]):
            stop_reason = "interviewer_finished"
            break
        if clock() - started > slow_seconds:
            stop_reason = "stopped_slow"
            break
        patient.hear(q["text"])

        selected = None
        if gating:
            g = ask("gate", [{"role": "user", "content": render_gate_prompt(case_v, q["text"], previous, gate_version)}],
                    turn, call_settings=llm.GATE_SETTINGS, fmt=GATE_SCHEMA)
            selected, problems = parse_gate(g["text"], case_v)  # only the ids are kept, never the raw reply
            gate_log["calls"] += 1
            gate_log["parse_errors"] += problems["parse_error"]
            gate_log["unknown_ids_dropped"] += problems["unknown_ids_dropped"]
            patient.show_only(selected)

        a = ask("patient", patient.messages, turn)
        entry = {"turn": turn, "role": "patient", "text": a["text"]}
        if gating:
            entry["gate_selected_fact_ids"] = selected
        transcript.append(entry)
        if not a["text"]:
            stop_reason = "empty_reply"
            break
        patient.said(a["text"])
        interviewer.hear(a["text"])
        previous = f'Interviewer asked: "{q["text"]}"\nPatient answered: "{a["text"]}"'
        if clock() - started > slow_seconds:
            stop_reason = "stopped_slow"
            break

    duration = clock() - started
    meta = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "condition": condition,
        "case_id": case["id"],
        "case_version": case["case_version"],
        "variant": variant_id,
        "run_index": run_index,
        "persona": case_v["persona"],
        "settings": {"interviewer": settings, "patient": settings},
        "same_settings_for_both_roles": True,
        "gating": {"enabled": gating, **({"gate_settings": llm.GATE_SETTINGS, **gate_log} if gating else {})},
        "interviewer_sees_age_and_gender": interviewer_version >= 2,
        "harness": {"version": "v2.1" if lenient_end else "v2.0", "lenient_end": lenient_end,
                    "note": "v2.1 (2026-11-24) also accepts HISTORY COMPLETE without brackets as the end; "
                            "the model's prompt is unchanged"},
        "max_interviewer_turns": max_turns,
        "slow_limit_seconds": slow_seconds,
        "prompts": prompt_meta(patient_version, interviewer_version, gating, gate_version),
        "stop_reason": stop_reason,
        "interviewer_turns": sum(1 for t in transcript if t["role"] == "interviewer"),
        "duration_seconds": round(duration, 2),
        "thinking": {
            "think_parameter": settings["think"],
            "think_tags_found_in_any_reply": any(c["think_tags_in_content"] for c in calls),
            "thinking_field_returned_in_any_reply": any(c["thinking_field_returned"] for c in calls),
            "note": "thinking text is removed in src/llm.py and never stored",
        },
        "environment": environment,
    }
    return {"meta": meta, "transcript": transcript, "calls": calls}


def record_name(record: dict) -> str:
    m = record["meta"]
    return f"{m['case_id']}__{m['variant']}__run{m['run_index']}"


def readable(record: dict) -> str:
    m = record["meta"]
    gating = m["gating"]["enabled"]
    head = [
        f"Case {m['case_id']} (version {m['case_version']}), variant {m['variant']}, run {m['run_index']}"
        + (f", condition {m['condition']}" if m.get("condition") else ""),
        f"Patient: {m['persona']['age']} years, {m['persona']['gender']}",
        f"Model: {m['settings']['interviewer']['model']}, thinking off, "
        f"temperature {m['settings']['interviewer']['options']['temperature']}, "
        f"seed {m['settings']['interviewer']['options']['seed']}",
        "Prompts: " + ", ".join(p["file"] for p in m["prompts"].values())
        + (" (fact gating on)" if gating else ""),
        f"Stopped because: {m['stop_reason']}; {m['interviewer_turns']} interviewer turns; "
        f"{m['duration_seconds']} s",
        "",
    ]
    body = []
    for t in record["transcript"]:
        who = "PATIENT    " if t["role"] == "patient" else "INTERVIEWER"
        body.append(f"[{t['turn']:>2}] {who}: {t['text']}")
        if t.get("gate_selected_fact_ids") is not None:
            shown = ", ".join(t["gate_selected_fact_ids"]) or "none"
            body.append(f"      (facts shown to the patient for this answer: {shown})")
    return "\n".join(head + body) + "\n"


def save_record(record: dict, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    (out_dir / "transcripts").mkdir(parents=True, exist_ok=True)
    name = record_name(record)
    path = out_dir / f"{name}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
    (out_dir / "transcripts" / f"{name}.txt").write_text(readable(record))
    return path


def cmd_conversations(args) -> int:
    all_cases = casemod.load_all()
    chosen = [c for c in all_cases if not args.cases or any(c["id"].startswith(p) for p in args.cases)]
    if not chosen:
        sys.exit("No matching cases.")
    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    environment = environment_meta()
    if warning := system.memory_warning(system.swap_status()):
        print(warning)

    t0 = time.perf_counter()  # load the model once so load time is not counted in conversation 1
    llm.chat([{"role": "user", "content": "Say OK."}])
    warmup = round(time.perf_counter() - t0, 2)
    print(f"model ready (warm-up {warmup} s)")

    summary, stopped = [], False
    for run_index in range(args.run_index, args.run_index + args.runs):
        for case in chosen:
            existing = out_dir / f"{case['id']}__{args.variant}__run{run_index}.json"
            if args.skip_existing and existing.exists():
                old = json.loads(existing.read_text())["meta"]
                if old["stop_reason"] != "stopped_slow":
                    print(f"{case['id']:<20} run {run_index}  already done ({old['stop_reason']}), skipped")
                    continue
            record = run_conversation(
                case, args.variant, run_index, environment=environment, max_turns=args.max_turns,
                slow_seconds=args.slow_seconds, patient_version=args.patient_version,
                interviewer_version=args.interviewer_version, gating=args.gating, condition=args.condition,
                lenient_end=args.lenient_end)
            path = save_record(record, out_dir)
            m = record["meta"]
            transcript_hash = hashlib.sha256(json.dumps(
                [(t["role"], t["text"]) for t in record["transcript"]]).encode()).hexdigest()[:12]
            summary.append({"file": path.name, "case_id": m["case_id"], "run_index": run_index,
                            "stop_reason": m["stop_reason"], "interviewer_turns": m["interviewer_turns"],
                            "duration_seconds": m["duration_seconds"], "transcript_hash": transcript_hash})
            print(f"{case['id']:<20} run {run_index}  {m['stop_reason']:<20} turns={m['interviewer_turns']:>2} "
                  f"time={m['duration_seconds']:>6} s")
            if m["stop_reason"] == "stopped_slow":
                print(f"STOPPED: this conversation took more than {args.slow_seconds} s. Not continuing.")
                stopped = True
                break
        if stopped:
            break
    if not summary:
        print("Nothing to run: every requested conversation already has a result.")
        return 0
    repeats = {}
    for s in summary:
        repeats.setdefault(s["case_id"], []).append(s["transcript_hash"])
    (out_dir / "run_meta.json").write_text(json.dumps(
        {"condition": args.condition, "environment": environment, "warmup_seconds": warmup,
         "conversations": summary,
         "repeats_per_case": {k: {"runs": len(v), "distinct_transcripts": len(set(v))} for k, v in repeats.items()}},
        indent=2))
    return 3 if stopped else 0


def cmd_seed_test(args) -> int:
    """Same prompt several times: is the output repeatable, and does the seed change it?"""
    case = casemod.with_variant(casemod.load_all()[0], "base")
    prompts = {
        # the kind of reply the patient gives: short and strongly determined, so little can vary
        "patient-style question": [
            {"role": "system", "content": render_patient_prompt(case)},
            {"role": "user", "content": "When did the headaches start, and how often do you get them?"}],
        # an open-ended prompt where sampling has room to vary, so a seed effect would be visible
        "open-ended prompt": [{"role": "user", "content": "Write a four-line poem about a kettle."}],
    }

    def replies(messages, temperature: float, seeds: list[int]) -> list[str]:
        out = []
        for seed in seeds:
            s = {**llm.SETTINGS, "options": {**llm.SETTINGS["options"], "temperature": temperature, "seed": seed}}
            out.append(llm.chat(messages, settings=s)["text"])
        return out

    result = {"model": llm.SETTINGS["model"], "environment": environment_meta(), "prompts": {}}
    for label, messages in prompts.items():
        groups = {
            "temperature 0, seed 42, run 3 times": replies(messages, 0, [42, 42, 42]),
            "temperature 1.0, seed 42, run 3 times": replies(messages, 1.0, [42, 42, 42]),
            "temperature 1.0, seeds 1 to 4": replies(messages, 1.0, [1, 2, 3, 4]),
        }
        g = [{"distinct_replies": len(set(v)), "runs": len(v), "replies": v} for v in groups.values()]
        result["prompts"][label] = {
            "groups": dict(zip(groups, g)),
            "temperature_0_repeatable": g[0]["distinct_replies"] == 1,
            "same_seed_repeatable_at_temperature_1": g[1]["distinct_replies"] == 1,
            "different_seeds_give_different_replies": g[2]["distinct_replies"] > 1,
        }
        print(f"\n{label}")
        for k, v in result["prompts"][label]["groups"].items():
            print(f"  {k}: {v['distinct_replies']} distinct of {v['runs']}")
    open_ended = result["prompts"]["open-ended prompt"]
    result["seed_is_honoured"] = (open_ended["same_seed_repeatable_at_temperature_1"]
                                  and open_ended["different_seeds_give_different_replies"])
    (ROOT / "results" / "seed_test.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print("\nseed honoured (judged on the open-ended prompt):", result["seed_is_honoured"])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("conversations")
    c.add_argument("--cases", nargs="*", default=[], help="case id prefixes, e.g. C01 C02; default all")
    c.add_argument("--variant", default="base", help="base, gender-swap or age-swap")
    c.add_argument("--run-index", type=int, default=1, help="first run number")
    c.add_argument("--runs", type=int, default=1, help="how many runs of each case")
    c.add_argument("--patient-version", type=int, default=1)
    c.add_argument("--interviewer-version", type=int, default=1)
    c.add_argument("--gating", action="store_true", help="fact gating: the patient sees only the facts the question relates to")
    c.add_argument("--condition", default=None, help="label stored in every record, e.g. v1 or v2")
    c.add_argument("--skip-existing", action="store_true", help="do not redo a conversation that already has a result")
    c.add_argument("--lenient-end", action="store_true", help="harness v2.1: accept HISTORY COMPLETE without brackets")
    c.add_argument("--out", default="results/stage2")
    c.add_argument("--max-turns", type=int, default=MAX_TURNS)
    c.add_argument("--slow-seconds", type=float, default=SLOW_SECONDS)
    c.set_defaults(fn=cmd_conversations)
    s = sub.add_parser("seed-test")
    s.set_defaults(fn=cmd_seed_test)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
