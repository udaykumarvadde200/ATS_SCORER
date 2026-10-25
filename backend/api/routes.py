import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool

from pydantic import BaseModel
from backend.api.auth import get_current_user
from backend.models.schemas import AnalysisResponse, ComponentScores, JDComparison, SkillValidationDetails
from backend.utils.file_utils import (
    get_default_grammar_results,
    get_default_location_results,
    get_default_skill_validation_results,
)

logger = logging.getLogger('ats_resume_scorer')

router = APIRouter(prefix='/api/v1', tags=['Analysis'])


def _clean(text: str) -> str:
    for prefix in ('✅', '🌟', '❌', '⚠️', '📝', '🔴', '🟡', '🟢', '🟠', '👍'):
        text = text.lstrip(prefix)
    return text.strip()


def _fb_field(fb, name: str) -> str:
    """Read a field from an IssueDetail that may be a dict or a Pydantic object."""
    if isinstance(fb, dict):
        return fb.get(name) or ''
    return getattr(fb, name, '') or ''


_SEVERITY_ALIASES = {'moderate': 'medium', 'info': 'low'}


def _normalize_feedback(detailed_fb) -> list:
    """feedback_engine emits 'High' / 'Moderate' / 'Low'. The UI and PDF expect
    lowercase critical/high/medium/low; 'moderate' used to be dropped from the
    Detailed Feedback page entirely."""
    normalized = []
    for fb in detailed_fb:
        data = dict(fb) if isinstance(fb, dict) else fb.model_dump()
        level = (data.get('severity_level') or 'low').lower()
        data['severity_level'] = _SEVERITY_ALIASES.get(level, level)
        normalized.append(data)
    return normalized


def _critical_issue_titles(detailed_fb) -> List[str]:
    return [
        _fb_field(fb, 'issue_title')
        for fb in detailed_fb
        if _fb_field(fb, 'severity_level').lower() in ('critical', 'high')
        and _fb_field(fb, 'issue_title')
    ]


def _build_suggestions(detailed_fb, limit: int = 8) -> List[str]:
    """Short list of 'how to fix' tips, most severe issues first, no duplicates."""
    rank = {'critical': 0, 'high': 1, 'medium': 2, 'moderate': 2, 'low': 3}
    ordered = sorted(
        detailed_fb,
        key=lambda fb: rank.get(_fb_field(fb, 'severity_level').lower(), 99),
    )
    suggestions: List[str] = []
    for fb in ordered:
        tip = _fb_field(fb, 'how_to_fix').strip()
        if tip and tip not in suggestions:
            suggestions.append(tip)
        if len(suggestions) >= limit:
            break
    return suggestions


@router.post('/analyze-resume', response_model=AnalysisResponse)
async def analyze_resume(
    request: Request,
    resume: UploadFile = File(..., description='Resume file — PDF or DOCX, max 5 MB'),
    job_description: str = Form('', description='Job description text (optional)'),
    user_id: str = Depends(get_current_user),
):
    warnings: List[str] = []

    nlp = request.app.state.nlp
    embedder = request.app.state.embedder

    try:
        file_bytes = await resume.read()
        filename = resume.filename or 'resume'

        from backend.services.resume_parser import (
            FileParsingError,
            FileValidationError,
            parse_resume_file,
        )

        resume_text, _metadata = await run_in_threadpool(
            parse_resume_file, file_bytes, filename
        )
        logger.info(f"Parsed '{filename}': {len(resume_text)} chars extracted")

    except Exception as exc:
        logger.error(f'File parsing failed: {exc}')
        raise HTTPException(
            status_code=422,
            detail=f'Could not read or parse the resume: {exc}',
        )

    # Full analysis pipeline.
    # It makes blocking calls (Groq, embeddings, spaCy), so run it in a worker
    # thread; otherwise one analysis freezes every other request.
    try:
        from backend.services.resume_analyzer import analyze_full_resume

        result = await run_in_threadpool(
            analyze_full_resume,
            resume_text=resume_text,
            nlp=nlp,
            embedder=embedder,
            job_description=job_description,
        )
    except Exception as exc:
        logger.error(f'Full analysis pipeline failed: {exc}')
        raise HTTPException(status_code=500, detail=f'Analysis pipeline failed: {exc}')

    # Extract jd_comparison details
    jd_comparison_result = None
    if result.get('jd_comparison'):
        jd_comparison_result = JDComparison(
            match_percentage=round(float(result['jd_comparison'].get('match_percentage', 0.0)), 1),
            semantic_similarity=round(float(result['jd_comparison'].get('semantic_similarity', 0.0)), 3),
            matched_keywords=result['jd_comparison'].get('matched_keywords', [])[:20],
            missing_keywords=result['jd_comparison'].get('missing_keywords', [])[:15],
            skills_gap=result['jd_comparison'].get('skills_gap', [])[:10],
        )

    detailed_fb = _normalize_feedback(result.get('detailed_feedback', []) or [])

    svd_raw = result.get('skill_validation_details') or {}
    skill_val_details = SkillValidationDetails(
        validated=svd_raw.get('validated', []),
        unvalidated=svd_raw.get('unvalidated', []),
        total=svd_raw.get('total', 0),
        validated_count=svd_raw.get('validated_count', 0),
        validation_pct=svd_raw.get('validation_pct', 0.0),
    )

    # Fields the frontend reads directly. These were previously never sent,
    # which left Strengths / Critical Issues / Recommendations empty.
    strengths = result.get('strengths', []) or []
    critical_issues = _critical_issue_titles(detailed_fb)
    suggestions = _build_suggestions(detailed_fb)

    response = AnalysisResponse(
        ATS_score=result['ats_score'],
        component_scores=ComponentScores(**result['component_scores']),
        issues_summary=result['issues_summary'],
        detailed_feedback=detailed_fb,
        jd_match_analysis=jd_comparison_result,
        skill_validation_details=skill_val_details,

        # Retro-compatibility fields
        ats_score=result['ats_score'],
        keyword_match=jd_comparison_result.match_percentage if jd_comparison_result else 0.0,
        missing_keywords=result.get('missing_keywords', []),
        matched_keywords=result.get('matched_keywords', []),
        skills=list(result.get('skills', [])[:20]),
        jd_comparison=jd_comparison_result,
        interpretation=result.get('interpretation', ''),

        strengths=strengths,
        critical_issues=critical_issues,
        suggestions=suggestions,
        warnings=warnings,
        
        weak_bullets=result.get('weak_bullets', []),
    )

    # Save what the user actually sees, so History and its PDF match the
    # live result (strengths etc. included).
    try:
        from backend.database.supabase_db import save_analysis
        await save_analysis(user_id, filename, response.model_dump())
    except Exception as exc:
        logger.warning(f'History save failed (non-blocking): {exc}')

    return response


@router.get('/health')
async def health_check(request: Request):
    """Health check — confirms models are loaded and the API is ready."""
    return {
        'status': 'healthy',
        'nlp_loaded': request.app.state.nlp is not None,
        'embedder_loaded': request.app.state.embedder is not None,
    }


@router.get('/history')
async def get_history(user_id: str = Depends(get_current_user)):
    """Return the signed-in user's past analyses (identity comes from the JWT)."""
    from backend.database.supabase_db import get_user_history
    try:
        return await get_user_history(user_id)
    except Exception as exc:
        logger.error(f'History fetch failed: {exc}')
        raise HTTPException(status_code=500, detail=f'Could not load history: {exc}')


@router.delete('/history/{analysis_id}')
async def delete_history_entry(
    analysis_id: str,
    user_id: str = Depends(get_current_user),
):
    """Delete one analysis from the signed-in user's history."""
    from backend.database.supabase_db import delete_analysis
    try:
        success = await delete_analysis(analysis_id, user_id)
        if not success:
            raise HTTPException(status_code=404, detail='Analysis not found or not owned by this user.')
        return {'status': 'deleted', 'id': analysis_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f'History delete failed: {exc}')
        raise HTTPException(status_code=500, detail=f'Could not delete: {exc}')


@router.post('/generate-pdf')
async def generate_pdf(
    data: AnalysisResponse,
    user_id: str = Depends(get_current_user),
):
    from backend.services.report_generator import generate_html_reports
    from backend.services.pdf_export import generate_combined_pdf
    from fastapi.responses import Response

    try:
        html_docs = generate_html_reports(data.model_dump())
        pdf_bytes = await run_in_threadpool(generate_combined_pdf, html_docs)

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=ats_report.pdf"
            }
        )
    except Exception as e:
        logger.error(f'Failed to generate PDF: {e}')
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {e}")


@router.get('/history/{analysis_id}/pdf')
async def generate_history_pdf(
    analysis_id: str,
    user_id: str = Depends(get_current_user),
):
    from backend.database.supabase_db import get_user_history
    from backend.services.report_generator import generate_html_reports
    from backend.services.pdf_export import generate_combined_pdf
    from fastapi.responses import Response

    history = await get_user_history(user_id)
    analysis_data = next((item["analysis_result"] for item in history if item["id"] == analysis_id), None)

    if not analysis_data:
        raise HTTPException(status_code=404, detail="Analysis not found")

    try:
        html_docs = generate_html_reports(analysis_data)
        pdf_bytes = await run_in_threadpool(generate_combined_pdf, html_docs)

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=ats_report_{analysis_id}.pdf"
            }
        )
    except Exception as e:
        logger.error(f'Failed to generate PDF for history: {e}')
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {e}")



class ImproveBulletsRequest(BaseModel):
    bullets: List[str]


@router.post('/improve-bullets')
async def improve_bullets(
    body: ImproveBulletsRequest,
    user_id: str = Depends(get_current_user),
):
    """Rewrite weak resume bullets with the AI service (placeholders, no invented numbers)."""
    from backend.services.bullet_rewriter import rewrite_bullets

    bullets = [b for b in body.bullets[:10] if isinstance(b, str) and b.strip()]
    if not bullets:
        raise HTTPException(status_code=422, detail='No bullets were provided.')

    try:
        rewrites = await run_in_threadpool(rewrite_bullets, bullets)
    except Exception as exc:
        logger.error(f'Bullet rewrite failed: {exc}')
        raise HTTPException(
            status_code=502,
            detail='The AI service could not rewrite the bullets. Please try again.',
        )
    return {'rewrites': rewrites}