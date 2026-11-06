"""Spelling and basic writing check for resume text.

Returns the same dictionary shape that get_default_grammar_results() returns, so the
scorer, the issue list and the recommendation engine can use it without changes.

What it checks
  critical : misspelled lowercase words (words that are not in the dictionary)
  moderate : repeated words ("the the") and a lowercase pronoun "i"
  minor    : a missing space after a period or comma ("model.Then")

What it deliberately does not check
  Capitalised words, ALL CAPS words, camelCase words, words with digits, hyphenated
  parts, URLs and e-mail addresses. That keeps names, brands and technologies from
  being flagged as spelling mistakes. This is a spelling check, not a full grammar check.
"""

import logging
import re
import time
from typing import Dict, List, Optional, Set

from spellchecker import SpellChecker

logger = logging.getLogger('ats_resume_scorer')

MAX_REPORTED = 25          # keep the work and the report small
MAX_WORD_LEN = 17          # longer tokens are usually words glued together by PDF extraction
TIME_BUDGET_SECONDS = 2.0  # stop looking for suggestions after this long

# Lowercase words that show up in technical resumes but are missing from a general dictionary.
TECH_TERMS = frozenset("""
api apis backend frontend fullstack dataset datasets preprocessing postprocessing hyperparameter
hyperparameters microservice microservices devops dockerized containerized containerised
regex json yaml sql nosql javascript typescript python numpy pandas scipy sklearn tensorflow pytorch
keras kubernetes docker github gitlab bitbucket jira postman linux unix bash webapp app apps
chatbot chatbots llm llms nlp cnn cnns rnn rnns lstm lstms gan gans bert gpt transformers
embeddings embedding tokenization tokenizer tokenizers autograd backpropagation ensemble ensembles
xgboost lightgbm catboost etl elt cicd oauth jwt http https html css json xml csv pdf docx
mlops dataops analytics dashboards dashboard visualizations visualization workflow workflows
frontend frameworks framework opensource async asyncio middleware endpoint endpoints serverless
multithreading multiprocessing uptime latency throughput scalability usability cybersecurity
hackathon hackathons webinar webinars upskill upskilling multimodal stakeholder stakeholders
""".split())

_PREFIXES = ('under', 'over', 're', 'pre', 'non', 'multi', 'sub', 'co', 'anti', 'inter', 'semi', 'auto', 'cross')
_SUFFIXES = ('s', 'es', 'ed', 'd', 'ing', 'ly', 'er', 'ers', 'ion', 'ions', 'ment', 'ments', 'ness')
_E_DROPPING = ('ed', 'ing', 'er', 'ers', 'ion', 'ions')   # make -> making, create -> creation

_URL_EMAIL = re.compile(
    r'\S+@\S+|https?://\S+|www\.\S+|\b[\w-]+\.(?:com|org|io|dev|net|in|ai|co)\b\S*', re.IGNORECASE)
# a lowercase word of 4+ letters that is not part of a longer token (digits, hyphens, dots, slashes)
_WORD = re.compile(r"(?<![\w@/.#+\-])([a-z][a-z'\u2019]{3,%d})(?![\w@/#+\-]|\.\w)" % (MAX_WORD_LEN - 1))
_REPEATED = re.compile(r"\b([A-Za-z]{3,})\s+\1\b", re.IGNORECASE)
_LOWER_I = re.compile(
    r"(?<![\w'.\-/])i(?=\s+(?:am|have|had|was|worked|built|developed|led|like|can|will|would|created|designed|implemented)\b)")
_MISSING_SPACE = re.compile(r"\b[a-z]{3,}[.,;][A-Z][a-z]{2,}\b")

_spell: Optional[SpellChecker] = None


def _get_spell() -> SpellChecker:
    global _spell
    if _spell is None:
        _spell = SpellChecker(language='en', distance=1)   # distance 2 can take seconds per long word
    return _spell


def _known_by_affix(word: str, spell: SpellChecker) -> bool:
    """True for valid derived words the dictionary lacks: 'underpriced', 'dockerizing'."""
    for prefix in _PREFIXES:
        if word.startswith(prefix) and len(word) - len(prefix) >= 4 and spell.known([word[len(prefix):]]):
            return True
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            stem = word[:-len(suffix)]
            if spell.known([stem]) or (suffix in _E_DROPPING and spell.known([stem + 'e'])):
                return True
    return False


def _context_words(parsed_resume: Optional[Dict]) -> Set[str]:
    """Words the candidate wrote in skills, titles and technology lists are never flagged."""
    words: Set[str] = set()
    if not parsed_resume:
        return words

    def add(value):
        if isinstance(value, str):
            words.update(w.lower() for w in re.findall(r"[A-Za-z][A-Za-z']*", value))
        elif isinstance(value, (list, tuple)):
            for v in value:
                add(v)
        elif isinstance(value, dict):
            for v in value.values():
                add(v)

    for key in ('skills', 'keywords', 'projects', 'experience', 'education'):
        add(parsed_resume.get(key))
    return words


def check_grammar(text: str, parsed_resume: Optional[Dict] = None) -> Dict:
    spell = _get_spell()
    allowed = TECH_TERMS | _context_words(parsed_resume)
    cleaned = _URL_EMAIL.sub(' ', text or '')
    word_count = max(len(re.findall(r"[A-Za-z']+", cleaned)), 1)

    # ---- critical: possible spelling mistakes -------------------------------------------
    candidates = {m.group(1).replace('\u2019', "'") for m in _WORD.finditer(cleaned)}
    unknown = sorted(w for w in spell.unknown(candidates)
                     if w not in allowed and not _known_by_affix(w, spell))
    critical: List[Dict] = []
    deadline = time.perf_counter() + TIME_BUDGET_SECONDS
    for word in unknown[:MAX_REPORTED]:
        if time.perf_counter() < deadline:
            suggestions = [s for s in (spell.candidates(word) or []) if s != word][:3]
        else:
            suggestions = []
        critical.append({
            'error_text': word,
            'message': 'Possible spelling mistake',
            'suggestions': suggestions,
        })

    # ---- moderate: repeated words, lowercase 'i' -----------------------------------------
    moderate: List[Dict] = []
    for m in _REPEATED.finditer(cleaned):
        moderate.append({'error_text': m.group(0), 'message': 'Repeated word',
                         'suggestions': [m.group(1)]})
    for m in _LOWER_I.finditer(cleaned):
        moderate.append({'error_text': 'i', 'message': "The pronoun 'I' should be capitalized",
                         'suggestions': ['I']})
    moderate = moderate[:MAX_REPORTED]

    # ---- minor: missing space after punctuation ------------------------------------------
    minor = [{'error_text': m.group(0), 'message': 'Add a space after the punctuation mark',
              'suggestions': []} for m in _MISSING_SPACE.finditer(cleaned)][:MAX_REPORTED]

    total = len(critical) + len(moderate) + len(minor)
    penalty = min(20.0, 4.0 * len(critical) + 2.0 * len(moderate) + 0.5 * len(minor))

    return {
        'total_errors':          total,
        'critical_errors':       critical,
        'moderate_errors':       moderate,
        'minor_errors':          minor,
        'grammar_score':         max(0, round(100 - penalty * 5)),
        'penalty_applied':       penalty,
        'error_free_percentage': round(max(0.0, 100.0 * (1 - total / word_count)), 1),
        '_component_status':     'available',
    }
