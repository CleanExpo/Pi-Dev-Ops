#!/usr/bin/env python3
"""Generate a client-ready PDF SEO report from a JSON audit file.

Usage:
  generate_pdf_report.py --input audit.json --output report.pdf

The JSON schema is flexible — see seo/schema/audit_input.example.json for the
shape produced by the /seo audit orchestrator. Missing sections are skipped.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
except ImportError:
    sys.stderr.write("ERROR: reportlab not installed. Run: pip install reportlab\n")
    sys.exit(2)


BRAND_PRIMARY = colors.HexColor("#1f4e79")
BRAND_ACCENT = colors.HexColor("#2e8b57")
BRAND_WARN = colors.HexColor("#d97706")
BRAND_BAD = colors.HexColor("#b91c1c")
GREY_LIGHT = colors.HexColor("#f3f4f6")
GREY_MID = colors.HexColor("#9ca3af")


def score_color(score: float | int | None) -> colors.Color:
    if score is None:
        return GREY_MID
    if score >= 80:
        return BRAND_ACCENT
    if score >= 60:
        return BRAND_PRIMARY
    if score >= 40:
        return BRAND_WARN
    return BRAND_BAD


def styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontSize=26, leading=30,
            textColor=BRAND_PRIMARY, alignment=TA_CENTER, spaceAfter=8,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=base["Normal"], fontSize=12, leading=16,
            textColor=GREY_MID, alignment=TA_CENTER, spaceAfter=24,
        ),
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"], fontSize=18, leading=22,
            textColor=BRAND_PRIMARY, spaceBefore=18, spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontSize=14, leading=18,
            textColor=BRAND_PRIMARY, spaceBefore=12, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"], fontSize=10.5, leading=15,
            textColor=colors.HexColor("#111827"), alignment=TA_LEFT, spaceAfter=6,
        ),
        "muted": ParagraphStyle(
            "muted", parent=base["Normal"], fontSize=9, leading=12,
            textColor=GREY_MID, spaceAfter=4,
        ),
    }


def score_card(label: str, score: float | int | None, S) -> Table:
    score_text = "—" if score is None else f"{int(round(score))}"
    cell_color = score_color(score)
    table = Table(
        [[Paragraph(f'<font size="34" color="white"><b>{score_text}</b></font>', S["body"])],
         [Paragraph(f'<font color="white">{label}</font>', S["body"])]],
        colWidths=[1.6 * inch], rowHeights=[0.9 * inch, 0.45 * inch],
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), cell_color),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ("BOX", (0, 0), (-1, -1), 0.5, cell_color),
    ]))
    return table


def kv_table(rows: list[tuple[str, str]], S) -> Table:
    body = [[Paragraph(f"<b>{k}</b>", S["body"]), Paragraph(v, S["body"])] for k, v in rows]
    t = Table(body, colWidths=[2.0 * inch, 4.5 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), GREY_LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, GREY_MID),
    ]))
    return t


def issues_table(issues: list[dict], S) -> Table | None:
    if not issues:
        return None
    header = [
        Paragraph("<b>Priority</b>", S["body"]),
        Paragraph("<b>Issue</b>", S["body"]),
        Paragraph("<b>Recommendation</b>", S["body"]),
    ]
    body = [header]
    for issue in issues[:30]:
        priority = (issue.get("priority") or "—").upper()
        body.append([
            Paragraph(priority, S["body"]),
            Paragraph(issue.get("title") or issue.get("issue") or "", S["body"]),
            Paragraph(issue.get("recommendation") or issue.get("fix") or "", S["body"]),
        ])
    t = Table(body, colWidths=[0.9 * inch, 2.4 * inch, 3.2 * inch], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GREY_LIGHT]),
    ]))
    return t


def build(audit: dict, output: Path) -> None:
    S = styles()
    doc = SimpleDocTemplate(
        str(output), pagesize=letter,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.7 * inch, bottomMargin=0.7 * inch,
        title="SEO Audit Report",
    )
    story: list = []

    domain = audit.get("target") or audit.get("domain") or "—"
    generated = audit.get("generated_at") or datetime.utcnow().strftime("%B %d, %Y")
    story.append(Paragraph("SEO Audit Report", S["title"]))
    story.append(Paragraph(f"{domain} &nbsp;·&nbsp; {generated}", S["subtitle"]))

    scores = audit.get("scores") or {}
    score_row = [
        score_card("OVERALL", scores.get("overall"), S),
        score_card("KEYWORDS", scores.get("keywords"), S),
        score_card("TECHNICAL", scores.get("technical"), S),
        score_card("AUTHORITY", scores.get("authority"), S),
    ]
    grid = Table([score_row], colWidths=[1.7 * inch] * 4)
    grid.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(grid)
    story.append(Spacer(1, 18))

    if audit.get("executive_summary"):
        story.append(Paragraph("Executive Summary", S["h1"]))
        for para in audit["executive_summary"].split("\n\n"):
            if para.strip():
                story.append(Paragraph(para.strip(), S["body"]))

    metrics = audit.get("key_metrics") or {}
    if metrics:
        story.append(Paragraph("Key Metrics", S["h1"]))
        rows = [(k.replace("_", " ").title(), str(v)) for k, v in metrics.items()]
        story.append(kv_table(rows, S))

    issues = audit.get("issues") or audit.get("priority_issues") or []
    if issues:
        story.append(Paragraph("Prioritized Action Plan", S["h1"]))
        story.append(issues_table(issues, S))

    keywords = audit.get("top_keywords") or []
    if keywords:
        story.append(PageBreak())
        story.append(Paragraph("Top Keyword Opportunities", S["h1"]))
        head = [Paragraph(f"<b>{h}</b>", S["body"])
                for h in ("Keyword", "Volume", "CPC", "Difficulty", "Position")]
        body = [head]
        for kw in keywords[:25]:
            body.append([
                Paragraph(str(kw.get("keyword", "")), S["body"]),
                Paragraph(str(kw.get("search_volume", "—")), S["body"]),
                Paragraph(f"${kw.get('cpc', '—')}", S["body"]),
                Paragraph(str(kw.get("difficulty", "—")), S["body"]),
                Paragraph(str(kw.get("position", "—")), S["body"]),
            ])
        t = Table(body, colWidths=[2.6 * inch, 0.9 * inch, 0.9 * inch, 1.0 * inch, 1.0 * inch], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GREY_LIGHT]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t)

    if audit.get("competitors"):
        story.append(Spacer(1, 18))
        story.append(Paragraph("Competitive Landscape", S["h1"]))
        head = [Paragraph(f"<b>{h}</b>", S["body"])
                for h in ("Domain", "Organic Keywords", "Est. Traffic", "Domain Rank")]
        body = [head]
        for c in audit["competitors"][:15]:
            body.append([
                Paragraph(str(c.get("domain", "")), S["body"]),
                Paragraph(str(c.get("keywords", "—")), S["body"]),
                Paragraph(str(c.get("traffic", "—")), S["body"]),
                Paragraph(str(c.get("rank", "—")), S["body"]),
            ])
        t = Table(body, colWidths=[2.6 * inch, 1.4 * inch, 1.4 * inch, 1.0 * inch], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GREY_LIGHT]),
        ]))
        story.append(t)

    story.append(Spacer(1, 30))
    story.append(Paragraph(
        '<font color="#9ca3af" size="8">Generated with dataforseo-claude · '
        'Powered by DataForSEO &amp; Claude Code</font>',
        S["muted"],
    ))

    doc.build(story)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate PDF SEO report.")
    parser.add_argument("--input", "-i", required=True, help="Path to audit JSON.")
    parser.add_argument("--output", "-o", required=True, help="Path to write PDF.")
    args = parser.parse_args()

    audit = json.loads(Path(args.input).read_text(encoding="utf-8"))
    out = Path(args.output)
    build(audit, out)
    sys.stderr.write(f"PDF written to {out}\n")


if __name__ == "__main__":
    sys.exit(main() or 0)
