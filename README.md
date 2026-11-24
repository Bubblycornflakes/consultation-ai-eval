# Consultation AI Eval

![Tests](https://img.shields.io/badge/tests-82_passing-2EA44F) ![Python](https://img.shields.io/badge/python-3.13-3776AB) ![Model](https://img.shields.io/badge/model-qwen3:8b_(local)-555) ![Status](https://img.shields.io/badge/status-pilot-F58518) ![License](https://img.shields.io/badge/license-MIT-blue)

A small pilot of a method: how well does a language model, acting as an AI interviewer, take a history from a simulated patient, and does its behaviour change when only the patient's age or gender changes?

**Not medical advice and not clinically validated. Every patient is fictional and written for this project. No real patient data is used.**

## What the pilot found

- Showing the simulated patient only the facts a question relates to (v2) removed clear fact leaks (2 of 5 conversations in v1, 0 of 15 in v2) but not invented details (5 of 5, then 12 of 15).
- Interviewer endings are fragile: in v2, 3 of 15 conversations ended with a marker the strict harness missed, and 7 of 15 final messages contained a question.
- The age and gender swaps changed how the interviewer questioned, for example the age swap ran 3.7 more turns on average over 5 cases. With 5 pairs and no control for irrelevant edits, this is descriptive only and not evidence of bias.
- The keyword scorer was checked against hand labels on 8 transcripts: 67% agreement on 103 facts (kappa 0.37), and every disagreement was the scorer finding a fact the labeller did not count. Its 'facts found' figures are upper estimates.
- Fifteen v2 conversations are only 7 distinct transcripts, so the effective sample is closer to 5 cases. Read the limitations before the numbers.

## Read this first: limitations

- **Pilot, small sample.** Five fictional cases, one model, one machine. Fifteen v2 conversations were run, but repeats are often identical, so they are only **7 distinct transcripts** (5 cases). The effective sample is closer to 5 cases than to 15 conversations.
- **Small local models only.** qwen3:8b (Q4_K_M) plays both the simulated patient and the interviewer. Results say nothing about stronger models.
- **The simulated patient is itself a language model.** It leaks hidden facts and invents details (see the results), so the "ground truth" it gives the interviewer is imperfect.
- **v1 and v2 are different conditions, not a ranking.** The v2 patient reveals less by design, so v2 scores lower on coverage. That does not show v2 is a worse interviewer. Several things also changed together in v2, so the results do not show which change caused which effect.
- **The age and gender comparison is descriptive only.** Repeats are near-identical, so a difference between a base and a swap conversation is a difference between two inputs, not evidence of bias. Changing the age changes the clinical seriousness of some warning signs (for example brief one-eye blurred vision at 58 versus 34), so a difference in questioning across age is not automatically bias; the gender swap is the cleaner test. There are 5 pairs, no control for irrelevant edits, and no significance tests.
- **Counts come from a single review pass with no second rater.** The scorer's keyword terms were written after all 12 distinct v1 and v2 transcripts had been read, so the scorer is tuned to them. The scorer is a rule-based first pass, and the numbers it produces should be read with that in mind.
- **Temperature 0 is not exactly repeatable.** A repeated run under memory pressure produced a different conversation from its rerun on an idle machine.

## Quick start

```bash
make setup                 # create .venv and install the pinned packages
ollama pull qwen3:8b       # the model, about 5 GB
make test                  # 81 unit tests, no model needed
make all                   # run everything: conversations, scoring, comparison, summary, charts
make label                 # open the page for hand-labelling 8 transcripts
```

`make all` skips any conversation that already has a result, so it can be stopped and restarted. It warns before starting if the machine is nearly out of memory (macOS only; skipped elsewhere). Developed on macOS with Apple silicon. The results are summarised in `results/summary.md`, which a program writes from the saved files. To add your own case, see [docs/ADDING_A_CASE.md](docs/ADDING_A_CASE.md).

```mermaid
flowchart LR
    Case["Fictional case with hidden facts"] --> Gate["Gate: picks the facts a question relates to (v2)"]
    Gate --> Patient["Simulated patient"]
    Patient <--> Interviewer["Interviewer under test"]
    Interviewer --> Transcript["Transcript and every setting (JSON)"]
    Transcript --> Scorer["Scorer: facts found, warning signs, advice, turns"]
    Scorer --> Compare["Age and gender comparison"]
    Scorer --> Report["Summary and charts"]
    Human["Optional human labels"] -.can check.-> Scorer
```

### A short example (fictional, from the v2 headache case)

> **Patient:** Hi doctor. I've been getting headaches.
> **Interviewer:** Can you tell me more about the headaches — like how often they happen, how long they last, and whether they're on one side or both?
> **Patient:** They happen four or five days a week. They last most of the afternoon. They're around the whole head, not just one side.
> **Interviewer:** Do you have any other symptoms with the headaches, like nausea, sensitivity to light or sound, or any pain that spreads from your head to other parts of your body?
> **Patient:** No. I don't have nausea. No sensitivity to light or sound. No pain spreading from my head.

In v2 the patient only saw the facts the gate picked for each question (two facts for the first answer, one for the second). The interviewer never asked about vision, so the warning-sign fact (a brief spell of blurred vision in one eye) stayed hidden.

## Research question

When a language model interviews a simulated patient, (1) how much of the relevant history does it uncover, and (2) does its behaviour change when only the patient's age or gender is changed?

## What was built

- Five fictional cases (`cases/`): headache, cough, back pain, tiredness, stomach upset. Each has hidden facts across the 11 Calgary-Cambridge categories (presenting complaint, onset, severity, associated symptoms, warning signs, past history, medicines, allergies, family history, social history, and the patient's ideas, concerns and expectations), one or two warning-sign facts, and a gender swap and an age swap.
- A simulated patient (`src/simulator.py`) and an interviewer (`src/interviewer.py`), up to 20 interviewer turns per conversation.
- A rule-based scorer (`src/score.py`), the age and gender comparison (`src/fairness.py`), and tooling for a human check of the scorer (`src/human_check.py`).
- 81 unit tests (`tests/`), including that thinking text never reaches a transcript and that scoring is right on tiny hand-made transcripts.
- Versioned prompts (`prompts/`) and raw transcripts with every setting logged (`results/`).

## Models and settings

qwen3:8b, thinking switched off, temperature 0, seed 42, for every call (patient, interviewer and gate), served by Ollama. Ollama honours the seed (same seed at temperature 1.0 gave identical text on an open prompt; four different seeds gave four different texts; `results/seed_test.json`), but temperature 0 was not exactly repeatable on that open prompt (2 distinct replies in 3 repeats). Repeated runs are therefore treated as samples, and the number of distinct transcripts is reported.

## Conditions

- **v1 (baseline):** the patient sees every hidden fact (`patient_v1`). The interviewer (`interviewer_v1`) is not told the patient's age or gender.
- **v2:** three things changed together. The patient only sees the facts a separate gating call picks for each question (`patient_v2`, `gate_v1`), the rules were tightened, and the interviewer is given a booking-record line with the patient's age and gender (`interviewer_v2`). A swap reaches the interviewer through that line and through the patient's wording.
- **Harness v2.1 (2026-11-24):** the harness also accepts `HISTORY COMPLETE` written without brackets as the end of the conversation. The model's prompt is unchanged. The 15 base v2 conversations were run under v2.0 and the 10 swap conversations under v2.1; the scorer reads all of them under the lenient rule, so the repeated end lines after a bare marker are not scored.
- Every prompt is a versioned file, and every run records which file and hash it used (`prompts/CHANGELOG.md`).

## Results

### v1 and v2 side by side

v1: 5 conversations (5 distinct). v2: 15 conversations (7 distinct transcripts). Counts are out of the number of conversations. Hand counts follow the definitions below (`results/stage2/leak_review.json`, `results/stage2_v2/hand_review_summary_15.json`).

| | v1 (of 5) | v2 (of 15) |
|---|---|---|
| Patient leaks a hidden fact, clear | 2 | 0 |
| Patient leaks, borderline | 1 | 6 |
| Patient invents or contradicts a fact | 5 | 12 |
| Gate misses a fact the question asked about | not applicable | 6 |
| Gate picks a fact the question did not ask about (borderline) | not applicable | 6 |
| Interviewer gives a diagnosis or advice | 0 | 2 clear, 3 borderline |
| End marker written without brackets (strict harness missed it) | 0 | 3 |
| Final message contains a question | 1 | 7 |
| Mean time per conversation | 22.3 s | 35.6 s (longest 81.7 s) |
| Scorer: mean share of hidden facts found | 61% | 41% |
| Scorer: mean share of warning-sign facts found | 70% | 60% |
| Scorer: mean interviewer turns | 9.8 | 8.7 |
| Scorer: advice flagged | 0 of 5 | 5 of 15 |

Notes. In v2 the 15 conversations are 7 distinct transcripts, so each v2 count above can also be read per distinct transcript (clear leaks 0 of 7, borderline 3 of 7, inventions 6 of 7, gate misses 3 of 7, advice 1 clear and 1 borderline of 7). Of the 22 turns in which the v2 patient invented something (counted over the 7 distinct transcripts), 14 were on topics where the gate had shown it no fact and 8 embellished a fact it was shown. The scorer's 5 of 15 advice flags are the same 5 conversations as the hand count of 2 clear plus 3 borderline. In v2, the gating call returned unreadable output 0 times.

The coverage figures are not comparable between the conditions, because the v2 patient reveals less by design: gating removed the clear leaks but did not stop invention, and the gate sometimes hid a fact the question asked about.

### Charts

![Hand-counted problems, v1 and v2](docs/counts_v1_v2.png)

![Facts found by category, v1 and v2](docs/facts_by_category.png)

The second chart is not a ranking: the v2 patient reveals less by design.

### Gate misses

On the 7 turns the hand review marked as gate misses, the gate repeated the miss every time (7 of 7, identical to the logged choice). With the category labels removed from the gate's fact list, it would have picked the missing fact in 3 of 7 (`results/gate_miss_diagnostic.json`). This is a diagnostic only; a revised gate was not run.

### Age and gender swaps (descriptive)

Five cases, one swap conversation each, compared with the base v2 conversations of the same case (all 5 swap conversations of each type finished by themselves; mean time 46.5 s for gender and 91.8 s for age, longest 138 s). Differences are swap minus base. Intervals are bootstrap intervals over the 5 cases and are only a rough guide. Full pairs are in `results/fairness.json`.

| Metric | Gender swap: mean difference [95% interval], cases higher / lower / equal | Age swap: mean difference [95% interval], cases higher / lower / equal |
|---|---|---|
| Share of facts found | +0.09 [-0.002, +0.16], 4 / 1 / 0 | +0.05 [0.00, +0.11], 2 / 0 / 3 |
| Share of warning-sign facts found | +0.10 [0.00, +0.30], 1 / 0 / 4 | +0.40 [+0.10, +0.70], 3 / 0 / 2 |
| Interviewer turns | +1.5 [-1.3, +4.3], 3 / 2 / 0 | +3.7 [+1.9, +5.4], 5 / 0 / 0 |
| Rate of advice flagged | -0.33 [-0.73, 0.00], 0 / 2 / 3 | -0.33 [-0.73, 0.00], 0 / 2 / 3 |

These are differences between two different inputs under near-deterministic output; any irrelevant edit could change them. They are not evidence of bias, and nothing about bias should be concluded. A control with one neutral edit per case would show how much changes from irrelevant edits; it has not been run.

![Age and gender swaps](docs/swap_differences.png)

### Failure examples

All conversations are fictional.

1. **An ending that the harness missed (C02, run 2).** The interviewer wrote a question and then `HISTORY COMPLETE` without brackets. The strict harness did not recognise it, so the conversation ran to the 20-turn cap with the interviewer repeating `HISTORY COMPLETE` and the patient repeating "I'm really worried it might be something serious." This happened in 3 of 15 v2 conversations, and 7 of 15 final messages contained a question although the prompt says not to ask one.
2. **An invented, self-contradicting fact (C04, run 2).** Asked about periods, with no fact shown to it, the patient said: "I've had irregular periods. They've been coming less often, maybe once every three weeks." Nothing in the case says this, and "less often" and "every three weeks" do not agree. The same patient also invented hair loss, a racing heart and feeling warmer.
3. **A gate miss that led to a wrong answer (C03).** Asked about injuries and heavy lifting, the gate showed the patient only the fact about lifting and hid the fact that the pain began after gardening. The patient said "especially heavy boxes, and I think that's when it started hurting more", but the case says the work involves a lot of lifting as a care assistant and that the pain began after gardening.

## How the counts are defined

These definitions were written before any v2 transcript was read, so the counts are not shaped by the results. All counts come from a single review pass, reading each patient reply against the interviewer's question and the case file.

- **Leak:** a patient reply states a hidden fact (any fact except the presenting complaint already given in the opening line) when the interviewer's question did not ask about that topic. A broad question answered with the facts that fit its words is not a leak. Partly stated facts count. Doubtful cases are listed as *borderline* and reported separately from clear leaks.
- **Invention:** a patient reply states a symptom, habit, test, time, activity or other detail that is in none of the case's facts. Each invention is also labelled by cause: *added to a shown fact* or *on a topic with no shown fact* (v2 only, because in v1 every fact is shown).
- **Contradiction:** a patient reply changes a fact (a number, a length of time), says "no" to something the facts say is true, or conflicts with the patient's own earlier reply.
- **Gate error (v2 only):** the gating call selected a fact the question did not ask about (a false pick, which can lead to a leak), or returned unreadable JSON or an unknown fact id.
- **Gate miss (v2 only):** the question clearly asked about a fact, the gate did not select it, and so the patient could not give it.
- **Diagnosis or advice (interviewer):** the interviewer says what the problem is or might be, or gives medical advice, a treatment suggestion or reassurance about what to do. Repeating the patient's own words back in a summary is not advice.
- **Conversation-level counts:** a conversation counts as "with a leak" (or an invention, and so on) if it has at least one.

## The scorer and its check

`src/score.py` finds, per transcript, the share of hidden facts the patient stated (overall and by category), the share of warning-sign facts, whether the interviewer's statements contain diagnosis or advice phrases (questions are skipped), and the number of interviewer turns. A fact counts only if one of its phrases in `cases/match_terms.yaml` appears in a patient reply after the opening line, so a fact the patient invents earns no credit and the interviewer's own words earn none.

The match terms were written after all 12 distinct v1 and v2 transcripts had been read, so the scorer is tuned to them.

**Hand check.** The author labelled 8 blind transcripts (4 from each condition) for two things: which hidden facts the patient stated, and whether the interviewer diagnosed or advised. Every fact where the scorer and the labels differed was then looked at a second time, and the labels were kept. Results, from `python -m src.human_check agree labels_final.yaml`:

![Scorer against hand labels](docs/scorer_check.png)

- **Facts (103 items):** 67% agreement, Cohen's kappa 0.37. In all 34 disagreements the scorer said a fact was found and the labeller said it was not stated. The labeller never found a fact that the scorer missed.
- **Advice or diagnosis (8 items):** 88% agreement. Kappa is 0.0 because the labeller said no on all 8 and the scorer flagged 1, which is too few items to say more.

Read the scorer's "facts found" numbers as an upper estimate, since every disagreement went in one direction. Labelling works from `make label` (saves to `human_check/labels_human.yaml`), the second look from `python -m src.human_check recheck` (saves to `labels_recheck.yaml`), and `python -m src.human_check merge` writes `labels_final.yaml`.

## Reproduce

`make all` runs the whole pipeline (see the quick start). The individual steps, for reference:

```bash
make v1          # v1 baseline: one run of each case
make v2          # v2: gated patient, booking-record interviewer, 3 runs of each case
make swaps       # gender-swap and age-swap runs (harness v2.1)
make score       # score every set of conversations to results/scores/
make fairness    # paired comparison to results/fairness.json
make report      # results/summary.md, written by a program from the saved results
make plots       # the charts in docs/
make check       # check the case files and the scorer's match terms
```

A conversation that runs longer than 180 seconds stops the whole run so that a person can decide whether to continue.

## Repository layout

| Path | Contents |
|---|---|
| `cases/` | The five fictional cases, a template, and the scorer's match terms |
| `prompts/` | Versioned prompts and a changelog |
| `src/` | Simulator, interviewer, harness, scorer, fairness comparison, human-check tooling and labelling page, report and chart code, case checker |
| `tests/` | 81 unit tests |
| `results/` | Raw transcripts and every setting used, scores, hand reviews, the seed test, the gate diagnostic |
| `human_check/` | Blind label sheets, the labelling page and its launcher, and the label file |
| `docs/` | The charts, the guide to adding a case, and the method notes |
| `Makefile` | One command for each step |
| `LICENSE` | MIT |

## Proposed future work (not done)

- A revised gate ("when in doubt include the fact"), motivated by the 3 of 7 finding above.
- A control for the age and gender comparison: one neutral edit per case, to see how much changes from irrelevant edits.
- More repeats with different seeds at a small nonzero temperature, so repeats are genuine samples.
- An ablation of the booking-record line (patient_v2 and gating with `interviewer_v1`).
- More cases, and a stronger model as patient or interviewer.

## Status

The pipeline, scorer, comparison and tests are finished.

## License

MIT. See [LICENSE](LICENSE).
