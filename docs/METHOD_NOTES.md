# Method notes

A working record of corrections, decisions and diagnostics behind the numbers in the README. Every figure comes from a file in `results/`.

## Corrections

- An early note counted 12 complete conversations plus 1 partial in the first v2 batch. The correct figures are **11 complete plus 1 partial** (a results log file had been counted as a conversation). Four runs, not three, were therefore missing, and all four were rerun.

## Runs and repeats

- One v2 run (C02, run 3) stalled for 180.9 s and was stopped by the 3-minute limit. It is kept in `results/stage2_v2/partial_stopped_slow/` and is excluded from counts. Memory pressure on the machine is the likely cause (swap was nearly full at the time); this was not tested.
- The four reruns finished in 31 to 49 s and each produced a dialogue identical to run 1 of the same case, so the 15 v2 conversations are **7 distinct transcripts** (C01 1, C02 2, C03 1, C04 2, C05 1). The stalled run differed from its rerun, so temperature 0 was not repeatable under that load.
- Ollama honours the seed (`results/seed_test.json`), but temperature 0 was not exactly repeatable on an open-ended prompt.

## Harness v2.1 (2026-11-24)

The harness accepts `HISTORY COMPLETE` written without brackets as the end of a conversation. Only the reading of the ending changed; the model's prompt did not. The existing v2 transcripts are read under the same rule by `src/endings.py`, and the strict counts are kept: in 3 of 15 v2 conversations the strict harness missed a bare marker, and in 7 of 15 the final message contained a question although the prompt says not to ask one. The 15 base v2 conversations were run under v2.0 and the 10 swap conversations under v2.1. The scorer reads all of them under the lenient rule, so repeated end lines after a bare marker are not scored.

## Counting

- The counting definitions in the README were written on 2026-11-19 at 23:52, before any v2 transcript was read. One v2 transcript had been seen before that: a smoke test of the pipeline on C03, which showed the patient inventing details even with gating. Its output was deleted and is not counted.
- All hand counts come from a single review pass. The first v2 batch was reviewed in `results/stage2_v2/hand_review_batch1.json` and carried to all 15 conversations in `hand_review_summary_15.json` (the reruns reproduced run 1 exactly, so they take their twin's labels).

## The scorer

The match terms in `cases/match_terms.yaml` were written after all 12 distinct v1 and v2 transcripts had been read, so the scorer is tuned to them. `human_check/labels_human.yaml` is the (blank) file for human labels.

## Gate misses

`results/gate_miss_diagnostic.json` re-ran the gate on the 7 turns marked as misses. The miss repeated every time (7 of 7, identical to the logged choice), so it is deterministic. With the category labels removed from the gate's fact list it would have picked the missing fact on 3 of 7. A revised gate was not run.

## Design choices

- v2 changed three things together (patient prompt with gating, tighter rules, and the booking-record line for the interviewer), so the effects cannot be separated.
- The interviewer is not told the patient's age or gender in v1, so a swap could only reach it through the patient's wording. In v2 it receives one booking-record line, identical in format across variants with only the values changed.

## Not run

A revised gate; a neutral-edit control for the age and gender comparison; more repeats with different seeds at a small nonzero temperature; an ablation of the booking-record line (patient_v2 with gating and `interviewer_v1`); a revised interviewer prompt for the ending problem; more cases; a stronger model.
