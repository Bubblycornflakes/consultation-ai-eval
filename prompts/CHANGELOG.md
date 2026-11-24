# Prompt versions

Prompts are plain text files named `<role>_v<N>.txt`. A prompt file is never edited after it has been used in a run: a change becomes a new version and the old file stays. Every run records the file name and a SHA-256 hash of each prompt it used.

## v1 (used in the Stage 2 baseline runs in `results/stage2/`)

- `patient_v1.txt`: the simulated patient. Receives persona and all hidden facts; answers only what is asked.
- `interviewer_v1.txt`: the model under test. One instruction: take a clear, complete history, one question at a time, no diagnosis, no advice. It also ends the history with the marker `[HISTORY COMPLETE]` so the harness knows when it has finished; the harness caps a conversation at 20 interviewer turns and does not tell the model about the cap. The interviewer is not told the patient's age or gender.

## v2 (used in `results/stage2_v2/`)

- `patient_v2.txt`: written for fact gating. The patient no longer sees the whole fact list. A separate call (`gate_v1.txt`) first picks which hidden facts the interviewer's question relates to, and the patient prompt shows only those facts for that one answer. Rules were tightened: use only the listed facts, give them as written, answer a plain "No" or "I don't know" for anything not listed, and give ideas, worries and hopes only if a listed fact states them.
- `gate_v1.txt`: the gating prompt. It sees every fact with its id and category, and returns JSON listing the relevant fact ids. The patient never sees categories.
- `interviewer_v2.txt`: v1 plus a booking record line (`Age: ..., Gender: ...`), identical in format across swap variants so only the values change. The end marker may only appear in the final message, which must not contain a question.
- `drafts/patient_v2_ungated_draft.txt`: an earlier draft of patient_v2 that showed the whole fact list. It was a proposal and was replaced by the gated version. It has not been used in any run.
