# Adding a case

Every case is a fictional patient. Never use real patient data, real transcripts or anything from a clinical source.

1. Start from the template:

   ```bash
   .venv/bin/python -m src.cases new back-pain-2
   ```

   This creates `cases/C06-back-pain-2.yaml` (the number is the next free one).
2. Fill it in. Rules are at the top of the template. In short: keep the medicine simple and low-risk; write facts in the third person with no gender pronouns (a swap must only change the persona's gender); give no name; use all 11 categories; list the warning-sign facts in `red_flags`; make both swap variants change one thing only.
3. Add match terms for every fact except the first one in `cases/match_terms.yaml`. They are the words a patient reply contains when it states the fact. Keep them specific: a term that appears whenever the topic is mentioned will credit facts the patient did not give.
4. Check it:

   ```bash
   .venv/bin/python -m src.cases check
   .venv/bin/python -m pytest -q
   ```

5. Have someone who is not the author read it. A layperson should be able to tell, from the case alone, whether an interviewer found each fact.
6. Run it like the others (see the README), and update the counts in the README from the generated `results/summary.md`.
