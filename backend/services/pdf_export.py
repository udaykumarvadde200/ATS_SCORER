
import io
import logging
from html import unescape

from bs4 import BeautifulSoup
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
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


def _html_to_story(html_str: str, styles: dict) -> list:
    """Convert report HTML into ReportLab paragraphs and spacers."""
    soup = BeautifulSoup(html_str, "html.parser")
    story = []

    for element in soup.body.find_all(
        ["h1", "h2", "h3", "h4", "p", "li", "br", "hr"],
        recursive=True,
    ) if soup.body else soup.find_all(
        ["h1", "h2", "h3", "h4", "p", "li", "br", "hr"]
    ):
        if element.name == "br":
            story.append(Spacer(1, 3 * mm))
            continue

        if element.name == "hr":
            story.extend([
                Spacer(1, 2 * mm),
                HRFlowable(width="100%", thickness=0.5,
                           color=colors.lightgrey),
                Spacer(1, 3 * mm),
            ])
            continue

        text = element.get_text(" ", strip=True)
        if not text:
            continue

        # Escape HTML special characters before ReportLab parses markup.
        from xml.sax.saxutils import escape
        text = escape(unescape(text))

        if element.name == "h1":
            style = styles["CustomTitle"]
        elif element.name == "h2":
            style = styles["CustomTitle1"]
        elif element.name in ("h3", "h4"):
            style = styles["CustomTitle2"]
        elif element.name == "li":
            text = "• " + text
            style = styles["BodyText"]
        else:
            style = styles["BodyText"]

        story.append(Paragraph(text, style))
        story.append(Spacer(1, 2 * mm))

    return story


def generate_combined_pdf(html_docs: dict[str, str]) -> bytes:
    """Generate one PDF from multiple HTML report sections."""
    if not html_docs:
        raise ValueError("No report sections were provided.")

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

    story = []
    sections = list(html_docs.items())

    for index, (name, html_str) in enumerate(sections):
        if index:
            story.append(PageBreak())

        # Use the section name if its HTML doesn't provide a main heading.
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
