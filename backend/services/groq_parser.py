import os
import json
import logging
from typing import Dict

from groq import Groq

logger = logging.getLogger('ats_resume_scorer')


GROQ_MODEL = 'openai/gpt-oss-120b'
_client = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.getenv('GROQ_API_KEY')

        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable not set")
        _client = Groq(api_key=api_key)
    return _client


RESUME_SYSTEM_PROMPT = (
    "You are a resume parser. Extract information from the resume "
    "and return ONLY a valid JSON object. No explanation, no markdown."
)

RESUME_USER_PROMPT = """Extract the following from this resume and return as JSON:
{{
  "name": "full name",
  "email": "email address",
  "phone": "phone number",
  "linkedin": "LinkedIn URL if present, otherwise null",
  "github": "GitHub URL if present, otherwise null",
  "professional_summary": "the full text of the Summary, Profile, About Me, Objective, or Professional Summary section at the top of the resume. Copy the ENTIRE paragraph exactly as written. If no such section exists, return an empty string.",
  "skills": ["list", "of", "skills"],
  "experience": [
    {{
      "job_title": "",
      "company": "",
      "start_date": "",
      "end_date": "",
      "duration_months": 0,
      "description": ""
    }}
  ],
  "education": [
    {{
      "degree": "",
      "institution": "",
      "year": ""
    }}
  ],
  "certifications": ["list of certifications"],
  "projects": [
    {{
      "title": "project name",
      "description": "what the project does and how it was built",
      "technologies": ["tech", "used"]
    }}
  ],
  "action_verbs": ["strong action verbs used in bullet points, e.g. developed, implemented, designed"],
  "keywords": ["important keywords and phrases from the resume for ATS matching"]
}}

Important instructions:
- For duration_months, calculate the number of months between start_date and end_date. If end_date is "Present" or "Current", calculate from start_date to now.
- For skills, extract ALL technical and soft skills mentioned anywhere in the resume.
- For action_verbs, find verbs that start bullet points or describe achievements.
- For keywords, extract noun phrases and technical terms relevant to ATS matching.
- Return ONLY valid JSON. No markdown code fences, no explanation.

Resume Text:
{raw_text}"""


def _call_groq(client: Groq, system_prompt: str, user_prompt: str) -> str:

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ],
        temperature=0.0,
        # Reasoning models spend part of this budget on hidden reasoning tokens,
        # so keep it generous to avoid truncated JSON.
        max_tokens=8192
    )

    content = response.choices[0].message.content or ""
    return content.strip()


def _try_parse_json(text: str) -> dict | None:

    # Strip markdown code fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):

        # Remove opening fence (```json or ```)
        first_newline = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
        cleaned = cleaned[first_newline + 1:]
        # Remove closing fence
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None

    # The validators expect a JSON object, not a list/string/number.
    return parsed if isinstance(parsed, dict) else None


def parse_resume(raw_text: str) -> Dict:

    client = _get_client()
    prompt = RESUME_USER_PROMPT.format(raw_text=raw_text)
    raw_response = _call_groq(client, RESUME_SYSTEM_PROMPT, prompt)
    result = _try_parse_json(raw_response)

    # FIX: was `if result is None`, which returned on failure and
    # retried on success.
    if result is not None:
        return _validate_resume_result(result)

    logger.warning("Groq resume parse: first attempt returned invalid JSON, retrying...")
    strict_prompt = (
        "Your previous response was not valid JSON. "
        "Return ONLY the raw JSON object, no markdown, no explanation, no code fences.\n\n"
        + prompt
    )
    raw_response = _call_groq(client, RESUME_SYSTEM_PROMPT, strict_prompt)
    result = _try_parse_json(raw_response)
    if result is not None:
        return _validate_resume_result(result)

    raise ValueError(
        f"Groq returned unparseable response after retry. Raw response:\n{raw_response[:500]}"
    )


JD_SYSTEM_PROMPT = (
    "You are a job description parser. Extract information and "
    "return ONLY a valid JSON object. No explanation, no markdown."
)

JD_USER_PROMPT = """Extract the following from this job description and return as JSON:
{{
  "job_title": "",
  "required_skills": ["list of must-have skills"],
  "preferred_skills": ["list of nice-to-have skills"],
  "experience_required": "",
  "education_required": "",
  "key_responsibilities": ["list of responsibilities"],
  "keywords": ["important keywords and phrases for ATS matching"]
}}

Important instructions:
- required_skills: skills explicitly stated as required or must-have.
- preferred_skills: skills stated as preferred, nice-to-have, or bonus.
- keywords: extract ALL important terms an ATS system would match against,
  including skills, technologies, certifications, and domain terms.
- Return ONLY valid JSON. No markdown code fences, no explanation.

Job Description Text:
{raw_text}"""


def parse_job_description(raw_text: str) -> Dict:
    client = _get_client()
    prompt = JD_USER_PROMPT.format(raw_text=raw_text)

    raw_response = _call_groq(client, JD_SYSTEM_PROMPT, prompt)
    result = _try_parse_json(raw_response)
    if result is not None:
        return _validate_jd_result(result)

    logger.warning("Groq JD parse: first attempt returned invalid JSON, retrying...")
    strict_prompt = (
        "Your previous response was not valid JSON. "
        "Return ONLY the raw JSON object, no markdown, no explanation, no code fences.\n\n"
        + prompt
    )
    raw_response = _call_groq(client, JD_SYSTEM_PROMPT, strict_prompt)
    result = _try_parse_json(raw_response)
    if result is not None:
        return _validate_jd_result(result)

    raise ValueError(
        f"Groq returned unparseable response after retry. Raw response:\n{raw_response[:500]}"
    )


# Makes sure the parsed JD JSON has all the fields we expect.
def _validate_jd_result(result: dict) -> dict:

    defaults = {
        "job_title": "",
        "required_skills": [],
        "preferred_skills": [],
        "experience_required": "",
        "education_required": "",
        "key_responsibilities": [],
        "keywords": [],
    }

    for key, default in defaults.items():
        if key not in result or result[key] is None:
            result[key] = default
        if isinstance(default, list) and not isinstance(result[key], list):
            result[key] = default

    return result


# Makes sure the parsed resume JSON has all the fields we expect.
def _validate_resume_result(result: dict) -> dict:

    defaults = {
        "name": "",
        "email": None,
        "phone": None,
        "linkedin": None,
        "github": None,
        "professional_summary": "",
        "skills": [],
        "experience": [],
        "education": [],
        "certifications": [],
        "projects": [],
        "action_verbs": [],
        "keywords": [],
    }
    for key, default in defaults.items():
        if key not in result or result[key] is None:
            result[key] = default

        # Ensure list fields are actually lists
        if isinstance(default, list) and not isinstance(result[key], list):
            result[key] = default

    # Validate experience entries
    for exp in result.get("experience", []):
        if not isinstance(exp, dict):
            continue
        exp.setdefault("job_title", "")
        exp.setdefault("company", "")
        exp.setdefault("start_date", "")
        exp.setdefault("end_date", "")
        exp.setdefault("duration_months", 0)
        exp.setdefault("description", "")
        # Ensure duration_months is an int
        try:
            exp["duration_months"] = int(exp["duration_months"])
        except (ValueError, TypeError):
            exp["duration_months"] = 0

    # Validate project entries
    for proj in result.get("projects", []):
        if not isinstance(proj, dict):
            continue
        proj.setdefault("title", "")
        proj.setdefault("description", "")
        proj.setdefault("technologies", [])
    # Groq sometimes returns null (or a list) for text fields; later code calls
    # .strip()/.split()/len() on them, so force them to plain strings.
    def _as_text(value) -> str:
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            return "\n".join(str(v) for v in value)
        return str(value)

    for exp in result.get("experience", []):
        if isinstance(exp, dict):
            for key in ("job_title", "company", "start_date", "end_date", "description"):
                exp[key] = _as_text(exp.get(key))

    for edu in result.get("education", []):
        if isinstance(edu, dict):
            for key in ("degree", "institution", "year"):
                edu[key] = _as_text(edu.get(key))

    for proj in result.get("projects", []):
        if isinstance(proj, dict):
            proj["title"] = _as_text(proj.get("title"))
            proj["description"] = _as_text(proj.get("description"))
            tech = proj.get("technologies")
            proj["technologies"] = [str(t) for t in tech] if isinstance(tech, list) else []

    result["professional_summary"] = _as_text(result.get("professional_summary"))
    result["skills"] = [str(s) for s in result["skills"] if s]
    result["keywords"] = [str(k) for k in result["keywords"] if k]
    result["action_verbs"] = [str(v) for v in result["action_verbs"] if v]

    return result