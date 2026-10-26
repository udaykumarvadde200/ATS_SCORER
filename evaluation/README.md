# Evaluation

Checks that the score responds to resume quality and stays stable between runs.

- `make_resumes.py` creates 12 synthetic resumes (fictional people, example.com emails) in four tiers.
- `run_evaluation.py` scores every resume with the real pipeline, 2 runs each, and writes
  `results.csv` and `results.md`.

Tier definitions (written from ordinary resume advice, not from the scoring code):

| Tier | What the resume looks like |
|---|---|
| weak | thin content, vague duties, no numbers, no skills section or a long unbacked list |
| average | all sections, few strong verbs, almost no numbers |
| good | verb-led bullets, some numbers, most skills used in projects |
| excellent | every bullet verb-led, numbers in most bullets, every skill backed by a project or job |

Run from the project folder:

    python evaluation/run_evaluation.py

Limits: the resumes were written by the project author, so this shows that the score moves in
the expected direction, not that it matches any real ATS.
