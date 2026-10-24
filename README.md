# ATS Resume Scorer

An AI-assisted resume analyzer that scores a resume out of 100 the way an Applicant Tracking System might, explains where points were lost, compares the resume against a job description, and exports a PDF report.

**Live demo:** `<your-streamlit-app-url>`  
**Backend API docs:** `<your-backend-url>/docs`


![Score breakdown](docs/score-breakdown.png)
![PDF report](docs/report.png)

## Features

- Upload a PDF or DOCX resume (5 MB max, file type checked by content, not just extension)
- Structured parsing with an LLM (Groq) into skills, experience, education, projects, keywords and action verbs
- Score out of 100 built from five weighted components:

| Component | Max points | What it checks |
|---|---|---|
| Formatting | 20 | Sections present, contact details, length and structure |
| Keywords & Skills | 25 | Keyword and skill coverage, matched with fuzzy matching and aliases (for example `ReactJS` = `react`) |
| Content Quality | 25 | Action verbs, quantified achievements, summary quality |
| Skill Validation | 15 | Whether each listed skill is backed up by a project or job description |
| ATS Compatibility | 15 | Whether the file can be parsed cleanly by an ATS |

- Optional job description comparison: matched and missing keywords, with the score adjusted up or down
- Detailed feedback with specific issues and prioritized recommendations
- PDF report export
- Sign-in with Supabase; each user gets a private history of past analyses

## Architecture

```
 Streamlit frontend  --(HTTPS, JWT)-->  FastAPI backend  --> Groq LLM (resume parsing)
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
  services/   parsing, scoring, JD matching, feedback, recommendations, PDF export
  templates/  HTML templates for PDF reports
  utils/      file validation, fuzzy keyword matching
frontend/
  views/      landing, scorer, history, resources pages
  components/ score display, feedback, recommendations, JD comparison
  services/   API client, Supabase auth client
jupyter notebooks/   exploratory work (EDA, BERT embeddings, fine-tuning)
tests/               unit tests for keyword matching
```

## How the score is computed

1. The file is validated (type, size) and its text is extracted (pdfplumber, with PyPDF2 and python-docx as fallbacks).
2. Groq parses the text into structured data. The parser output is validated and cleaned before scoring.
3. Each component is scored separately, so the breakdown tells the user exactly where points were lost.
4. Skill validation checks every listed skill against project and experience text, using exact whole-word matches first and sentence-embedding similarity (`all-MiniLM-L6-v2`) as a fallback.
5. If a job description is provided, its keywords are compared with the resume using alias normalization and fuzzy matching, and the overall score is adjusted.

## Run locally

Requirements: Python 3.10+.

```bash
git clone <your-repo-url>
cd ai-resume-ats-main
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
| GET | `/history/{analysis_id}/pdf` | PDF report for a saved analysis |
| GET | `/health` | Health check |

## Tech stack

Python, FastAPI, Streamlit, Groq (LLM parsing), spaCy, sentence-transformers, RapidFuzz, Supabase (auth and Postgres), Jinja2, WeasyPrint, ReportLab, pdfplumber, python-docx.

## Known limitations

- Grammar checking and location checking are placeholders. They do not currently affect the score.
- LLM parsing can vary slightly between runs, so the same resume may differ by a few points, mostly in content quality and keywords.
- The score is a heuristic inspired by how ATS software works. It is not an official score from any specific ATS.
- Semantic skill matching uses a small embedding model, so skills are mainly validated through exact mentions in projects and experience.
- The notebooks are exploratory. The live scorer uses `all-MiniLM-L6-v2` and does not load a fine-tuned model.

## Roadmap

- Real grammar and location checks
- Deterministic action-verb counting so scores are more stable
- More unit tests for the scoring components
- Support for more resume languages and layouts
