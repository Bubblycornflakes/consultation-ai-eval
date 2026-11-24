"""Human check of the automatic scorer.

    python -m src.human_check build      # pick transcripts, write blind label sheets and a label template
    python -m src.human_check serve      # open the labelling page (saves to human_check/labels_human.yaml)
    python -m src.human_check agree      # compare the labeller's answers with the scorer
    python -m src.human_check recheck    # second-look page for the facts where the first labels and the scorer differed
    python -m src.human_check merge      # apply the second-look answers on top of the first labels (labels_final.yaml)

The labeller reads each transcript and says (a) which hidden facts the PATIENT actually stated and
(b) whether the INTERVIEWER gave a diagnosis or advice. The sheets are blind: they show no condition
(v1 or v2), no file name, no gate information and no automatic score. The key that links a sheet to
its result file is in human_check/key.json and is only used by `agree`.
"""
import hashlib
import json
import random
import sys
from pathlib import Path

import yaml

from src import cases as casemod
from src import score
from src.endings import ending_report

ROOT = Path(__file__).resolve().parent.parent
HC = ROOT / "human_check"
SOURCES = {"v1": "results/stage2", "v2": "results/stage2_v2"}
SEED = 2026


def pool() -> list[dict]:
    """Every complete, distinct transcript in the v1 and v2 results (identical repeats counted once)."""
    seen, out = set(), []
    for label, directory in SOURCES.items():
        for path in sorted((ROOT / directory).glob("C0*.json")):
            rec = json.loads(path.read_text())
            end = ending_report(rec["transcript"])
            if rec["meta"]["stop_reason"] in ("stopped_slow", "empty_reply"):
                continue
            if end["lenient_end_turn"] is None and rec["meta"]["stop_reason"] != "interviewer_finished":
                continue
            text = [(t["role"], t["text"]) for t in end["scored_transcript"]]
            digest = hashlib.sha256(json.dumps([rec["meta"]["case_id"], label, text]).encode()).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            out.append({"label": label, "path": str(path.relative_to(ROOT)), "case_id": rec["meta"]["case_id"]})
    return out


def pick(candidates: list[dict], n: int = 8, seed: int = SEED) -> list[dict]:
    """One transcript per case first, then random fill, in a seeded random order."""
    rng = random.Random(seed)
    shuffled = candidates[:]
    rng.shuffle(shuffled)
    chosen, used = [], set()
    for c in shuffled:
        if c["case_id"] not in used:
            chosen.append(c)
            used.add(c["case_id"])
    for c in shuffled:
        if len(chosen) >= n:
            break
        if c not in chosen:
            chosen.append(c)
    rng.shuffle(chosen)
    return chosen[:n]


def sheet_text(sid: str, record: dict, case: dict) -> str:
    end = ending_report(record["transcript"])
    lines = [f"TRANSCRIPT {sid}", "", "Read the conversation, then answer the two questions at the bottom.", ""]
    for t in end["scored_transcript"]:
        who = "PATIENT    " if t["role"] == "patient" else "INTERVIEWER"
        lines.append(f"{who}: {t['text']}")
    lines += ["", "(The conversation ends with the interviewer's last message above.)", "",
              "QUESTION 1. Which of these facts did the PATIENT state in an answer? A fact counts if the patient",
              "said it, even briefly. It does not count if only the interviewer said it, or if the patient said",
              "something different. Put true or false for each in labels_human.yaml.", ""]
    for f in case["hidden_facts"]:
        if not f.get("revealed_at_start"):
            lines.append(f"  {f['id']}: {' '.join(f['fact'].split())}")
    lines += ["", "QUESTION 2. Did the INTERVIEWER say what the problem is or might be, or give medical advice or a",
              "treatment suggestion? Repeating the patient's own words is not advice. Put true or false in",
              "labels_human.yaml (interviewer_gave_diagnosis_or_advice).", ""]
    return "\n".join(lines)


def template_text(entries: list[tuple[str, dict]]) -> str:
    out = ["# Fill in true or false for every line. Leave nothing as null.",
           "# patient_stated: true if the PATIENT stated that fact in an answer (see the sheet for the fact text).",
           "# interviewer_gave_diagnosis_or_advice: true if the INTERVIEWER diagnosed or advised.", ""]
    for sid, case in entries:
        out.append(f"{sid}:")
        out.append("  patient_stated:")
        for f in case["hidden_facts"]:
            if not f.get("revealed_at_start"):
                out.append(f"    {f['id']}: null   # {' '.join(f['fact'].split())[:70]}")
        out.append("  interviewer_gave_diagnosis_or_advice: null")
        out.append("")
    return "\n".join(out)


def build(n: int = 8) -> dict:
    cands = pool()
    chosen = pick(cands, n)
    cases = {c["id"]: c for c in casemod.load_all()}
    (HC / "sheets").mkdir(parents=True, exist_ok=True)
    key, entries = {}, []
    for i, c in enumerate(chosen, start=1):
        sid = f"T{i}"
        rec = json.loads((ROOT / c["path"]).read_text())
        (HC / "sheets" / f"{sid}.txt").write_text(sheet_text(sid, rec, cases[c["case_id"]]))
        key[sid] = c
        entries.append((sid, cases[c["case_id"]]))
    (HC / "key.json").write_text(json.dumps(
        {"note": "Links each blind sheet to its result file. Not for the labeller.", "seed": SEED, "sheets": key}, indent=2))
    (HC / "labels_human.yaml").write_text(template_text(entries))
    return {"candidates": len(cands), "chosen": len(chosen), "sheets": key}


def kappa(pairs: list[tuple[bool, bool]]) -> dict:
    """Cohen's kappa for two yes/no labellers. pairs are (labeller A, labeller B)."""
    n = len(pairs)
    a = sum(x and y for x, y in pairs)
    b = sum(x and not y for x, y in pairs)
    c = sum((not x) and y for x, y in pairs)
    d = sum((not x) and (not y) for x, y in pairs)
    po = (a + d) / n if n else None
    pe = (((a + b) * (a + c)) + ((c + d) * (b + d))) / (n * n) if n else None
    k = None if (n == 0 or pe == 1) else round((po - pe) / (1 - pe), 3)
    return {"n": n, "both_yes": a, "labeller_yes_scorer_no": b, "labeller_no_scorer_yes": c, "both_no": d,
            "percent_agreement": round(po, 3) if po is not None else None, "kappa": k}


def load_labels(path: Path) -> dict:
    return yaml.safe_load(Path(path).read_text()) or {}


def agree(labels_path: Path | None = None) -> dict:
    key = json.loads((HC / "key.json").read_text())["sheets"]
    labels = load_labels(labels_path or HC / "labels_human.yaml")
    all_cases = {c["id"]: c for c in casemod.load_all()}
    terms = score.load_match_terms()
    fact_pairs, advice_pairs, missing, disagreements = [], [], [], []
    for sid, src in key.items():
        lab = labels.get(sid)
        if not lab:
            missing.append(sid)
            continue
        auto = score.score_file(ROOT / src["path"], all_cases, terms)
        for fid, val in (lab.get("patient_stated") or {}).items():
            if val is None:
                missing.append(f"{sid}.{fid}")
                continue
            pair = (bool(val), fid in auto["found_fact_ids"])
            fact_pairs.append(pair)
            if pair[0] != pair[1]:
                disagreements.append({"sheet": sid, "fact": fid, "labeller": pair[0], "scorer": pair[1]})
        adv = lab.get("interviewer_gave_diagnosis_or_advice")
        if adv is None:
            missing.append(f"{sid}.advice")
        else:
            advice_pairs.append((bool(adv), auto["advice_flagged"]))
            if bool(adv) != auto["advice_flagged"]:
                disagreements.append({"sheet": sid, "fact": "advice", "labeller": bool(adv), "scorer": auto["advice_flagged"]})
    return {"sheets_in_key": len(key), "unlabelled_or_missing": missing,
            "facts": kappa(fact_pairs), "advice_or_diagnosis": kappa(advice_pairs), "disagreements": disagreements}


# ---------- labelling page: a local web page that saves to labels_human.yaml ----------

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Label transcripts</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{--bg:#fafaf7;--ink:#1c1c1a;--mut:#6b6b66;--line:#dddcd6;--pat:#e8f0fa;--int:#f3efe6;--ok:#1f7a4d;--no:#a33b2f}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--ink:#ecebe6;--mut:#9a9a93;--line:#34332f;--pat:#1d2a3a;--int:#2a271f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,sans-serif}
header{padding:14px 20px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:center;flex-wrap:wrap}
h1{font-size:18px;margin:0}.mut{color:var(--mut);font-size:14px}
nav{display:flex;gap:6px;flex-wrap:wrap}
nav button{border:1px solid var(--line);background:transparent;color:var(--ink);border-radius:8px;padding:6px 12px;cursor:pointer;font:inherit}
nav button.on{background:var(--ink);color:var(--bg)}nav button.done::after{content:" \\2713";color:var(--ok)}
main{display:grid;grid-template-columns:1.2fr 1fr;gap:20px;padding:20px;max-width:1200px;margin:auto}
@media (max-width:860px){main{grid-template-columns:1fr}}
.turn{padding:10px 12px;border-radius:10px;margin-bottom:8px;white-space:pre-wrap}
.turn b{display:block;font-size:12px;letter-spacing:.04em;color:var(--mut);margin-bottom:2px}
.P{background:var(--pat)}.I{background:var(--int)}
.card{border:1px solid var(--line);border-radius:12px;padding:14px 16px;position:sticky;top:12px;align-self:start}
.fact{padding:10px 0;border-top:1px solid var(--line)}.fact:first-of-type{border-top:0}
.fact p{margin:0 0 6px}.fact small{color:var(--mut)}
label{margin-right:14px;cursor:pointer}input{accent-color:var(--ok)}
.bar{height:6px;background:var(--line);border-radius:3px;margin-top:8px}.bar i{display:block;height:100%;background:var(--ok);border-radius:3px}
#st{font-size:14px;color:var(--ok)}
</style></head><body>
<header><h1>Label the transcripts</h1><nav id="nav"></nav><span id="st" class="mut"></span></header>
<main><section id="chat"></section>
<aside class="card"><div id="q1"></div><div class="fact"><p><b>Did the interviewer diagnose or give advice?</b><br>
<small>Saying what the problem is or might be, or suggesting treatment or what to do. Repeating the patient's own words is not advice.</small></p>
<label><input type="radio" name="adv" value="true"> Yes</label><label><input type="radio" name="adv" value="false"> No</label></div>
<div class="bar"><i id="bar" style="width:0"></i></div><p class="mut" id="prog"></p>
<p><button id="prev">Previous</button> <button id="next">Next</button></p></aside></main>
<script>
let D,L={},cur=0;
const $=s=>document.querySelector(s);
async function init(){D=await (await fetch('/data')).json();L=D.labels||{};D.sheets.forEach(s=>{L[s.id]=L[s.id]||{patient_stated:{},interviewer_gave_diagnosis_or_advice:null}});render()}
function answered(s){const l=L[s.id];return s.facts.every(f=>l.patient_stated[f.id]===true||l.patient_stated[f.id]===false)&&(l.interviewer_gave_diagnosis_or_advice===true||l.interviewer_gave_diagnosis_or_advice===false)}
function render(){const s=D.sheets[cur],l=L[s.id];
$('#nav').innerHTML=D.sheets.map((x,i)=>`<button class="${i==cur?'on':''} ${answered(x)?'done':''}" onclick="go(${i})">${x.id}</button>`).join('');
$('#chat').innerHTML=s.turns.map(t=>`<div class="turn ${t.role=='patient'?'P':'I'}"><b>${t.role.toUpperCase()}</b>${esc(t.text)}</div>`).join('');
$('#q1').innerHTML='<p><b>Which facts did the PATIENT state in an answer?</b><br><small>True if the patient said it, even briefly. False if only the interviewer said it, or the patient said something different.</small></p>'+
s.facts.map(f=>`<div class="fact"><p>${esc(f.text)}</p><label><input type="radio" name="${f.id}" value="true" ${l.patient_stated[f.id]===true?'checked':''}> Said</label><label><input type="radio" name="${f.id}" value="false" ${l.patient_stated[f.id]===false?'checked':''}> Not said</label></div>`).join('');
document.querySelectorAll('input[name=adv]').forEach(r=>{r.checked=String(l.interviewer_gave_diagnosis_or_advice)===r.value});
s.facts.forEach(f=>document.querySelectorAll(`input[name=${f.id}]`).forEach(r=>r.onchange=()=>{l.patient_stated[f.id]=r.value=='true';save()}));
document.querySelectorAll('input[name=adv]').forEach(r=>r.onchange=()=>{l.interviewer_gave_diagnosis_or_advice=r.value=='true';save()});
const n=D.sheets.filter(answered).length;$('#bar').style.width=(100*n/D.sheets.length)+'%';
$('#prog').textContent=n+' of '+D.sheets.length+' transcripts fully answered'+(n==D.sheets.length?'. All done: close this tab and press Ctrl+C in the terminal.':'');
$('#prev').onclick=()=>go(Math.max(0,cur-1));$('#next').onclick=()=>go(Math.min(D.sheets.length-1,cur+1))}
function go(i){cur=i;render();window.scrollTo(0,0)}
function esc(t){return t.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
async function save(){const r=await fetch('/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(L)});$('#st').textContent=r.ok?'Saved':'Could not save';render()}
init();
</script></body></html>"""


def sheet_data(hc_dir: Path | None = None) -> dict:
    """What the labelling page may show: transcripts and fact texts only. Nothing about the condition, the
    result file or the scorer ever leaves this function."""
    hc_dir = hc_dir or HC
    key = json.loads((hc_dir / "key.json").read_text())["sheets"]
    cases = {c["id"]: c for c in casemod.load_all()}
    sheets = []
    for sid, src in key.items():
        rec = json.loads((ROOT / src["path"]).read_text())
        case = cases[src["case_id"]]
        sheets.append({
            "id": sid,
            "turns": [{"role": t["role"], "text": t["text"]} for t in ending_report(rec["transcript"])["scored_transcript"]],
            "facts": [{"id": f["id"], "text": " ".join(f["fact"].split())} for f in case["hidden_facts"]
                      if not f.get("revealed_at_start")],
        })
    labels_file = hc_dir / "labels_human.yaml"
    labels = (yaml.safe_load(labels_file.read_text()) or {}) if labels_file.exists() else {}
    return {"sheets": sheets, "labels": {k: v for k, v in labels.items() if v}}


def save_labels(payload: dict, hc_dir: Path | None = None) -> Path:
    """Validate what the page sent and write labels_human.yaml. Unanswered items stay null."""
    hc_dir = hc_dir or HC
    data = sheet_data(hc_dir)
    allowed = {s["id"]: {f["id"] for f in s["facts"]} for s in data["sheets"]}
    out = {}
    for sid, fact_ids in allowed.items():
        lab = payload.get(sid) or {}
        stated = lab.get("patient_stated") or {}
        unknown = set(stated) - fact_ids
        if unknown:
            raise ValueError(f"{sid}: unknown fact ids {sorted(unknown)}")
        for v in list(stated.values()) + [lab.get("interviewer_gave_diagnosis_or_advice")]:
            if v not in (True, False, None):
                raise ValueError(f"{sid}: answers must be true, false or empty")
        out[sid] = {"patient_stated": {fid: stated.get(fid) for fid in sorted(fact_ids)},
                    "interviewer_gave_diagnosis_or_advice": lab.get("interviewer_gave_diagnosis_or_advice")}
    path = hc_dir / "labels_human.yaml"
    path.write_text("# Saved by the labelling page. true or false for every line; null means not answered yet.\n"
                    + yaml.safe_dump(out, sort_keys=False))
    return path


def make_handler(hc_dir: Path):
    from http.server import BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, kind: str):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path == "/":
                self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            elif self.path == "/data":
                self._send(200, json.dumps(sheet_data(hc_dir)).encode(), "application/json")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):  # noqa: N802
            if self.path != "/save":
                return self._send(404, b"not found", "text/plain")
            n = int(self.headers.get("Content-Length", 0))
            if n > 200_000:
                return self._send(413, b"too large", "text/plain")
            try:
                save_labels(json.loads(self.rfile.read(n)), hc_dir)
            except (ValueError, KeyError, json.JSONDecodeError) as e:
                return self._send(400, str(e).encode(), "text/plain")
            self._send(200, b"saved", "text/plain")

        def log_message(self, *args):  # keep the terminal quiet
            pass

    return Handler


def serve(port: int = 8765, open_browser: bool = True) -> None:
    from http.server import ThreadingHTTPServer

    server = None
    for p in range(port, port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), make_handler(HC))   # this computer only
            break
        except OSError:
            continue
    if server is None:
        sys.exit("Could not open a local port.")
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Labelling page: {url}\nYour answers are saved to human_check/labels_human.yaml as you click.\n"
          "When every transcript shows a tick, press Ctrl+C here.")
    if open_browser:
        import webbrowser

        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped. Your answers are saved.")


# ---------- re-check page: only the facts where the scorer and the first labels differed ----------

RECHECK = HC / "labels_recheck.yaml"
FINAL = HC / "labels_final.yaml"


def recheck_items() -> list[dict]:
    """One item per fact where the scorer and the first labels disagree: the fact, the patient replies
    that contain a scorer match term (with the terms), and the whole conversation to open if needed."""
    key = json.loads((HC / "key.json").read_text())["sheets"]
    labels = load_labels(HC / "labels_human.yaml")
    all_cases = {c["id"]: c for c in casemod.load_all()}
    terms = score.load_match_terms()
    items = []
    for sid, src in key.items():
        rec = json.loads((ROOT / src["path"]).read_text())
        case = all_cases[src["case_id"]]
        auto = score.score_file(ROOT / src["path"], all_cases, terms)
        scored = ending_report(rec["transcript"])["scored_transcript"]
        facts = {f["id"]: f for f in case["hidden_facts"]}
        for fid, val in (labels[sid].get("patient_stated") or {}).items():
            if bool(val) == (fid in auto["found_fact_ids"]):
                continue
            hits = []
            for t in scored:
                if t["role"] != "patient" or t["turn"] < 1:
                    continue
                low = score._norm(t["text"])
                found = [x for x in terms[src["case_id"]].get(fid, []) if x in low]
                if found:
                    hits.append({"turn": t["turn"], "text": t["text"], "terms": found})
            items.append({"key": f"{sid}.{fid}", "sheet": sid, "fact": " ".join(facts[fid]["fact"].split()),
                          "replies": hits, "turns": [{"role": t["role"], "text": t["text"]} for t in scored]})
    return items


def save_recheck(payload: dict) -> Path:
    allowed = {i["key"] for i in recheck_items()}
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"unknown items {sorted(unknown)}")
    for v in payload.values():
        if v not in (True, False, None):
            raise ValueError("answers must be true, false or empty")
    RECHECK.write_text("# Second look at the facts where the scorer and the first labels differed. "
                       "true = the patient stated it. null = not answered yet.\n"
                       + yaml.safe_dump({k: payload.get(k) for k in sorted(allowed)}, sort_keys=False))
    return RECHECK


def merge_final() -> Path:
    """labels_final.yaml = the first labels, with each re-checked answer replacing the original."""
    labels = load_labels(HC / "labels_human.yaml")
    second = yaml.safe_load(RECHECK.read_text()) or {}
    for k, v in second.items():
        if v is None:
            continue
        sid, fid = k.split(".")
        labels[sid]["patient_stated"][fid] = v
    FINAL.write_text("# First labels with the re-checked answers applied. See labels_human.yaml and labels_recheck.yaml.\n"
                     + yaml.safe_dump(labels, sort_keys=False))
    return FINAL


RECHECK_PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Second look</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{--bg:#fafaf7;--ink:#1c1c1a;--mut:#6b6b66;--line:#dddcd6;--hit:#ffe9a8;--ok:#1f7a4d}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--ink:#ecebe6;--mut:#9a9a93;--line:#34332f;--hit:#5a4a14}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,sans-serif}
main{max-width:760px;margin:auto;padding:20px}h1{font-size:20px}.mut{color:var(--mut);font-size:14px}
.item{border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:14px 0}
.fact{font-weight:600}.reply{background:rgba(120,120,120,.12);border-radius:8px;padding:8px 10px;margin:6px 0;white-space:pre-wrap}
mark{background:var(--hit);color:inherit;border-radius:3px}label{margin-right:16px;cursor:pointer}
details{margin-top:8px}.turn{padding:6px 0;white-space:pre-wrap;font-size:14px}.turn b{color:var(--mut)}
.bar{position:sticky;top:0;background:var(--bg);padding:10px 0;border-bottom:1px solid var(--line)}
</style></head><body><main>
<div class="bar"><h1>Second look</h1><span class="mut" id="prog"></span></div>
<p class="mut">For each fact: did the patient state it in any answer? Said means the patient said it, even briefly. Highlighted words are only a pointer to where to look. Your earlier answers stay saved; these replace them only where you answer here.</p>
<div id="list"></div></main>
<script>
let I=[],A={};
const esc=t=>t.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
function mark(text,terms){let h=esc(text);terms.forEach(t=>{const r=new RegExp(t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'ig');h=h.replace(r,m=>'<mark>'+m+'</mark>')});return h}
async function init(){const d=await (await fetch('/recheck-data')).json();I=d.items;A=d.answers||{};render()}
function render(){document.getElementById('list').innerHTML=I.map(i=>`<div class="item"><div class="mut">${i.sheet}</div><div class="fact">${esc(i.fact)}</div>
${i.replies.length?i.replies.map(r=>`<div class="reply"><span class="mut">Patient, turn ${r.turn}:</span> ${mark(r.text,r.terms)}</div>`).join(''):'<p class="mut">No patient answer contains the scorer words.</p>'}
<label><input type="radio" name="${i.key}" value="true" ${A[i.key]===true?'checked':''}> Said</label><label><input type="radio" name="${i.key}" value="false" ${A[i.key]===false?'checked':''}> Not said</label>
<details><summary class="mut">Whole conversation</summary>${i.turns.map(t=>`<div class="turn"><b>${t.role.toUpperCase()}</b> ${esc(t.text)}</div>`).join('')}</details></div>`).join('');
I.forEach(i=>document.querySelectorAll(`input[name="${i.key}"]`).forEach(r=>r.onchange=()=>{A[i.key]=r.value=='true';save()}));
const n=I.filter(i=>A[i.key]===true||A[i.key]===false).length;document.getElementById('prog').textContent=n+' of '+I.length+' answered'+(n==I.length?'. All done: press Ctrl+C in the terminal.':'')}
async function save(){await fetch('/recheck-save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(A)});const y=window.scrollY;render();window.scrollTo(0,y)}
init();
</script></body></html>"""


def serve_recheck(port: int = 8766) -> None:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class H(BaseHTTPRequestHandler):
        def _send(self, code, body, kind):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path == "/":
                self._send(200, RECHECK_PAGE.encode(), "text/html; charset=utf-8")
            elif self.path == "/recheck-data":
                ans = (yaml.safe_load(RECHECK.read_text()) or {}) if RECHECK.exists() else {}
                self._send(200, json.dumps({"items": recheck_items(), "answers": ans}).encode(), "application/json")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):  # noqa: N802
            if self.path != "/recheck-save":
                return self._send(404, b"not found", "text/plain")
            n = int(self.headers.get("Content-Length", 0))
            if n > 200_000:
                return self._send(413, b"too large", "text/plain")
            try:
                save_recheck(json.loads(self.rfile.read(n)))
            except (ValueError, json.JSONDecodeError) as e:
                return self._send(400, str(e).encode(), "text/plain")
            self._send(200, b"saved", "text/plain")

        def log_message(self, *args):
            pass

    server = None
    for p in range(port, port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), H)
            break
        except OSError:
            continue
    if server is None:
        sys.exit("Could not open a local port.")
    print(f"Second-look page: http://127.0.0.1:{server.server_address[1]}/\nAnswers save to human_check/labels_recheck.yaml as you click.\n"
          "When all are answered, press Ctrl+C here.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped. Your answers are saved.")


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build":
        r = build()
        print(f"{r['candidates']} distinct complete transcripts available; {r['chosen']} sheets written to human_check/sheets/")
    elif cmd == "serve":
        serve()
    elif cmd == "recheck":
        serve_recheck()
    elif cmd == "merge":
        print("wrote", merge_final().relative_to(ROOT))
    elif cmd == "agree":
        r = agree(HC / sys.argv[2] if len(sys.argv) > 2 else None)   # optional: another label file
        (ROOT / "results" / "human_check_agreement.json").write_text(json.dumps(r, indent=2))
        print(json.dumps({k: v for k, v in r.items() if k != "disagreements"}, indent=2))
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
