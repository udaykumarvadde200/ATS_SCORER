"""PDF export for the ATS report.

Primary renderer: WeasyPrint (keeps the HTML/CSS layout; needs Pango/Cairo,
which is normally available on a Linux host).

Fallback renderer: ReportLab (works anywhere, including Windows). It converts
the HTML into plain text blocks. The report templates keep most of their text
inside <div> and <span> tags, so the fallback walks the whole document and
keeps the text of every block, not just <h1>-<h4>, <p> and <li>.
"""

import io
import logging
from xml.sax.saxutils import escape

from bs4 import BeautifulSoup
from bs4.element import NavigableString, PreformattedString
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
    HRFlowable,
)

logger = logging.getLogger("ats_resume_scorer")


# ---------------------------------------------------------------------------
# Primary renderer: WeasyPrint
# ---------------------------------------------------------------------------

def _render_with_weasyprint(html_docs: dict[str, str]) -> bytes:
    # Imported lazily: WeasyPrint needs system libraries (Pango). If they are
    # missing, the import raises and we fall back to the ReportLab renderer.
    from weasyprint import HTML

    rendered = [HTML(string=html).render() for html in html_docs.values()]
    all_pages = [page for doc in rendered for page in doc.pages]
    return rendered[0].copy(all_pages).write_pdf()


# ---------------------------------------------------------------------------
# Fallback renderer: ReportLab
# ---------------------------------------------------------------------------

_SKIP_TAGS = {"style", "script", "head", "title", "meta", "link"}

_BLOCK_TAGS = {
    "div", "p", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "tr", "section", "header", "footer", "article", "blockquote",
}

_KIND_BY_TAG = {
    "h1": "h1", "h2": "h2", "h3": "h3", "h4": "h3", "h5": "h3", "h6": "h3",
    "li": "li",
}

# Helvetica cannot draw most symbols; swap common ones for plain equivalents.
_CHAR_MAP = str.maketrans({
    "\u2013": "-", "\u2014": "-", "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"', "\u2022": "-", "\u2192": "->",
    "\u2026": "...", "\u00a0": " ", "\u2713": "[x]", "\u2714": "[x]",
    "\u2717": "[ ]", "\u2610": "[ ]", "\u2611": "[x]",
})


def _clean_text(text: str) -> str:
    text = text.translate(_CHAR_MAP)
    # Anything still outside Latin-1 (emoji etc.) is dropped.
    return text.encode("latin-1", errors="ignore").decode("latin-1")


def _extract_blocks(root) -> list:
    """Walk the HTML and return [(kind, text), ...] in reading order.

    kind is one of: h1, h2, h3, li, p, pre, hr.
    Text from inline tags (span, strong, em, a ...) is joined into the block
    that contains them; every block-level tag starts a new block.
    """
    blocks = []
    buf = []

    def flush(kind):
        text = " ".join("".join(buf).split())
        buf.clear()
        if text:
            blocks.append((kind, text))

    def walk(node, kind):
        for child in node.children:
            if isinstance(child, PreformattedString):   # comments, doctype
                continue
            if isinstance(child, NavigableString):
                buf.append(str(child))
                continue

            name = child.name
            if name in _SKIP_TAGS:
                continue
            if name == "br":
                flush(kind)
            elif name == "hr":
                flush(kind)
                blocks.append(("hr", ""))
            elif name == "pre":
                flush(kind)
                for line in child.get_text().splitlines():
                    blocks.append(("pre", line.rstrip()))
            elif name in _BLOCK_TAGS:
                flush(kind)
                child_kind = _KIND_BY_TAG.get(name, "li" if kind == "li" else "p")
                walk(child, child_kind)
                flush(child_kind)
            else:
                # inline tag: keep its text, separated from its neighbours
                walk(child, kind)
                buf.append(" ")

    walk(root, "p")
    flush("p")
    return blocks


def _html_to_story(html_str: str, styles: dict) -> list:
    """Convert report HTML into ReportLab paragraphs and spacers."""
    soup = BeautifulSoup(html_str, "html.parser")
    root = soup.body if soup.body else soup
    story = []

    for kind, text in _extract_blocks(root):
        if kind == "hr":
            story.extend([
                Spacer(1, 2 * mm),
                HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey),
                Spacer(1, 3 * mm),
            ])
            continue

        text = _clean_text(text).rstrip()

        if kind == "pre":
            if text.strip():
                story.append(Paragraph(escape(text), styles["CodeText"]))
            else:
                story.append(Spacer(1, 2 * mm))
            continue

        text = text.strip()
        if not text:
            continue
        text = escape(text)

        if kind == "h1":
            story.append(Paragraph(text, styles["CustomTitle"]))
        elif kind == "h2":
            story.append(Paragraph(text, styles["CustomTitle1"]))
        elif kind == "h3":
            story.append(Paragraph(text, styles["CustomTitle2"]))
        elif kind == "li":
            story.append(Paragraph("\u2022 " + text, styles["ListText"]))
            story.append(Spacer(1, 1 * mm))
        else:
            story.append(Paragraph(text, styles["BodyText"]))
            story.append(Spacer(1, 1.5 * mm))

    return story


def _render_with_reportlab(html_docs: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="CustomTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=25,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#17365D"),
        spaceAfter=8 * mm,
    ))

    styles.add(ParagraphStyle(
        name="CustomTitle1",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#17365D"),
        spaceBefore=4 * mm,
        spaceAfter=3 * mm,
    ))

    styles.add(ParagraphStyle(
        name="CustomTitle2",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#28527A"),
        spaceBefore=3 * mm,
        spaceAfter=2 * mm,
    ))

    styles["BodyText"].fontSize = 9
    styles["BodyText"].leading = 13

    styles.add(ParagraphStyle(
        name="ListText",
        parent=styles["BodyText"],
        leftIndent=6 * mm,
        firstLineIndent=-3 * mm,
    ))

    styles.add(ParagraphStyle(
        name="CodeText",
        parent=styles["BodyText"],
        fontName="Courier",
        fontSize=8,
        leading=10,
    ))

    story = []
    for index, (name, html_str) in enumerate(html_docs.items()):
        if index:
            story.append(PageBreak())

        soup = BeautifulSoup(html_str, "html.parser")
        if soup.find(["h1", "h2"]) is None:
            story.append(Paragraph(name.replace("_", " ").title(), styles["CustomTitle1"]))
            story.append(Spacer(1, 3 * mm))

        story.extend(_html_to_story(html_str, styles))

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="ATS Resume Analysis Report",
        author="ATS Resume Scorer",
    )
    doc.build(story)

    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


# ---------------------------------------------------------------------------
# Public API (same signature as before)
# ---------------------------------------------------------------------------

def generate_combined_pdf(html_docs: dict[str, str]) -> bytes:
    """Generate one PDF from multiple HTML report sections."""
    if not html_docs:
        raise ValueError("No report sections were provided.")

    try:
        return _render_with_weasyprint(html_docs)
    except (ImportError, OSError) as exc:
        # WeasyPrint (or its Pango/Cairo libraries) is not installed.
        logger.warning(f"WeasyPrint unavailable ({exc}); using ReportLab fallback")
    except Exception as exc:
        logger.error(f"WeasyPrint rendering failed ({exc}); using ReportLab fallback")

    return _render_with_reportlab(html_docs)
