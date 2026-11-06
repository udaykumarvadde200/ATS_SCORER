from backend.utils.timing import timed
import re
import spacy
import numpy as np
from sentence_transformers import SentenceTransformer
from typing import Dict, List, Optional, Tuple

from backend.utils.file_utils import log_warning
from backend.core.config import SENTENCE_TRANSFORMER_MODEL
from backend.utils.matching import fuzzy_match_keywords

# A bare 5-digit number is NOT a ZIP code: it also matches chunks of phone numbers
# ("98765 43210") and metrics ("10000 records"). Require a clear postal context.
ZIP_CODE_PATTERN = (
    r'\b[A-Z]{2},?\s+\d{5}(?:-\d{4})?\b'                          # CA 94105
    r'|\b(?:PIN|Pin|pin|ZIP|Zip|zip)(?:\s*code)?[\s:.\-]*\d{5,6}\b'    # PIN 500081
    r'|\b[A-Z][a-z]{2,}\s*[-,]\s*[1-9]\d{5}\b'                       # Hyderabad - 500081
)

STREET_ADDRESS_PATTERN = (
    r'\b\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+'
    r'(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Circle|Cir|Way|Place|Pl)\b'
)

def _tier_score(n: float, tiers:list)-> float:
    for threshold, pts in tiers:
        if n>=threshold:
            return pts
    
    return 0.0

#Location/privacy detection
@timed('location_check')
def detect_location_info(text: str, nlp: spacy.Language) -> Dict:
    locations = []

    #method01: spacy NER
    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_ in ['GPE', 'LOC']:
            locations.append({'text': ent.text, 'type': ent.label_.lower(), 'start': ent.start_char})

    #moetod02: street address regx
    for match in re.finditer(STREET_ADDRESS_PATTERN, text, re.IGNORECASE):
        locations.append({'text': match.group(), 'type': 'address', 'start': match.start()})

    #method03: ZIP/PIN CODE REGEX PATTERN
    for match in re.finditer(ZIP_CODE_PATTERN, text):
        locations.append({'text': match.group(), 'type': 'zip', 'start': match.start()})

    has_address = any(loc['type'] == 'address' for loc in locations)
    has_zip     = any(loc['type'] == 'zip'     for loc in locations)

    if has_address and has_zip:
        privacy_risk, penalty = 'high', 5.0
    elif has_address or has_zip:
        privacy_risk, penalty = 'high', 4.0
    elif len({loc['text'].lower() for loc in locations}) > 3:
        privacy_risk, penalty = 'medium', 2.0
    elif locations:
        # "City, State" in the header is normal and recommended: no penalty.
        privacy_risk, penalty = 'low', 0.0
    else:
        privacy_risk, penalty = 'none', 0.0

    recommendations = []
    if not locations:
        recommendations.append(" No privacy concerns detected.")
    if has_address:
        recommendations.append(" Remove full street addresses — ATS systems don't need this and it's a privacy risk.")
    if has_zip:
        recommendations.append(" Remove zip codes — this level of location detail is unnecessary.")
    if privacy_risk in ('low', 'medium') and not has_address and not has_zip:
        recommendations.append(" Consider reducing location mentions. 'City, State' in the contact header is sufficient.")

    return {
        'location_found':     len(locations) > 0,
        'detected_locations': locations,
        'privacy_risk':       privacy_risk,
        'recommendations':    recommendations,
        'penalty_applied':    penalty,
    }

def _calculate_semantic_similarity(skill: str, text: str, embedder: SentenceTransformer) -> float:
    #similarity = (A · B) / (|A| × |B|)
    if not skill or not text:
        return 0.0
    try:
        skill_vec  = embedder.encode(skill, convert_to_tensor=False)
        text_vec   = embedder.encode(text,  convert_to_tensor=False)

        similarity = np.dot(skill_vec, text_vec) / (
            np.linalg.norm(skill_vec) * np.linalg.norm(text_vec)
        )

        return float(max(0.0, min(1.0, similarity)))
    except Exception as e:
        log_warning(f"Similarity error for '{skill}': {e}", context='ats_scorer')
        return 0.0

def _skill_in_text(skill: str, text: str) -> bool:
    """Whole-token match, so 'C' or 'R' don't match every word containing that
    letter, and 'Java' doesn't match 'JavaScript'. Handles C++, C#, Node.js."""
    s = skill.strip().lower()
    if not s:
        return False
    pattern = r'(?<![a-z0-9+#])' + re.escape(s) + r'(?![a-z0-9+#])'
    return re.search(pattern, text.lower()) is not None


def _skill_matches(skill: str, text: str, embedder: SentenceTransformer, threshold: float) -> Tuple[bool, float]:

    # fast path: exact whole-token match
    if _skill_in_text(skill, text):
        return True, 1.0

    # embeddings of 1-2 character skills are meaningless
    if len(skill.strip()) <= 2:
        return False, 0.0

    #slow, semantic similarity check using sentence embeddings
    sim = _calculate_semantic_similarity(skill, text, embedder)
    return sim >= threshold, sim

#Skill validation
@timed('skill_validation')
def validate_skills_with_projects(
    skills: List[str],
    projects: List[Dict],
    experience_entries: List[Dict],
    embedder: SentenceTransformer,
    threshold: float = 0.6,
) -> Dict:
    skills = [str(s).strip() for s in (skills or []) if s and str(s).strip()]
    if not skills:
        return {
            'validated_skills':      [],
            'unvalidated_skills':    [],
            'validation_percentage': 0.0,
            'skill_project_mapping': {},
            'validation_score':      0.0,
        }

    experience_text = ' '.join(
        f"{e.get('job_title', '')} {e.get('company', '')} {e.get('description', '')}"
        for e in (experience_entries or [])
        if isinstance(e, dict)
    ).strip()

    # (label, text) for every place a skill can be backed up
    sources = []
    for project in (projects or []):
        if not isinstance(project, dict):
            continue
        label = project.get('title') or 'Untitled Project'
        tech = project.get('technologies') or []
        if not isinstance(tech, list):
            tech = [tech]
        tech_text = ' '.join(str(t) for t in tech)
        text = f"{project.get('title', '')} {project.get('description', '')} {tech_text}".strip()
        if text:
            sources.append((label, text))
    if experience_text:
        sources.append(('Experience Section', experience_text))

    # Embed every skill and every source once (two batches) instead of once per pair
    skill_vecs = src_vecs = None
    if sources:
        try:
            skill_vecs = embedder.encode(skills, convert_to_numpy=True, normalize_embeddings=True)
            src_vecs = embedder.encode(
                [t for _, t in sources], convert_to_numpy=True, normalize_embeddings=True
            )
        except Exception as e:
            log_warning(f'Embedding failed, using exact matches only: {e}', context='ats_scorer')
            skill_vecs = src_vecs = None

    validated_skills, unvalidated_skills, skill_project_mapping = [], [], {}

    for i, skill in enumerate(skills):
        matching, max_sim = [], 0.0
        for j, (label, text) in enumerate(sources):
            if _skill_in_text(skill, text):
                matched, sim = True, 1.0
            elif len(skill) <= 2 or skill_vecs is None:
                matched, sim = False, 0.0
            else:
                sim = float(np.clip(np.dot(skill_vecs[i], src_vecs[j]), 0.0, 1.0))
                matched = sim >= threshold
            max_sim = max(max_sim, sim)
            if matched and label not in matching:
                matching.append(label)

        if matching:
            validated_skills.append({'skill': skill, 'projects': matching, 'similarity': max_sim})
            skill_project_mapping[skill] = matching
        else:
            unvalidated_skills.append(skill)
            skill_project_mapping[skill] = []

    validation_percentage = len(validated_skills) / len(skills)
    return {
        'validated_skills':      validated_skills,
        'unvalidated_skills':    unvalidated_skills,
        'validation_percentage': validation_percentage,
        'skill_project_mapping': skill_project_mapping,
        'validation_score':      validation_percentage * 15.0,
    }


def _calc_formatting_score(parsed_resume: Dict, text: str) -> float:

    score = 0.0

    exp_entries  = [e for e in parsed_resume.get('experience', []) if isinstance(e, dict)]
    edu_entries  = [e for e in parsed_resume.get('education', [])  if isinstance(e, dict)]
    skills       = parsed_resume.get('skills', [])
    summary      = parsed_resume.get('professional_summary', '')
    proj_entries = [p for p in parsed_resume.get('projects', [])   if isinstance(p, dict)]

    if exp_entries and any(e.get('job_title') or e.get('description') for e in exp_entries):
        score += 3.0
    if edu_entries:
        score += 2.0
    if len(skills) >= 3:
        score += 2.0
    if len(summary) > 30:
        score += 1.5
    if proj_entries:
        score += 1.5

    bullet_count = sum(
        1 for line in text.split('\n')
        if re.match(r'^\s*[•\-\*\◦]', line) or re.match(r'^\s*\d+\.', line)
    )
    score += _tier_score(bullet_count, [(15,5.0),(10,4.0),(5,3.0),(3,2.0),(1,1.0)])

    filled = sum(1 for has_it in [
        bool(exp_entries), bool(edu_entries), bool(skills),
        bool(summary.strip()), bool(proj_entries),
    ] if has_it)
    score += _tier_score(filled, [(4,5.0),(3,4.0),(2,3.0),(1,2.0)])

    return min(20.0, max(0.0, score))

#02 keyword score
def _calc_keywords_score(
    resume_keywords: List[str],
    skills: List[str],
    jd_keywords: Optional[List[str]] = None,
) -> float:
    score = 0.0

    score += _tier_score(len(resume_keywords), [(20,10.0),(15,8.0),(10,6.0),(5,4.0),(3,2.0)])
    score += _tier_score(len(skills),          [(15,10.0),(10,8.0),(7,6.0),(5,4.0),(3,2.0)])

    if jd_keywords:
        all_resume_terms = list(set(resume_keywords + skills))
        fuzzy_result     = fuzzy_match_keywords(all_resume_terms, jd_keywords, threshold=80)
        match_pct        = len(fuzzy_result['matched']) / len(jd_keywords) if jd_keywords else 0
        score += _tier_score(match_pct, [(0.7,5.0),(0.5,4.0),(0.3,3.0),(0.2,2.0),(0.1,1.0)])
    
    elif len(resume_keywords) >= 10:
        score += 3.0

    return min(25.0, max(0.0, score))

#3. CONTENT QUALITY SCORE
def _calc_content_score(
    text: str,
    action_verbs: List[str],
    grammar_results: Dict,
) -> float:
    
    score = 0.0

    score += _tier_score(len(action_verbs), [(15,10.0),(10,8.0),(7,6.0),(5,4.0),(3,2.0)])

    number_patterns = [
        r'\d+%',
        r'\$\d+',
        r'\d+[kKmMbB]',
        r'\d+\s*(?:users|customers|clients|projects|hours|days|months|years)',
        r'(?:increased|decreased|improved|reduced|grew|saved)\s+(?:by\s+)?\d+',
    ]
    achievement_count = sum(len(re.findall(p, text, re.IGNORECASE)) for p in number_patterns)
    score += _tier_score(achievement_count, [(10,5.0),(7,4.0),(5,3.0),(3,2.0),(1,1.0)])

    if grammar_results.get('_component_status') == 'unavailable':
        # No spelling check ran: rescale the 15 measurable points to the full 25.
        score = score * 25.0 / 15.0
    else:
        # Spelling is worth 5 points; the other 15 measurable points are rescaled to 20.
        grammar_penalty = grammar_results.get('penalty_applied', 0.0)
        score = score * 20.0 / 15.0 + max(0.0, 5.0 - grammar_penalty / 4.0)

    return min(25.0, max(0.0, score))

#4. SKILL VALIDATION SCORE
def _calc_skill_validation_score(validation_results: Dict) -> float:
    return min(15.0, max(0.0, validation_results.get('validation_score', 0.0)))

#5. ATS COMPATIBILITY SCORE
# ---------------------------------------------------------------------------
# ATS compatibility: can a machine read this resume?  (0 to 15)
# Points are EARNED by passing checks on the raw extracted text.
# ---------------------------------------------------------------------------
_HEADING_PATTERNS = {
    'summary':        r'summary|professional summary|objective|career objective|profile|about me',
    'experience':     r'experience|work experience|professional experience|employment|employment history|internships?',
    'education':      r'education|academic background|academics',
    'skills':         r'skills|technical skills|key skills|core skills|technologies|tech stack',
    'projects':       r'projects?|personal projects?|academic projects?',
    'certifications': r'certifications?|certificates|achievements|awards',
}
_HEADING_RES = {
    name: re.compile(rf'^\s*(?:{pattern})\s*:?\s*$', re.IGNORECASE)
    for name, pattern in _HEADING_PATTERNS.items()
}
_EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
_PHONE_RE = re.compile(r'(?:\+\d{1,3}[\s-]?)?\d[\d\s().-]{8,16}\d')
_LINK_RE = re.compile(r'linkedin\.com|github\.com', re.IGNORECASE)
_ARTIFACT_RE = re.compile('[\ufffd\ue000-\uf8ff\x00-\x08\x0b\x0c\x0e-\x1f]')
_MONTH_YEAR_RE = re.compile(
    r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(?:19|20)\d{2}\b',
    re.IGNORECASE)
_NUMERIC_DATE_RE = re.compile(r'\b(?:0?[1-9]|1[0-2])/(?:19|20)\d{2}\b')
_YEAR_RANGE_RE = re.compile(r'\b(?:19|20)\d{2}\s*[-\u2013to]+\s*(?:(?:19|20)\d{2}|present|current)\b', re.IGNORECASE)


def _calc_ats_compatibility_score(
    text: str,
    location_results: Dict,
    parsed_resume: Dict,
) -> float:
    score = 0.0

    # 1. Enough text came out of the file (0-3). Scanned or image-only PDFs fail here.
    n = len(text.strip())
    score += 3.0 if n >= 1500 else 2.0 if n >= 800 else 1.0 if n >= 300 else 0.0

    # 2. Standard section headings an ATS looks for (0-4).
    lines = [line for line in text.split('\n') if 0 < len(line.strip()) <= 40]
    found = sum(1 for rx in _HEADING_RES.values() if any(rx.match(line) for line in lines))
    score += 4.0 if found >= 4 else float(found)

    # 3. Contact details are machine-readable (0-3).
    if _EMAIL_RE.search(text):
        score += 1.5
    if any(sum(ch.isdigit() for ch in m.group()) >= 10 for m in _PHONE_RE.finditer(text)):
        score += 1.0
    if _LINK_RE.search(text):
        score += 0.5

    # 4. Clean extraction: few broken or private-use characters (0-3).
    artifacts = len(_ARTIFACT_RE.findall(text))
    per_1000 = artifacts / max(len(text), 1) * 1000
    if n >= 300:                                   # nothing to judge in an empty or image-only file
        score += 3.0 if artifacts == 0 else 2.0 if per_1000 <= 2 else 1.0 if per_1000 <= 5 else 0.0

    # 5. Dates present and written in one style (0-2).
    month_year = len(_MONTH_YEAR_RE.findall(text))
    numeric = len(_NUMERIC_DATE_RE.findall(text))
    ranges = len(_YEAR_RANGE_RE.findall(text))
    if month_year + numeric + ranges >= 2:
        score += 1.0
        if not (month_year and numeric):          # not mixing 'Jun 2024' with '06/2024'
            score += 1.0

    score -= location_results.get('penalty_applied', 0.0)
    return min(15.0, max(0.0, score))


@timed('scoring')
def calculate_overall_score(
    text: str,
    parsed_resume: Dict,
    skills: List[str],
    keywords: List[str],
    action_verbs: List[str],
    skill_validation_results: Dict,
    grammar_results: Dict,
    location_results: Dict,
    jd_keywords: Optional[List[str]] = None,
    experience_months: int = 0,
) -> Dict:

    formatting_score        = _calc_formatting_score(parsed_resume, text)
    keywords_score          = _calc_keywords_score(keywords, skills, jd_keywords)
    content_score           = _calc_content_score(text, action_verbs, grammar_results)
    skill_validation_score  = _calc_skill_validation_score(skill_validation_results)
    ats_compatibility_score = _calc_ats_compatibility_score(text, location_results, parsed_resume)
    # Skills that no project or job backs up should not earn full keyword credit.
    if skills:
        evidence = float(skill_validation_results.get('validation_percentage', 0.0))
        keywords_score = keywords_score * (0.5 + 0.5 * evidence)
    # Round each component to a whole number first so the headline score
    # always equals the sum of the numbers shown in the breakdown.
    formatting_score        = float(round(formatting_score))
    keywords_score          = float(round(keywords_score))
    content_score           = float(round(content_score))
    skill_validation_score  = float(round(skill_validation_score))
    ats_compatibility_score = float(round(ats_compatibility_score))

    COMPONENT_MAX = {
        'formatting': 20.0, 'keywords': 25.0, 'content': 25.0,
        'skill_validation': 15.0, 'ats_compatibility': 15.0,
    }

    formatting_pct        = (formatting_score        / COMPONENT_MAX['formatting'])        * 100.0
    keywords_pct          = (keywords_score          / COMPONENT_MAX['keywords'])          * 100.0
    content_pct           = (content_score           / COMPONENT_MAX['content'])           * 100.0
    skill_validation_pct  = (skill_validation_score  / COMPONENT_MAX['skill_validation'])  * 100.0
    ats_compatibility_pct = (ats_compatibility_score / COMPONENT_MAX['ats_compatibility']) * 100.0

    # Overall = sum of the five displayed components (20+25+25+15+15 = 100), so the
    # headline score always matches the breakdown (and the weights on the landing page).
    base_score = (
        formatting_score + keywords_score + content_score
        + skill_validation_score + ats_compatibility_score
    )

    penalties = {}
    bonuses   = {}
    score     = base_score

    if grammar_results.get('penalty_applied', 0.0) > 0:
        penalties['grammar'] = grammar_results['penalty_applied']

    if location_results.get('penalty_applied', 0.0) > 0:
        penalties['location_privacy'] = location_results['penalty_applied']

    validation_pct = skill_validation_results.get('validation_percentage', 0.0)
    if validation_pct >= 0.9:
        bonuses['excellent_skill_validation'] = 2.0
        score += 2.0
    elif validation_pct >= 0.8:
        bonuses['good_skill_validation'] = 1.0
        score += 1.0

    if (grammar_results.get('total_errors', 0) == 0
            and grammar_results.get('_component_status') != 'unavailable'):
        bonuses['perfect_grammar'] = 1.0
        score += 1.0

    if jd_keywords and len(jd_keywords) > 0:
        all_resume_terms = list(set((keywords or []) + (skills or [])))
        fuzzy_result     = fuzzy_match_keywords(all_resume_terms, jd_keywords, threshold=80)
        missing_pct      = len(fuzzy_result['missing']) / len(jd_keywords)

        if missing_pct > 0.7:
            penalties['missing_jd_keywords'] = 15.0
            score -= 15.0
        elif missing_pct > 0.5:
            penalties['missing_jd_keywords'] = 10.0
            score -= 10.0
        elif missing_pct > 0.3:
            penalties['missing_jd_keywords'] = 5.0
            score -= 5.0

    overall_score = min(100.0, max(0.0, score))
    interpretation = _generate_score_interpretation(overall_score)

    return {
        'overall_score':           round(overall_score, 1),
        'formatting_score':        round(formatting_score, 1),
        'keywords_score':          round(keywords_score, 1),
        'content_score':           round(content_score, 1),
        'skill_validation_score':  round(skill_validation_score, 1),
        'ats_compatibility_score': round(ats_compatibility_score, 1),
        'overall_interpretation':  interpretation,
        'penalties':               penalties,
        'bonuses':                 bonuses,}

#Overall score calculation and interpretation
def generate_strengths(
    score_results: Dict,
    skill_validation_results: Dict,
    grammar_results: Dict,
) -> List[str]:

    strengths = []

    if score_results['formatting_score']       >= 16:
        strengths.append(' Well-structured with clear sections and bullet points')
    if score_results['keywords_score']          >= 20:
        strengths.append(' Strong keyword optimization and skills presence')
    if score_results['content_score']           >= 20:
        strengths.append(' Excellent use of action verbs and quantifiable achievements')
    if score_results['skill_validation_score']  >= 12:
        pct = skill_validation_results.get('validation_percentage', 0) * 100
        strengths.append(f' {pct:.0f}% of skills are validated by projects')
    if score_results['ats_compatibility_score'] >= 13:
        strengths.append(' Excellent ATS compatibility with clean formatting')
    if (grammar_results.get('total_errors', 0) == 0
            and grammar_results.get('_component_status') != 'unavailable'):
        strengths.append(' Error-free grammar and spelling')

    if not strengths:
        strengths.append('Your resume has potential - focus on the recommendations below')
    return strengths


#Critical issues that could cause ATS rejection
def generate_critical_issues(
    score_results: Dict,
    grammar_results: Dict,
    location_results: Dict,
) -> List[str]:
    issues = []

    critical_errors = len(grammar_results.get('critical_errors', []))
    if critical_errors > 0:
        issues.append(f' {critical_errors} critical grammar/spelling error(s) detected')
    if location_results.get('privacy_risk') == 'high':
        issues.append('High privacy risk: Remove detailed location information')
    if score_results['formatting_score']       < 10:
        issues.append(' Poor formatting: Add clear sections and bullet points')
    if score_results['keywords_score']         < 12:
        issues.append(' Insufficient keywords and skills')
    if score_results['skill_validation_score'] < 7:
        issues.append(' Most skills lack supporting evidence in projects')

    return issues


#Actionable improvements to enhance ATS performance
def generate_improvements(
    score_results: Dict,
    skill_validation_results: Dict,
) -> List[str]:
    improvements = []

    if 12 <= score_results['formatting_score']       < 16:
        improvements.append('Add more bullet points and improve section organization')
    if 14 <= score_results['keywords_score']          < 20:
        improvements.append('Include more relevant keywords and technical skills')
    if 14 <= score_results['content_score']           < 20:
        improvements.append('Add more quantifiable achievements and action verbs')
    if 7  <= score_results['skill_validation_score']  < 12:
        unvalidated_count = len(skill_validation_results.get('unvalidated_skills', []))
        improvements.append(f'Validate {unvalidated_count} skill(s) by adding relevant project details')
    if 9  <= score_results['ats_compatibility_score'] < 13:
        improvements.append('Simplify formatting for better ATS compatibility')

    return improvements

#Interpretation of overall score
def _generate_score_interpretation(overall_score: float) -> str:
    if overall_score >= 90:    return 'Excellent! Your resume is highly optimized for ATS systems.'
    elif overall_score >= 80:  return 'Great! Your resume should perform well with most ATS systems.'
    elif overall_score >= 70:  return 'Good! Your resume is ATS-friendly with room for minor improvements.'
    elif overall_score >= 60:  return 'Fair. Your resume needs some improvements to be fully ATS-compatible.'
    elif overall_score >= 50:  return 'Below Average. Significant improvements needed for ATS compatibility.'
    else:                      return 'Poor. Your resume requires major revisions to pass ATS screening.'