"""
PDF Generator for AlignIQ Reports

Uses ReportLab for PDF generation from Markdown content.
Includes proper handling of:
- Markdown headers (H1, H2, H3)
- Code blocks
- Tables
- Lists (ordered and unordered)
- Bold/italic text
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Preformatted, ListFlowable, ListItem
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from io import BytesIO
import re
from datetime import datetime
from utils.logger import logger


def _create_styles():
    """Create custom paragraph styles for the PDF."""
    styles = getSampleStyleSheet()

    # Title style
    styles.add(ParagraphStyle(
        name='ReportTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#1a1a2e')
    ))

    # H1 style
    styles.add(ParagraphStyle(
        name='H1',
        parent=styles['Heading1'],
        fontSize=18,
        spaceBefore=20,
        spaceAfter=12,
        textColor=colors.HexColor('#1a1a2e')
    ))

    # H2 style
    styles.add(ParagraphStyle(
        name='H2',
        parent=styles['Heading2'],
        fontSize=14,
        spaceBefore=16,
        spaceAfter=8,
        textColor=colors.HexColor('#333333')
    ))

    # H3 style
    styles.add(ParagraphStyle(
        name='H3',
        parent=styles['Heading3'],
        fontSize=12,
        spaceBefore=12,
        spaceAfter=6,
        textColor=colors.HexColor('#444444')
    ))

    # Body text - renamed to avoid conflict with built-in 'BodyText'
    styles.add(ParagraphStyle(
        name='CustomBody',
        parent=styles['Normal'],
        fontSize=10,
        spaceBefore=6,
        spaceAfter=6,
        alignment=TA_JUSTIFY,
        leading=14
    ))

    # Code block style - renamed to avoid conflict with built-in 'Code'
    styles.add(ParagraphStyle(
        name='CodeBlock',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=9,
        backColor=colors.HexColor('#f5f5f5'),
        borderColor=colors.HexColor('#cccccc'),
        borderWidth=1,
        borderPadding=8,
        spaceBefore=8,
        spaceAfter=8,
        leading=12
    ))

    # Table header style
    styles.add(ParagraphStyle(
        name='TableHead',
        parent=styles['Normal'],
        fontSize=10,
        fontName='Helvetica-Bold',
        alignment=TA_CENTER
    ))

    return styles


def _parse_markdown_to_flowables(markdown_content: str, styles) -> list:
    """
    Convert markdown content to ReportLab flowables.

    Args:
        markdown_content: The markdown text to convert
        styles: The stylesheet to use

    Returns:
        List of ReportLab flowables
    """
    flowables = []
    lines = markdown_content.split('\n')

    i = 0
    in_code_block = False
    code_content = []
    in_table = False
    table_rows = []

    while i < len(lines):
        line = lines[i]

        # Handle code blocks
        if line.strip().startswith('```'):
            if in_code_block:
                # End code block
                code_text = '\n'.join(code_content)
                flowables.append(Preformatted(code_text, styles['CodeBlock']))
                code_content = []
                in_code_block = False
            else:
                # Start code block
                in_code_block = True
            i += 1
            continue

        if in_code_block:
            code_content.append(line)
            i += 1
            continue

        # Handle tables
        if '|' in line and line.strip().startswith('|'):
            if not in_table:
                in_table = True
                table_rows = []

            # Skip separator rows (|---|---|)
            if not re.match(r'^\|[\s\-:]+\|$', line.replace('|', '').strip() + '|'):
                cells = [cell.strip() for cell in line.split('|')[1:-1]]
                if cells:
                    table_rows.append(cells)
            i += 1
            continue
        elif in_table:
            # End of table
            if table_rows:
                flowables.append(_create_table(table_rows, styles))
            in_table = False
            table_rows = []

        # Handle headers
        if line.startswith('# '):
            text = _convert_inline_markdown(line[2:].strip())
            flowables.append(Paragraph(text, styles['H1']))
        elif line.startswith('## '):
            text = _convert_inline_markdown(line[3:].strip())
            flowables.append(Paragraph(text, styles['H2']))
        elif line.startswith('### '):
            text = _convert_inline_markdown(line[4:].strip())
            flowables.append(Paragraph(text, styles['H3']))

        # Handle horizontal rules
        elif line.strip() in ['---', '***', '___']:
            flowables.append(Spacer(1, 12))

        # Handle bullet lists
        elif line.strip().startswith('- ') or line.strip().startswith('* '):
            text = _convert_inline_markdown(line.strip()[2:])
            flowables.append(Paragraph(f"&bull; {text}", styles['CustomBody']))

        # Handle numbered lists
        elif re.match(r'^\d+\.\s', line.strip()):
            text = _convert_inline_markdown(re.sub(r'^\d+\.\s', '', line.strip()))
            num_match = re.match(r'^(\d+)\.', line.strip())
            if num_match:
                num = num_match.group(1)
                flowables.append(Paragraph(f"{num}. {text}", styles['CustomBody']))

        # Handle empty lines
        elif line.strip() == '':
            flowables.append(Spacer(1, 6))

        # Regular paragraph
        else:
            text = _convert_inline_markdown(line.strip())
            if text:
                flowables.append(Paragraph(text, styles['CustomBody']))

        i += 1

    # Handle any remaining table
    if in_table and table_rows:
        flowables.append(_create_table(table_rows, styles))

    return flowables


def _convert_inline_markdown(text: str) -> str:
    """Convert inline markdown (bold, italic, code) to ReportLab tags."""
    # Bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)

    # Italic
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    text = re.sub(r'_(.+?)_', r'<i>\1</i>', text)

    # Inline code
    text = re.sub(r'`(.+?)`', r'<font name="Courier" size="9">\1</font>', text)

    # Links (just show the text, not the URL)
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)

    return text


def _create_table(rows: list, styles) -> Table:
    """Create a ReportLab table from rows."""
    if not rows:
        return Spacer(1, 0)

    # Convert cells to paragraphs for proper text wrapping
    table_data = []
    for i, row in enumerate(rows):
        if i == 0:
            # Header row
            table_data.append([
                Paragraph(cell, styles['TableHead']) for cell in row
            ])
        else:
            table_data.append([
                Paragraph(cell, styles['CustomBody']) for cell in row
            ])

    # Calculate column widths
    num_cols = len(rows[0]) if rows else 1
    col_width = 6.5 * inch / num_cols

    table = Table(table_data, colWidths=[col_width] * num_cols)

    # Style the table
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8e8e8')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#333333')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ])
    table.setStyle(table_style)

    return table


async def generate_pdf_from_markdown(
    markdown_content: str,
    title: str = "Technical Report",
    version: int = 1,
    page_size=letter
) -> bytes:
    """
    Generate a PDF from markdown content.

    Args:
        markdown_content: The markdown text to convert
        title: The report title
        version: The version number
        page_size: Page size (default: letter)

    Returns:
        PDF content as bytes
    """
    try:
        buffer = BytesIO()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=page_size,
            rightMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch
        )

        styles = _create_styles()
        story = []

        # Title page
        story.append(Spacer(1, 2 * inch))
        story.append(Paragraph(title, styles['ReportTitle']))
        story.append(Spacer(1, 0.5 * inch))
        story.append(Paragraph(f"Version {version}", styles['CustomBody']))
        story.append(Paragraph(
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            styles['CustomBody']
        ))
        story.append(Paragraph("Generated by AlignIQ", styles['CustomBody']))
        story.append(PageBreak())

        # Convert markdown to flowables
        content_flowables = _parse_markdown_to_flowables(markdown_content, styles)
        story.extend(content_flowables)

        # Build PDF
        doc.build(story)

        pdf_data = buffer.getvalue()
        buffer.close()

        logger.info(f"Generated PDF: {len(pdf_data)} bytes for {title} v{version}")
        return pdf_data

    except Exception as e:
        logger.error(f"PDF generation failed: {str(e)}")
        raise
