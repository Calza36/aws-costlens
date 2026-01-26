"""PDF rendering utilities for report generation."""

from reportlab.platypus import (
    Paragraph,
    Table,
    TableStyle,
    ListFlowable,
    ListItem,
)
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from typing import List

styles = getSampleStyleSheet()

# Custom style for footer
pdf_footer_style = ParagraphStyle(
    name="PDF_Footer",
    parent=styles["Normal"],
    fontSize=8,
    textColor=colors.grey,
    alignment=1,  # Center
    leading=10,
)


def paragraphStyling(text: str, style_name="BodyText", font_size=9, leading=11):
    """Create a styled paragraph."""
    base = styles[style_name]
    st = ParagraphStyle(
        f"{style_name}_cell",
        parent=base,
        fontSize=font_size,
        leading=leading,
    )
    return Paragraph(text, st)


def miniHeader(text: str):
    """Create a mini header paragraph."""
    return paragraphStyling(f"<b>{text}</b>", style_name="BodyText", font_size=9, leading=11)


def keyValueTable(rows, colWidths=None):
    """Create a key-value table."""
    # rows = List[Tuple[label, value]]
    data = [[paragraphStyling(f"<b>{k}</b>"), paragraphStyling(v)] for k, v in rows]
    t = Table(data, colWidths=colWidths or [1.6*inch, 5.8*inch], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LEADING", (0, 0), (-1, -1), 11),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def bulletList(items):
    """Create a bullet list."""
    # items: List[str]
    # Use smaller font and allow splitting across pages
    styled = [ListItem(paragraphStyling(i, font_size=9, leading=11), leftIndent=6) for i in items]
    return ListFlowable(styled, bulletType="bullet", start="•", leftIndent=12)


def formatServicesForList(services):
    """Format services for bullet list display."""
    # services: List[Tuple[str, float]]
    if not services:
        return ["No costs"]
    return [f"{svc}: ${cost:,.2f}" for svc, cost in services]


def split_to_items(value: str) -> List[str]:
    """Turn a possibly multiline string into bullet items (safe for Paragraph)."""
    if not value:
        return ["None"]
    items = [line.strip() for line in value.splitlines() if line.strip()]
    return items or ["None"]


def profileHeaderCard(profile: str, account_id: str, doc_width: float):
    """Create a styled header card for a profile section.
    
    Args:
        profile: AWS profile name
        account_id: AWS account ID
        doc_width: Document width for proper sizing
    
    Returns:
        Table flowable with styled header
    """
    header_content = paragraphStyling(
        f"<b>Profile:</b> {profile} &nbsp;&nbsp;&nbsp; <b>Account:</b> {account_id}"
    )
    header_tbl = Table(
        [[header_content]],
        colWidths=[doc_width],
        hAlign="LEFT",
    )
    header_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
        ("BOX", (0, 0), (-1, -1), 0.25, colors.grey),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return header_tbl


def footerParagraph(text: str):
    """Create a footer paragraph with footer styling."""
    return Paragraph(text, pdf_footer_style)
