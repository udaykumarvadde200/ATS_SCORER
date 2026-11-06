"""Native PDF report (drawn directly with ReportLab, so it looks the same on every machine).

build_report_pdf(analysis) takes the analysis dictionary (an AnalysisResponse as a dict) and
returns PDF bytes. If anything goes wrong it falls back to the older HTML-based report, so a
download never fails because of the layout code.
"""

import io
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

logger = logging.getLogger('ats_resume_scorer')

NAVY = colors.HexColor('#1E293B')
INDIGO = colors.HexColor('#4F46E5')
SLATE = colors.HexColor('#64748B')
LIGHT = colors.HexColor('#F1F5F9')
LINE = colors.HexColor('#E2E8F0')
GREEN = colors.HexColor('#16A34A')
AMBER = colors.HexColor('#D97706')
RED = colors.HexColor('#DC2626')

PAGE_W = A4[0] - 32 * mm - 12     # usable width inside the frame padding

# component key -> (label, what it checks, maximum, advice when points are lost)
COMPONENTS = [
    ('formatting', 'Formatting', 'Sections, contact details, length', 20,
     'Add any missing standard sections and complete your contact details.'),
    ('keywords', 'Keywords & Skills', 'Keyword coverage, backed by evidence', 25,
     'List only skills you use, and mention each one in a project or job bullet.'),
    ('content', 'Content Quality', 'Action verbs, numbers, spelling', 25,
     'Start bullets with strong verbs, add real numbers, and fix any spelling mistakes.'),
    ('skill_validation', 'Skill Validation', 'Skills backed by project evidence', 15,
     'Name each listed skill in a project or experience bullet that shows how you used it.'),
    ('ats_compatibility', 'ATS Compatibility', 'Machine-readable structure', 15,
     'Use standard section headings, plain bullets and readable contact details.'),
]

_CHAR_MAP = str.maketrans({
    '\u2013': '-', '\u2014': '-', '\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"',
    '\u2022': '-', '\u2192': '->', '\u2026': '...', '\u00a0': ' ', '\u2011': '-', '\u2010': '-',
})


def _txt(value: Any, limit: int = 600) -> str:
    """Plain, latin-1-safe, XML-escaped text for a Paragraph."""
    text = '' if value is None else str(value)
    text = text.translate(_CHAR_MAP).encode('latin-1', errors='ignore').decode('latin-1')
    text = ' '.join(text.split())
    if len(text) > limit:
        text = text[:limit - 3].rstrip() + '...'
    return escape(text)


def _band(fraction: float):
    return GREEN if fraction >= 0.8 else AMBER if fraction >= 0.6 else RED


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class ScoreBar(Flowable):
    """A rounded progress bar."""

    def __init__(self, value: float, maximum: float, width: float = 200, height: float = 9):
        super().__init__()
        self.value, self.maximum, self.width, self.height = value, maximum, width, height

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        fraction = max(0.0, min(1.0, self.value / self.maximum if self.maximum else 0.0))
        self.canv.setFillColor(LINE)
        self.canv.roundRect(0, 0, self.width, self.height, self.height / 2, stroke=0, fill=1)
        if fraction > 0:
            self.canv.setFillColor(_band(fraction))
            self.canv.roundRect(0, 0, max(self.height, self.width * fraction), self.height,
                                self.height / 2, stroke=0, fill=1)


def _styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()['Normal']
    def make(name, **kw):
        return ParagraphStyle(name, parent=base, fontName=kw.pop('fontName', 'Helvetica'), **kw)
    return {
        'body':   make('body', fontSize=9.5, leading=13, textColor=NAVY),
        'small':  make('small', fontSize=8.5, leading=11.5, textColor=SLATE),
        'bold':   make('bold', fontName='Helvetica-Bold', fontSize=9.5, leading=13, textColor=NAVY),
        'h1':     make('h1', fontName='Helvetica-Bold', fontSize=11.5, leading=15, textColor=NAVY,
                       spaceBefore=12, spaceAfter=5),
        'bullet': make('bullet', fontSize=9.5, leading=13, textColor=NAVY, leftIndent=11, bulletIndent=1),
        'big':    make('big', fontName='Helvetica-Bold', fontSize=46, leading=48, alignment=1),
        'over':   make('over', fontSize=9, leading=11, textColor=SLATE, alignment=1),
        'right':  make('right', fontName='Helvetica-Bold', fontSize=10, leading=13, alignment=2, textColor=NAVY),
    }


def _section(title: str, st) -> List:
    rule = Table([['']], colWidths=[PAGE_W], rowHeights=[1.2])
    rule.setStyle(TableStyle([('LINEABOVE', (0, 0), (-1, 0), 1.2, LINE)]))
    return [Paragraph(_txt(title), st['h1']), rule, Spacer(1, 5)]


def _severity(level: Any):
    low = str(level or '').lower()
    if any(k in low for k in ('crit', 'high')):
        return 0, 'HIGH', RED
    if any(k in low for k in ('mod', 'med')):
        return 1, 'MEDIUM', AMBER
    return 2, 'LOW', SLATE


def _header(st, filename: Optional[str], when: str):
    right = f"{_txt(filename, 60)}<br/>{when}" if filename else when
    t = Table([[Paragraph('<font color="white"><b>ATS Resume Report</b></font>',
                          ParagraphStyle('t', fontName='Helvetica-Bold', fontSize=16, leading=19)),
                Paragraph(f'<font color="#CBD5E1">{right}</font>',
                          ParagraphStyle('r', fontName='Helvetica', fontSize=8.5, leading=11, alignment=2))]],
              colWidths=[PAGE_W * 0.55, PAGE_W * 0.45])
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), NAVY), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                           ('LEFTPADDING', (0, 0), (-1, -1), 12), ('RIGHTPADDING', (0, 0), (-1, -1), 12),
                           ('TOPPADDING', (0, 0), (-1, -1), 11), ('BOTTOMPADDING', (0, 0), (-1, -1), 11)]))
    return t


def _score_card(analysis: Dict, st) -> Table:
    overall = _num(analysis.get('ATS_score', analysis.get('ats_score')))
    comps = analysis.get('component_scores') or {}
    total = sum(_num(comps.get(k)) for k, *_ in COMPONENTS)
    color = _band(overall / 100.0)
    big = Paragraph(f'<font color="{color.hexval().replace("0x", "#")}">{overall:.0f}</font>', st['big'])
    over = Paragraph('out of 100', st['over'])
    lines = [Paragraph(_txt(analysis.get('interpretation') or 'Your resume has been scored.', 220), st['bold'])]
    adjustment = round(overall - total)
    if adjustment < 0:
        lines.append(Paragraph(f'The five parts add up to {total:.0f}. A job description penalty of '
                               f'{abs(adjustment)} points was applied because many of its keywords are missing '
                               f'from the resume.', st['small']))
    elif adjustment > 0:
        lines.append(Paragraph(f'The five parts add up to {total:.0f}. A bonus of {adjustment} point(s) was added '
                               f'for strong skill validation.', st['small']))
    right = Table([[l] for l in lines], colWidths=[PAGE_W - 120])
    right.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('TOPPADDING', (0, 0), (-1, -1), 2),
                               ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
    left = Table([[big], [over]], colWidths=[100])
    left.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                              ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
    card = Table([[left, right]], colWidths=[110, PAGE_W - 110])
    card.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), LIGHT), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                              ('LEFTPADDING', (0, 0), (-1, -1), 12), ('RIGHTPADDING', (0, 0), (-1, -1), 12),
                              ('TOPPADDING', (0, 0), (-1, -1), 12), ('BOTTOMPADDING', (0, 0), (-1, -1), 12)]))
    return card


def _components_table(analysis: Dict, st) -> Table:
    comps = analysis.get('component_scores') or {}
    rows = []
    for key, label, note, maximum, _ in COMPONENTS:
        value = _num(comps.get(key))
        rows.append([Paragraph(f'<b>{_txt(label)}</b><br/><font size="8" color="#64748B">{_txt(note)}</font>', st['body']),
                     ScoreBar(value, maximum, width=PAGE_W * 0.42),
                     Paragraph(f'{value:.0f}/{maximum}', st['right'])])
    t = Table(rows, colWidths=[PAGE_W * 0.40, PAGE_W * 0.45, PAGE_W * 0.15])
    t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 5),
                           ('BOTTOMPADDING', (0, 0), (-1, -1), 5), ('LINEBELOW', (0, 0), (-1, -2), 0.5, LINE),
                           ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
    return t


def _fix_first(analysis: Dict, st) -> List:
    comps = analysis.get('component_scores') or {}
    lost = sorted(((maximum - _num(comps.get(key)), label, advice)
                   for key, label, _n, maximum, advice in COMPONENTS), reverse=True)
    lost = [item for item in lost if item[0] >= 1][:3]
    if not lost:
        return [Paragraph('Every part of the score is at or near its maximum. Nice work.', st['body'])]
    out = []
    for i, (points, label, advice) in enumerate(lost, 1):
        out.append(Paragraph(f'<b>{i}. {_txt(label)}</b> - {points:.0f} points lost. {_txt(advice)}', st['body']))
        out.append(Spacer(1, 3))
    return out


def _bullets(items: List[str], st, limit: int = 6, more_note: str = '') -> List:
    shown = [Paragraph(_txt(i, 300), st['bullet'], bulletText='-') for i in items[:limit] if i]
    if len(items) > limit:
        shown.append(Paragraph(f'... and {len(items) - limit} more{more_note}', st['small']))
    return shown


def _issues(analysis: Dict, st) -> List:
    issues = [i for i in (analysis.get('detailed_feedback') or []) if isinstance(i, dict)]
    issues.sort(key=lambda i: _severity(i.get('severity_level'))[0])
    out: List = []
    for issue in issues[:8]:
        _rank, tag, color = _severity(issue.get('severity_level'))
        hex_color = color.hexval().replace('0x', '#')
        block = [Paragraph(f'<font color="{hex_color}"><b>{tag}</b></font>  <b>{_txt(issue.get("issue_title"), 120)}</b>', st['body']),
                 Paragraph(_txt(issue.get('explanation'), 380), st['small'])]
        if issue.get('how_to_fix'):
            block.append(Paragraph(f'<b>How to fix:</b> {_txt(issue.get("how_to_fix"), 380)}', st['small']))
        actions = [a for a in (issue.get('action_items') or []) if a]
        if actions:
            block += _bullets(actions, st, limit=3, more_note=' (see the skills table below)' if len(actions) > 3 else '')
        block.append(Spacer(1, 7))
        out.append(KeepTogether(block))
    if not out:
        out.append(Paragraph('No issues were found.', st['body']))
    return out


def _skills(analysis: Dict, st) -> List:
    details = analysis.get('skill_validation_details') or {}
    validated = [v for v in (details.get('validated') or []) if isinstance(v, dict)]
    unvalidated = [str(s) for s in (details.get('unvalidated') or [])]
    if not validated and not unvalidated:
        return []
    ok = [Paragraph('<b>Backed by your projects</b>', st['body'])]
    for v in validated[:14]:
        projects = ', '.join(str(p) for p in (v.get('projects') or [])[:2])
        ok.append(Paragraph(f'{_txt(v.get("skill"), 40)} <font color="#64748B">- {_txt(projects, 70)}</font>', st['small']))
    if len(validated) > 14:
        ok.append(Paragraph(f'... and {len(validated) - 14} more', st['small']))
    need = [Paragraph('<b>Needs evidence</b>', st['body']),
            Paragraph(_txt(', '.join(unvalidated) or 'None - every listed skill is backed up.', 900), st['small'])]
    t = Table([[ok, need]], colWidths=[PAGE_W * 0.5, PAGE_W * 0.5])
    t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                           ('RIGHTPADDING', (0, 0), (0, 0), 10)]))
    total = details.get('total') or (len(validated) + len(unvalidated))
    summary = Paragraph(f'{len(validated)} of {total} listed skills are backed by a project or job.', st['small'])
    return _section('Skills and evidence', st) + [summary, Spacer(1, 4), t]


def _weak_bullets(analysis: Dict, st) -> List:
    weak = [w for w in (analysis.get('weak_bullets') or []) if isinstance(w, dict) and w.get('bullet')]
    if not weak:
        return []
    out = _section('Bullets to strengthen', st)
    out.append(Paragraph('Start each with a strong action verb and add a real, checkable result. '
                         'The app can suggest rewrites with "Fix my weak bullets".', st['small']))
    out.append(Spacer(1, 4))
    for w in weak[:6]:
        cell = Table([[Paragraph(_txt(w.get('bullet'), 260), st['body'])],
                      [Paragraph(f'{_txt(w.get("source"), 60)}: {_txt(w.get("issues"), 120)}', st['small'])]],
                     colWidths=[PAGE_W])
        cell.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), LIGHT), ('LEFTPADDING', (0, 0), (-1, -1), 8),
                                  ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                                  ('LINEBEFORE', (0, 0), (0, -1), 2, INDIGO)]))
        out += [KeepTogether([cell]), Spacer(1, 4)]
    return out


def _jd_match(analysis: Dict, st) -> List:
    jd = analysis.get('jd_match_analysis') or analysis.get('jd_comparison')
    if not isinstance(jd, dict):
        return []
    matched, missing, gap = jd.get('matched_keywords') or [], jd.get('missing_keywords') or [], jd.get('skills_gap') or []
    if not (matched or missing or gap or _num(jd.get('match_percentage'))):
        return []
    pct = _num(jd.get('match_percentage'))
    out = _section('Job description match', st)
    out.append(Paragraph(f'<b>{pct:.0f}%</b> of the job description keywords were found. '
                         f'Meaning match: {_num(jd.get("semantic_similarity")) * 100:.0f}%.', st['body']))
    out.append(Spacer(1, 4))
    out.append(Paragraph(f'<b>Matched:</b> {_txt(", ".join(map(str, matched[:25])) or "none", 500)}', st['small']))
    out.append(Paragraph(f'<b>Missing:</b> {_txt(", ".join(map(str, missing[:25])) or "none", 500)}', st['small']))
    if gap:
        out.append(Paragraph(f'<b>Skills gap:</b> {_txt(", ".join(map(str, gap[:20])), 400)}', st['small']))
    return out


class CheckBox(Flowable):
    """An empty square to tick by hand."""

    def __init__(self, size: float = 8):
        super().__init__()
        self.size = size

    def wrap(self, *_):
        return self.size, self.size

    def draw(self):
        self.canv.setStrokeColor(INDIGO)
        self.canv.setLineWidth(1)
        self.canv.rect(0, 0, self.size, self.size, stroke=1, fill=0)


def _checklist(analysis: Dict, st) -> List:
    issues = [i for i in (analysis.get('detailed_feedback') or []) if isinstance(i, dict)]
    issues.sort(key=lambda i: _severity(i.get('severity_level'))[0])
    rows = []
    for issue in issues[:6]:
        title = issue.get('issue_title')
        if not title:
            continue
        actions = [a for a in (issue.get('action_items') or []) if a]
        line = f'<b>{_txt(title, 90)}</b>' + (f': {_txt(actions[0], 110)}' if actions else '')
        rows.append([CheckBox(), Paragraph(line, st['body'])])
    if not rows:
        return []
    table = Table(rows, colWidths=[16, PAGE_W - 16])
    table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                               ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
    return _section('Your checklist', st) + [table]


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(SLATE)
    canvas.drawString(16 * mm, 9 * mm, 'Generated by ATS Resume Scorer')
    canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f'Page {doc.page}')
    canvas.restoreState()


def _build_native(analysis: Dict[str, Any], filename: Optional[str]) -> bytes:
    st = _styles()
    when = datetime.now().strftime('%B %d, %Y')
    story: List = [_header(st, filename, when), Spacer(1, 10), _score_card(analysis, st)]
    story += _section('Score breakdown', st) + [_components_table(analysis, st)]
    story += _section('Fix these first', st) + _fix_first(analysis, st)
    strengths = [s for s in (analysis.get('strengths') or []) if s]
    if strengths:
        story += _section('Strengths', st) + _bullets(strengths, st, limit=8)
    story += _section('Issues, most important first', st) + _issues(analysis, st)
    story += _skills(analysis, st) + _weak_bullets(analysis, st) + _jd_match(analysis, st) + _checklist(analysis, st)

    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm,
                      bottomMargin=16 * mm, title='ATS Resume Report', author='ATS Resume Scorer'
                      ).build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def build_report_pdf(analysis: Dict[str, Any], filename: Optional[str] = None) -> bytes:
    try:
        return _build_native(analysis or {}, filename)
    except Exception as exc:  # never let the layout code block a download
        logger.error(f'Native PDF report failed, using the HTML report instead: {exc}')
        from backend.services.pdf_export import generate_combined_pdf
        from backend.services.report_generator import generate_html_reports
        return generate_combined_pdf(generate_html_reports(analysis or {}))
