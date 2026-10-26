# ATS Resume Scorer

An AI-assisted resume analyzer that scores a resume out of 100 the way an Applicant Tracking System might, explains where points were lost, suggests safer rewrites for weak bullets, compares the resume against a job description, and exports a PDF report.

**Status:** runs locally (see "Run locally" below). Cloud deployment is planned.
**Demo video:** https://youtu.be/gwM7k7aJ19E

![Score breakdown](docs/score-breakdown.png)
![PDF report](docs/report.png)

## Features

- Upload a PDF or DOCX resume (5 MB max, file type checked by content, not just extension)
- Structured parsing with an LLM (Groq) into skills, experience, education, projects and keywords
- Score out of 100 built from five weighted components:

| Component | Max points | What it checks |
|---|---|---|
| Formatting | 20 | Sections present, contact details, length and structure |
| Keywords & Skills | 25 | Keyword and skill coverage, matched with fuzzy matching and aliases (for example `ReactJS` = `react`). Credit is scaled by how many skills are backed by projects or experience |
| Content Quality | 25 | Action verbs (counted from the resume text), quantified achievements, summary quality |
| Skill Validation | 15 | Whether each listed skill is backed up by a project or job description |
| ATS Compatibility | 15 | Whether the file can be parsed cleanly by an ATS |

- The overall score always equals the sum of the five components plus any adjustment, and every adjustment is explained on the page and in the PDF
- Optional job description comparison: matched and missing keywords, with the score adjusted up or down
- Detailed feedback with specific issues and prioritized recommendations
- Fix my weak bullets: finds weak bullets in your projects and experience and suggests AI rewrites. Rewrites never invent numbers; missing results appear as [placeholders] to fill in with your real figures
- PDF report export
- Sign-in with Supabase (email or Google); each user gets a private history of past analyses

## Architecture

```
 Streamlit frontend  --(HTTPS, JWT)-->  FastAPI backend  --> Groq LLM (resume parsing, bullet rewrites)
 (views, components)                    |                --> spaCy + sentence-transformers (NLP)
        |                               |                --> Jinja2 + WeasyPrint / ReportLab (PDF)
        +-- Supabase Auth               +--> Supabase (Postgres) for analysis history
```

```
backend/
  api/        routes and JWT auth
  core/       configuration
  database/   Supabase REST client
  models/     Pydantic schemas
  services/   parsing, scoring, JD matching, feedback, recommendations, bullet rewriting, PDF export
  templates/  HTML templates for PDF reports
  utils/      file validation, fuzzy keyword matching, action-verb detection
frontend/
  views/      landing, scorer, history, resources pages
  components/ score display, feedback, recommendations, JD comparison, bullet fixer
  services/   API client, Supabase auth client
evaluation/          12 synthetic test resumes and a script that scores them
tests/               unit tests for matching, action verbs and the bullet fixer
docs/                screenshots used in this README
jupyter notebooks/   exploratory work (EDA, BERT embeddings, fine-tuning)
```

## How the score is computed

1. The file is validated (type, size) and its text is extracted (pdfplumber, with PyPDF2 and python-docx as fallbacks).
2. Groq parses the text into structured data. The parser output is validated and cleaned before scoring.
3. Each component is scored separately and rounded to a whole number, so the breakdown tells the user exactly where points were lost.
4. Skill validation checks every listed skill against project and experience text, using exact whole-word matches first and sentence-embedding similarity (`all-MiniLM-L6-v2`) as a fallback. Keyword credit is scaled by the share of skills that are backed up.
5. If a job description is provided, its keywords are compared with the resume using alias normalization and fuzzy matching. The overall score drops by 5, 10 or 15 points when more than 30%, 50% or 70% of the job description's keywords are missing, and the app shows a note explaining the adjustment. Strong skill validation adds a small bonus.

## Fix my weak bullets

After scoring, the app finds bullets in the projects and experience sections that do not start with a strong action verb or show no measurable result. One click asks the LLM for rewrites, and every rewrite is checked before it is shown:

- a rewrite that adds a number which was not in the original bullet is dropped
- a rewrite that adds an improvement or achievement claim the original never made is dropped
- missing results appear as [placeholders] such as [X%] or [N users], to be filled in with real figures

## Evaluation

To check that the score responds to resume quality, I wrote 12 synthetic resumes (fictional people) in four tiers and scored each one twice with the full pipeline (`evaluation/`). The tiers were written from ordinary resume advice, not from the scoring code.

| Tier | Before fix (average) | After fix (average) | After fix (range) |
|---|---|---|---|
| Weak | 39.7 | 33.0 | 29-39 |
| Average | 57.3 | 50.8 | 46.5-54 |
| Good | 74.0 | 71.0 | 71 |
| Excellent | 84.0 | 81.3 | 80-84 |

- Using each resume's average score, every resume in a higher tier scored above every resume in the tier below.
- Repeat runs of the same resume differed by at most 2 points after the fix (10 of 12 resumes were identical).
- The first evaluation exposed a weakness: a weak resume with 24 unsupported skills scored 50, close to the average tier, because the keywords component only counted skills. Keyword credit is now scaled by how many skills are backed by projects or experience. That resume now scores 39, and the gap between the weak and average tiers widened from 4 to 7.5 points.
- That resume is still the highest of the weak tier, so a long skills list still earns some credit.
- The resumes were written by the project author, so this shows the score moves in the expected direction. It does not show agreement with any real ATS.

Reproduce it with `python evaluation/make_resumes.py` and `python evaluation/run_evaluation.py`. The first (baseline) results are saved in `evaluation/results_baseline.md`. The script retries when the Groq API rate-limits a request.

## Design decisions

- **The LLM extracts, rules score.** Groq only turns the resume into structured data. Every point in the score comes from rule-based code, so a result can be explained and tested.
- **Action verbs are counted from the text, not taken from the LLM.** The LLM's list changed between runs and moved the content score. Counting verbs that start bullets gave identical scores on repeat runs.
- **The score always adds up.** Components are rounded before they are summed, and any job description penalty or skill bonus is shown on the page and in the PDF, so the headline number never disagrees with the breakdown.
- **Skills need evidence.** A skill listed but never used in a project or job earns less. The evaluation showed that counting skills alone let a keyword-stuffed resume score near the average tier, so keyword credit is now scaled by how many skills are backed up.
- **Rewrites never invent results.** The bullet fixer asks for [placeholders] instead of numbers, and the code drops any rewrite that adds a number or an improvement claim the original did not have.
- **Failures degrade instead of breaking.** PDF export falls back from WeasyPrint to ReportLab, and file parsing has fallback extractors, so the app still works on machines without every system library.

## Run locally

Requirements: Python 3.10+.

```bash
git clone https://github.com/udaykumarvadde200/ATS_SCORER.git
cd ATS_SCORER
python -m venv .venv
.venv\Scripts\activate        # Windows (use: source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
python -m spacy download en_core_web_md
```

Copy `.env.example` to `.env` and fill in your values:

```
GROQ_API_KEY=
SUPABASE_URL=
SUPABASE_KEY=            # service_role key, backend only
SUPABASE_ANON_KEY=       # public anon key, used for sign-in
SUPABASE_JWT_SECRET=
```

For the frontend, create `frontend/.streamlit/secrets.toml`:

```toml
[backend]
url = "http://localhost:8000"
```

Start the backend and the frontend in two terminals:

```bash
python -m uvicorn backend.main:app --reload
streamlit run frontend/streamlit_app.py
```

Run the tests:

```bash
pip install pytest
python -m pytest tests -q
```

## API

All routes are under `/api/v1` and require a Supabase access token except `/health`.

| Method | Route | Purpose |
|---|---|---|
| POST | `/analyze-resume` | Upload a resume (and optional job description), get the full analysis |
| GET | `/history` | List the signed-in user's past analyses |
| DELETE | `/history/{analysis_id}` | Delete one analysis |
| POST | `/generate-pdf` | Generate a PDF report from an analysis |
| POST | `/improve-bullets` | Rewrite weak bullets with AI suggestions |
| GET | `/history/{analysis_id}/pdf` | PDF report for a saved analysis |
| GET | `/health` | Health check |

## Tech stack

Python, FastAPI, Streamlit, Groq (LLM parsing and rewrites), spaCy, sentence-transformers, RapidFuzz, Supabase (auth and Postgres), Jinja2, WeasyPrint, ReportLab, pdfplumber, python-docx.

## Known limitations

- Grammar checking and location checking are placeholders. They do not currently affect the score.
- LLM parsing can vary slightly between runs, so the same resume may differ by a few points, mostly in keywords and skill validation. Action-verb counting is deterministic.
- The score is a heuristic inspired by how ATS software works. It is not an official score from any specific ATS.
- A long skills list that no project backs up still earns some keyword credit.
- Semantic skill matching uses a small embedding model, so skills are mainly validated through exact mentions in projects and experience.
- The notebooks are exploratory. The live scorer uses `all-MiniLM-L6-v2` and does not load a fine-tuned model.
- Email confirmation links point to the configured app address, so sign-up links only work on the machine running the app until it is deployed. Google sign-in works.
- Heavy use can hit the Groq API rate limit, which shows up as a temporary error.

## Roadmap

- Real grammar and location checks
- Cache parsed results so the same resume always returns the same score
- More unit tests for the scoring components
- Cloud deployment (needs a host with enough memory for PyTorch and spaCy, or a lighter embedding engine)
- Support for more resume languages and layouts
