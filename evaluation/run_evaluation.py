"""Score the synthetic test resumes with the real pipeline and build a README table.

Run from the project folder (the one that contains `backend` and `evaluation`):

    python evaluation/run_evaluation.py            # 2 runs per resume
    python evaluation/run_evaluation.py --runs 3

Needs the same setup as the backend (.env with GROQ_API_KEY, spaCy model,
sentence-transformers model). Each run makes one Groq call per resume.
Writes evaluation/results.csv and evaluation/results.md.
"""

import argparse
import csv
import glob
import os
import re
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TIERS = ["weak", "average", "good", "excellent"]
COMPONENTS = ["formatting", "keywords", "content", "skill_validation", "ats_compatibility"]


def find_resumes(folder):
    found = []
    for tier in TIERS:
        for path in sorted(glob.glob(os.path.join(folder, tier, "*.pdf"))):
            found.append((tier, path))
    return found


MAX_WAIT = 180  # seconds; a longer wait means a daily limit, so give up on that run


def _is_rate_limit(message):
    low = message.lower()
    return "429" in low or "rate limit" in low


def _retry_wait(message, attempt):
    """Seconds to wait after a rate-limit error (uses the hint in the message if present)."""
    match = re.search(r"try again in (?:(\d+)m)?\s*([\d.]+)\s*(ms|s)", message)
    if match:
        minutes = float(match.group(1) or 0)
        value = float(match.group(2))
        seconds = value / 1000 if match.group(3) == "ms" else value
        return minutes * 60 + seconds + 1
    return 15.0 * attempt


def _score_with_retry(analyze, text, max_retries, sleep):
    attempt = 0
    while True:
        try:
            return analyze(text)
        except Exception as exc:
            message = str(exc)
            attempt += 1
            if not _is_rate_limit(message) or attempt > max_retries:
                raise
            wait = _retry_wait(message, attempt)
            if wait > MAX_WAIT:
                raise RuntimeError(f"Rate limit needs a {wait:.0f}s wait (daily limit?). Try again later.")
            print(f"    rate limited, waiting {wait:.0f}s (attempt {attempt}/{max_retries})")
            sleep(wait)


def evaluate(resumes, runs, parse, analyze, pause=6.0, max_retries=5, sleep=time.sleep):
    """Return one row per (resume, run). `parse` and `analyze` are injected."""
    rows = []
    for tier, path in resumes:
        name = os.path.basename(path)
        with open(path, "rb") as f:
            text, _meta = parse(f.read(), name)
        for run in range(1, runs + 1):
            try:
                result = _score_with_retry(analyze, text, max_retries, sleep)
                comp = result.get("component_scores", {})
                row = {
                    "tier": tier, "file": name, "run": run,
                    "overall": float(result.get("ATS_score", result.get("ats_score", 0))),
                    **{c: float(comp.get(c, 0)) for c in COMPONENTS},
                    "error": "",
                }
            except Exception as exc:  # keep going; report the failure
                row = {"tier": tier, "file": name, "run": run, "overall": float("nan"),
                       **{c: float("nan") for c in COMPONENTS}, "error": str(exc)[:120]}
            rows.append(row)
            print(f"  {name} run {run}: {row['overall'] if not row['error'] else 'ERROR ' + row['error']}")
            sleep(pause)
    return rows


def _ok(rows):
    return [r for r in rows if not r["error"]]


def summarize(rows):
    """Markdown report: per-tier summary, per-resume stability, ordering check."""
    good_rows = _ok(rows)
    per_resume = {}
    for r in good_rows:
        per_resume.setdefault((r["tier"], r["file"]), []).append(r)

    lines = ["### Score by resume quality tier", "",
             "| Tier | Resumes | Average score | Lowest | Highest |", "|---|---|---|---|---|"]
    tier_means = {}
    resume_means = {t: [] for t in TIERS}
    for (tier, _f), rs in per_resume.items():
        resume_means[tier].append(statistics.mean(x["overall"] for x in rs))
    for tier in TIERS:
        vals = resume_means[tier]
        if not vals:
            continue
        tier_means[tier] = statistics.mean(vals)
        lines.append(f"| {tier.capitalize()} | {len(vals)} | {tier_means[tier]:.1f} | {min(vals):.1f} | {max(vals):.1f} |")

    lines += ["", "### Repeat-run stability", "",
              "| Resume | Scores across runs | Largest difference |", "|---|---|---|"]
    worst = 0.0
    for (tier, fname), rs in per_resume.items():
        scores = [x["overall"] for x in rs]
        diff = max(scores) - min(scores)
        worst = max(worst, diff)
        lines.append(f"| {fname} | {', '.join(f'{s:.0f}' for s in scores)} | {diff:.0f} |")

    present = [t for t in TIERS if resume_means[t]]
    ordered = all(tier_means[a] < tier_means[b] for a, b in zip(present, present[1:]))
    separated = all(max(resume_means[a]) < min(resume_means[b]) for a, b in zip(present, present[1:]))
    failures = len(rows) - len(good_rows)

    lines += ["", "### Checks", "",
              f"- Tier averages increase from weak to excellent: **{'yes' if ordered else 'no'}**",
              f"- Every resume in a higher tier scores above every resume in the tier below: **{'yes' if separated else 'no'}**",
              f"- Largest difference between repeat runs of the same resume: **{worst:.0f} points**"]
    if failures:
        lines.append(f"- Runs that failed and were left out: **{failures}**")
    return "\n".join(lines)


def write_outputs(rows, report):
    csv_path = os.path.join(HERE, "results.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["tier", "file", "run", "overall", *COMPONENTS, "error"])
        writer.writeheader()
        writer.writerows(rows)
    md_path = os.path.join(HERE, "results.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report + "\n")
    return csv_path, md_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--pause", type=float, default=6.0,
                        help="seconds to wait between Groq calls (avoids rate limits)")
    args = parser.parse_args()

    sys.path.insert(0, ROOT)
    resumes = find_resumes(os.path.join(HERE, "resumes"))
    if not resumes:
        sys.exit("No resumes found. Run: python evaluation/make_resumes.py")

    print("Loading models (this takes a minute)...")
    import spacy
    from sentence_transformers import SentenceTransformer
    from backend.core.config import SENTENCE_TRANSFORMER_MODEL, SPACY_MODEL_PRIMARY, SPACY_MODEL_SECONDARY
    from backend.services.resume_analyzer import analyze_full_resume
    from backend.services.resume_parser import parse_resume_file

    try:
        nlp = spacy.load(SPACY_MODEL_PRIMARY)
    except OSError:
        nlp = spacy.load(SPACY_MODEL_SECONDARY)
    embedder = SentenceTransformer(SENTENCE_TRANSFORMER_MODEL)

    def analyze(text):
        return analyze_full_resume(resume_text=text, nlp=nlp, embedder=embedder, job_description="")

    print(f"Scoring {len(resumes)} resumes, {args.runs} runs each...")
    rows = evaluate(resumes, args.runs, parse_resume_file, analyze, pause=args.pause)
    report = summarize(rows)
    csv_path, md_path = write_outputs(rows, report)
    print("\n" + report)
    print(f"\nSaved {csv_path}\nSaved {md_path}")


if __name__ == "__main__":
    main()
