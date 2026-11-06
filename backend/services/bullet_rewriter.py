"""Find weak resume bullets and rewrite them with Groq.

find_weak_bullets() is deterministic (no LLM call) and runs during every
analysis. rewrite_bullets() calls Groq and only runs when the user asks.

Rewrites never invent results: any number in a rewrite must already be in the
original bullet, or sit inside a [placeholder] the user fills in themselves.
"""

import difflib
import logging
import re
from typing import Dict, List

from backend.services.groq_parser import _call_groq, _get_client, _try_parse_json
from backend.utils.action_verbs import ACTION_VERBS
from backend.utils.timing import timed

logger = logging.getLogger('ats_resume_scorer')

MAX_BULLETS = 6
MAX_BULLET_CHARS = 400

_BULLET_GLYPHS = re.compile("[\u2022\u25cf\u25aa\u25e6\u2023\u00b7\uf0b7\uf0a7]")
_LEADING_JUNK = re.compile(r"^(?:[\s\-\*>\u2013\u2014]+|o\s+)+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.;])\s+")
_FIRST_WORD = re.compile(r"[A-Za-z]+")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_LABEL_PREFIX = re.compile(r"^[A-Z][^:.;]{2,60}:\s+")
_PLACEHOLDER = re.compile(r"\[[^\]]*\]")

_METRIC = re.compile(
    r"\d+(?:[.,]\d+)?\s*%"
    r"|\$\s?\d+"
    r"|\b\d+(?:[.,]\d+)?\s*[kKmMbB]\b"
    r"|\b\d[\d,]*\+?\s*(?:users?|customers?|clients?|projects?|hours?|days?|months?|"
    r"years?|records?|requests?|samples?|documents?|models?|images?|rows?|queries|"
    r"datasets?|layers?|epochs?|features?|classes|tests?|endpoints?)\b",
    re.IGNORECASE,
)


def _split_bullets(description: str) -> List[str]:
    """Split a description into bullet-sized sentences."""
    bullets = []
    for line in _BULLET_GLYPHS.sub("\n", description or "").splitlines():
        line = _LEADING_JUNK.sub("", line.strip())
        for sentence in _SENTENCE_SPLIT.split(line):
            sentence = _LEADING_JUNK.sub("", sentence.strip())
            words = sentence.split()
            if 5 <= len(words) <= 60:          # skip headings and fragments
                bullets.append(sentence)
    return bullets


def _issues_for(bullet: str) -> List[str]:
    issues = []
    # "Project Name: Built a ..." -> judge the verb after the label
    body = _LABEL_PREFIX.sub("", bullet, count=1)
    match = _FIRST_WORD.match(body)
    if not match or match.group(0).lower() not in ACTION_VERBS:
        issues.append("does not start with a strong action verb")
    if not _METRIC.search(bullet):
        issues.append("no measurable result")
    return issues


@timed('weak_bullets')
def find_weak_bullets(parsed_resume: Dict, limit: int = MAX_BULLETS) -> List[Dict[str, str]]:
    """Return up to `limit` bullets from experience and projects that need work."""
    sources = []
    for exp in parsed_resume.get('experience') or []:
        if isinstance(exp, dict):
            label = exp.get('job_title') or exp.get('company') or 'Experience'
            sources.append((str(label), exp.get('description')))
    for proj in parsed_resume.get('projects') or []:
        if isinstance(proj, dict):
            sources.append((str(proj.get('title') or 'Project'), proj.get('description')))

    found = []
    for label, description in sources:
        if not isinstance(description, str):
            continue
        for bullet in _split_bullets(description):
            issues = _issues_for(bullet)
            if issues:
                found.append({
                    'bullet': bullet[:MAX_BULLET_CHARS],
                    'source': label,
                    'issues': '; '.join(issues),
                    '_count': len(issues),
                })

    # Bullets with both problems first; ties keep resume order (stable sort).
    found.sort(key=lambda item: -item['_count'])
    return [{k: v for k, v in item.items() if k != '_count'} for item in found[:limit]]


# ---------------------------------------------------------------------------
# Rewriting with Groq
# ---------------------------------------------------------------------------

REWRITE_SYSTEM_PROMPT = (
    "You are a careful resume editor. Return ONLY a valid JSON object. "
    "No explanation, no markdown."
)

# Concrete verbs the scorer also recognises (checked against the verb list at import time).
_PREFERRED_VERBS = [
    v for v in (
        "built developed designed implemented created deployed trained evaluated tested analyzed automated "
        "optimized reduced improved integrated engineered architected refactored debugged configured extended "
        "migrated prototyped documented led managed delivered launched researched applied indexed parsed"
    ).split() if v in ACTION_VERBS
]
_BANNED_STARTS = {'leveraged', 'utilized', 'utilised', 'used', 'worked', 'helped', 'responsible'}

REWRITE_USER_PROMPT = """Improve each resume bullet below. Return JSON only.

For every bullet give:
- "rewrite": a stronger version, or "" if the original wording is already fine.
- "note": at most 12 words saying what changed.
- "measure_ideas": up to 3 short phrases naming things the person could MEASURE for this kind of work, for example "number of documents indexed", "answer accuracy on a test set", "average response time". Never put numbers in them.

Rules for "rewrite":
- Keep every fact. Do NOT add tools, technologies, employers, results, goals or numbers that are not in the original bullet.
- Start with a concrete past-tense action verb. Prefer one of: {verbs}. Never start with Leveraged, Utilized, Used, Worked, Helped or Responsible.
- Do not rewrite just to swap a synonym or to add small words. If the bullet already starts with a good verb and only lacks a result, return "" for "rewrite" and give "measure_ideas" instead.
- You may add ONE placeholder in square brackets, such as [N documents] or [X%], only if the bullet names something that can be counted or measured. Never claim an improvement the original does not claim.
- Keep the tense: ongoing work stays ongoing. One sentence, at most 28 words. Use plain hyphens and straight quotes.

Return JSON in exactly this shape, one item per bullet, in the same order:
{{"rewrites": [{{"original": "...", "rewrite": "...", "note": "...", "measure_ideas": ["...", "..."]}}]}}

Bullets:
{numbered}"""

_TYPO_MAP = str.maketrans({
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
    "\u2014": " - ", "\u2015": " - ",
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u00a0": " ",
})

# Words that claim an improvement or achievement.
_IMPACT_STEMS = ("achiev", "improv", "boost", "reduc", "increas", "enhanc",
                 "accelerat", "outperform")


def _normalize(text: str) -> str:
    """Plain ASCII-friendly punctuation, so pasted bullets stay ATS-readable."""
    return " ".join(text.translate(_TYPO_MAP).split())


def _first_word(text: str) -> str:
    match = _FIRST_WORD.match(_LABEL_PREFIX.sub("", text, count=1).lstrip())
    return match.group(0).lower() if match else ""


def _adds_impact_claim(original: str, rewrite: str) -> bool:
    """True if the rewrite claims an improvement the original never mentioned."""
    low_original, low_rewrite = original.lower(), rewrite.lower()
    claims_now = any(stem in low_rewrite for stem in _IMPACT_STEMS)
    claimed_before = any(stem in low_original for stem in _IMPACT_STEMS)
    return claims_now and not claimed_before


def _numbers(text: str) -> set:
    return {n.replace(',', '') for n in _NUMBER.findall(text)}


def _introduces_new_numbers(original: str, rewrite: str) -> bool:
    """True if the rewrite has a number (outside [placeholders]) not in the original."""
    outside = _PLACEHOLDER.sub(' ', rewrite)
    return not _numbers(outside) <= _numbers(original)


def _is_cosmetic(original: str, rewrite: str) -> bool:
    """A reword of a bullet that already starts well, with no placeholder, is not worth showing."""
    if _PLACEHOLDER.search(rewrite):
        return False
    first = _first_word(original)
    already_strong = first in ACTION_VERBS and first not in _BANNED_STARTS
    ratio = difflib.SequenceMatcher(None, original.lower(), rewrite.lower()).ratio()
    return already_strong and ratio >= 0.85


def _acceptable(original: str, rewrite: str) -> bool:
    if not rewrite or rewrite.lower() == original.lower():
        return False
    if _introduces_new_numbers(original, rewrite):
        logger.warning("Dropped a rewrite that introduced a new number")
        return False
    if _adds_impact_claim(original, rewrite):
        logger.warning("Dropped a rewrite that added an improvement claim")
        return False
    first, original_first = _first_word(rewrite), _first_word(original)
    ongoing = first.endswith('ing') and original_first.endswith('ing')     # "Exploring ..." stays ongoing
    if first in _BANNED_STARTS or (first not in ACTION_VERBS and not ongoing):
        return False
    return not _is_cosmetic(original, rewrite)


def _clean_ideas(value) -> List[str]:
    """Up to 3 short things to measure. Anything containing a digit is dropped."""
    if not isinstance(value, list):
        return []
    ideas = []
    for entry in value:
        text = _normalize(str(entry))
        if text and len(text) <= 80 and not re.search(r"\d", text):
            ideas.append(text)
    return ideas[:3]


@timed('bullet_rewrite')
def rewrite_bullets(bullets: List[str]) -> List[Dict]:
    """Rewrite up to MAX_BULLETS bullets. Each result has the original, a rewrite (empty if the
    wording is already fine or the rewrite was unsafe), a short note, and ideas for what to measure."""
    cleaned = [b.strip()[:MAX_BULLET_CHARS] for b in bullets if isinstance(b, str) and b.strip()]
    cleaned = cleaned[:MAX_BULLETS]
    if not cleaned:
        return []

    numbered = "\n".join(f"{i}. {b}" for i, b in enumerate(cleaned, 1))
    verbs = ", ".join(v.capitalize() for v in _PREFERRED_VERBS)
    prompt = REWRITE_USER_PROMPT.format(numbered=numbered, verbs=verbs)

    client = _get_client()
    parsed = _try_parse_json(_call_groq(client, REWRITE_SYSTEM_PROMPT, prompt))
    if parsed is None:
        strict = ("Your previous response was not valid JSON. Return ONLY the raw JSON "
                  "object.\n\n" + prompt)
        parsed = _try_parse_json(_call_groq(client, REWRITE_SYSTEM_PROMPT, strict))
    if parsed is None or not isinstance(parsed.get('rewrites'), list):
        raise ValueError("The AI service returned an unreadable response.")

    results = []
    for original, item in zip(cleaned, parsed['rewrites']):
        if not isinstance(item, dict):
            continue
        rewrite = _normalize(str(item.get('rewrite') or ''))
        note = _normalize(str(item.get('note') or ''))[:120]
        if not _acceptable(original, rewrite):
            rewrite, note = '', ''
        ideas = _clean_ideas(item.get('measure_ideas'))
        if rewrite or ideas:
            results.append({'original': original, 'rewrite': rewrite, 'note': note, 'ideas': ideas})
    return results
