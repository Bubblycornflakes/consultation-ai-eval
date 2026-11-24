from types import SimpleNamespace as NS

from src import cases, run, system


def test_swap_output_is_parsed():
    out = "vm.swapusage: total = 8192.00M  used = 7639.94M  free = 552.06M  (encrypted)"
    s = system.parse_swap(out)
    assert s["total_mb"] == 8192.0 and s["used_mb"] == 7639.94
    assert abs(s["used_fraction"] - 0.9326) < 0.001
    assert system.parse_swap("nonsense") is None


def test_warning_appears_only_when_swap_is_nearly_full():
    full = system.parse_swap("total = 8192.00M  used = 7639.94M  free = 552.06M")
    ok = system.parse_swap("total = 8192.00M  used = 2000.00M  free = 6192.00M")
    assert "WARNING" in system.memory_warning(full) and "93%" in system.memory_warning(full)
    assert system.memory_warning(ok) is None
    assert system.memory_warning(None) is None


class FakeClient:
    def __init__(self):
        self.calls = 0

    def chat(self, **kwargs):
        self.calls += 1
        first = kwargs["messages"][0]["content"]
        text = f"Thanks.\n[HISTORY COMPLETE]" if first.startswith("You are an AI assistant") else "Ok."
        return NS(message=NS(content=text, thinking=None), prompt_eval_count=1, eval_count=1, done_reason="stop")


def test_skip_existing_does_not_redo_finished_conversations(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    real = run.run_conversation
    case1 = cases.load_all()[0]
    run.save_record(real(case1, client=FakeClient(), environment={}), out)   # C01 run 1 is already done

    calls = []

    def fake(case, variant, run_index, **kw):
        calls.append(case["id"])
        keep = {k: v for k, v in kw.items() if k in ("patient_version", "interviewer_version", "gating", "condition",
                                                     "lenient_end", "max_turns", "slow_seconds")}
        return real(case, variant, run_index, client=FakeClient(), environment={}, **keep)

    monkeypatch.setattr(run, "ROOT", tmp_path)
    monkeypatch.setattr(run, "run_conversation", fake)
    monkeypatch.setattr(run, "environment_meta", lambda client=None: {})
    real_chat = run.llm.chat
    # the warm-up call has no client and must not reach Ollama; calls made by the fake conversation do have one
    monkeypatch.setattr(run.llm, "chat", lambda *a, **k: real_chat(*a, **k) if k.get("client") else {"text": "OK"})
    monkeypatch.setattr(run.system, "swap_status", lambda: None)
    args = NS(cases=["C01", "C02"], variant="base", run_index=1, runs=1, patient_version=1, interviewer_version=1,
              gating=False, condition="t", lenient_end=False, skip_existing=True, out="out", max_turns=20,
              slow_seconds=180)
    assert run.cmd_conversations(args) == 0
    assert calls == ["C02-cough"]                  # C01 was skipped
    assert run.cmd_conversations(args) == 0
    assert calls == ["C02-cough"]                  # everything is done now: nothing is rerun
    args.skip_existing = False
    run.cmd_conversations(args)
    assert calls == ["C02-cough", "C01-headache", "C02-cough"]   # without the flag both are redone
