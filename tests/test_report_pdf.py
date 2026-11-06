import io
import sys
import types

import pdfplumber

from backend.services import report_pdf
from backend.services.report_pdf import build_report_pdf

ANALYSIS = {
    "ATS_score": 66.0, "ats_score": 66.0,
    "interpretation": "Fair. Your resume needs some improvements.",
    "component_scores": {"formatting": 15, "keywords": 23, "content": 7, "skill_validation": 6, "ats_compatibility": 15},
    "strengths": ["Education section is present"],
    "detailed_feedback": [
        {"issue_title": "Strengthen Your Resume", "severity_level": "Moderate", "ats_impact": "High",
         "explanation": "Most skills lack evidence.", "where_it_appears": "Skills", "how_to_fix": "Mention each skill.",
         "action_items": ["Mention 'SQL' in a bullet", "Mention 'OOP' in a bullet"], "example_improvement": ""}],
    "skill_validation_details": {"validated": [{"skill": "Python", "projects": ["RAG Platform"]}],
                                 "unvalidated": ["SQL", "OOP"], "total": 3, "validated_count": 1, "validation_pct": 33.3},
    "weak_bullets": [{"bullet": "Worked on the website for the team", "source": "Portfolio",
                      "issues": "no measurable result"}],
}


def text_and_pages(pdf_bytes):
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages), len(pdf.pages)


def test_report_contains_the_key_content_in_few_pages():
    text, pages = text_and_pages(build_report_pdf(ANALYSIS, filename="resume.pdf"))
    for expected in ("ATS Resume Report", "66", "out of 100", "Content Quality", "7/25", "Fix these first",
                     "Strengthen Your Resume", "Needs evidence", "Bullets to strengthen", "Your checklist"):
        assert expected in text
    assert pages <= 3


def test_job_description_section_appears_only_when_there_is_one():
    without, _ = text_and_pages(build_report_pdf(ANALYSIS))
    assert "Job description match" not in without
    with_jd = dict(ANALYSIS, jd_match_analysis={"match_percentage": 54.0, "semantic_similarity": 0.62,
                   "matched_keywords": ["python"], "missing_keywords": ["kubernetes"], "skills_gap": ["aws"]})
    text, _ = text_and_pages(build_report_pdf(with_jd))
    assert "Job description match" in text and "kubernetes" in text


def test_score_adjustment_is_explained():
    adjusted = dict(ANALYSIS, ATS_score=51.0, ats_score=51.0)       # components add up to 66
    text, _ = text_and_pages(build_report_pdf(adjusted))
    assert "penalty of 15 points" in text


def test_empty_and_odd_input_never_crash():
    for odd in ({}, {"component_scores": None, "detailed_feedback": [None, "x"], "strengths": [None]},
                {"ATS_score": "bad", "weak_bullets": [{"bullet": "x" * 5000}]}):
        assert build_report_pdf(odd).startswith(b"%PDF")


def test_special_characters_are_handled():
    odd = dict(ANALYSIS, strengths=["Uses <b>tags</b> & symbols \u2014 and \u2713 emoji \U0001F600"])
    assert build_report_pdf(odd).startswith(b"%PDF")


def test_falls_back_to_the_html_report_if_the_new_layout_fails(monkeypatch):
    monkeypatch.setattr(report_pdf, "_build_native", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    fake_gen = types.SimpleNamespace(generate_html_reports=lambda analysis: {"x": "<p>hi</p>"})
    fake_pdf = types.SimpleNamespace(generate_combined_pdf=lambda docs: b"%PDF-fallback")
    monkeypatch.setitem(sys.modules, "backend.services.report_generator", fake_gen)
    monkeypatch.setitem(sys.modules, "backend.services.pdf_export", fake_pdf)
    assert build_report_pdf(ANALYSIS) == b"%PDF-fallback"
