from io import BytesIO
from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.worksheet.worksheet import Worksheet
from openpyxl.cell.cell import MergedCell
from openpyxl.utils import get_column_letter

from app.services.statements_service import CompteResultat, Bilan, AgedBalanceRow


CellValue = str | int | Decimal | None


def _money_xaf(amount: Decimal) -> str:
    rounded = amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{rounded:,.0f}"


def _pdf_decimal_to_text(value: CellValue) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return _money_xaf(value)
    return str(value)

def _autosize_columns(ws: Worksheet) -> None:
    """
    Auto-adjust column widths based on cell content.
    Safely handles MergedCell placeholders by using the column index
    instead of the column_letter property, and skipping merged placeholders
    when measuring content length.
    """
    for column_cells in ws.columns:
        if not column_cells:
            continue

        max_length = 0
        # Use column index -> letter conversion. This works for both
        # regular Cell and MergedCell objects, avoiding AttributeError.
        column_letter = get_column_letter(column_cells[0].column)

        for cell in column_cells:
            # Skip merged cell placeholders (they carry no real content)
            if isinstance(cell, MergedCell):
                continue
            if cell.value is not None:
                try:
                    cell_length = len(str(cell.value))
                    if cell_length > max_length:
                        max_length = cell_length
                except Exception:
                    pass

        # Add padding and cap at a reasonable max width
        adjusted_width = min(max_length + 2, 60)
        if adjusted_width > 8:  # Only override if wider than default
            ws.column_dimensions[column_letter].width = adjusted_width

def _build_excel(title: str, headers: list[str], rows: list[list[CellValue]]) -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]

    ws.append([title])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    ws["A1"].font = Font(bold=True, size=14)
    ws["A1"].alignment = Alignment(horizontal="center")

    ws.append([])
    ws.append(headers)

    header_fill = PatternFill("solid", fgColor="1F2937")
    for cell in ws[3]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    for row in rows:
        ws.append(row)

    for row in ws.iter_rows(min_row=4):
        for cell in row:
            if isinstance(cell.value, Decimal):
                cell.number_format = '#,##0'
                cell.alignment = Alignment(horizontal="right")

    _autosize_columns(ws)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def _build_pdf(title: str, headers: list[str], rows: list[list[CellValue]]) -> BytesIO:
    """
    Pure-Python PDF generation using ReportLab.
    No GTK/Pango/GObject native libraries required.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"<b>SYCEBNL — {title}</b>", styles["Title"]))
    story.append(Spacer(1, 8 * mm))

    table_data: list[list[str]] = [headers]
    for row in rows:
        table_data.append([_pdf_decimal_to_text(value) for value in row])

    table = Table(table_data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
            ]
        )
    )

    story.append(table)
    doc.build(story)

    buffer.seek(0)
    return buffer


def export_compte_resultat_to_excel(data: CompteResultat) -> BytesIO:
    rows: list[list[CellValue]] = []

    rows.append(["", "CHARGES", None])
    for row in data.charges:
        rows.append([row.account_code, row.account_label, row.amount])
    rows.append(["", "TOTAL CHARGES", data.total_charges])

    rows.append([None, None, None])
    rows.append(["", "PRODUITS", None])
    for row in data.produits:
        rows.append([row.account_code, row.account_label, row.amount])
    rows.append(["", "TOTAL PRODUITS", data.total_produits])

    rows.append([None, None, None])
    rows.append(["", "RÉSULTAT DE L'EXERCICE", data.resultat])

    return _build_excel(
        title="Compte de Résultat",
        headers=["Compte", "Libellé", "Montant (XAF)"],
        rows=rows,
    )


def export_compte_resultat_to_pdf(data: CompteResultat) -> BytesIO:
    rows: list[list[CellValue]] = []

    rows.append(["", "CHARGES", None])
    for row in data.charges:
        rows.append([row.account_code, row.account_label, row.amount])
    rows.append(["", "TOTAL CHARGES", data.total_charges])

    rows.append(["", "PRODUITS", None])
    for row in data.produits:
        rows.append([row.account_code, row.account_label, row.amount])
    rows.append(["", "TOTAL PRODUITS", data.total_produits])

    rows.append(["", "RÉSULTAT DE L'EXERCICE", data.resultat])

    return _build_pdf(
        title="Compte de Résultat",
        headers=["Compte", "Libellé", "Montant (XAF)"],
        rows=rows,
    )


def export_bilan_to_excel(data: Bilan) -> BytesIO:
    rows: list[list[CellValue]] = []

    rows.append(["", "ACTIF", None])
    for row in data.actif:
        rows.append([row.account_code, row.account_label, row.amount])
    rows.append(["", "TOTAL ACTIF", data.total_actif])

    rows.append([None, None, None])
    rows.append(["", "PASSIF", None])
    for row in data.passif:
        rows.append([row.account_code, row.account_label, row.amount])
    rows.append(["", "TOTAL PASSIF", data.total_passif])

    return _build_excel(
        title="Bilan SYCEBNL",
        headers=["Compte", "Libellé", "Montant (XAF)"],
        rows=rows,
    )


def export_bilan_to_pdf(data: Bilan) -> BytesIO:
    rows: list[list[CellValue]] = []

    rows.append(["", "ACTIF", None])
    for row in data.actif:
        rows.append([row.account_code, row.account_label, row.amount])
    rows.append(["", "TOTAL ACTIF", data.total_actif])

    rows.append(["", "PASSIF", None])
    for row in data.passif:
        rows.append([row.account_code, row.account_label, row.amount])
    rows.append(["", "TOTAL PASSIF", data.total_passif])

    return _build_pdf(
        title="Bilan SYCEBNL",
        headers=["Compte", "Libellé", "Montant (XAF)"],
        rows=rows,
    )


def export_aged_balance_to_excel(rows_data: Sequence[AgedBalanceRow], title: str) -> BytesIO:
    rows: list[list[CellValue]] = []
    for row in rows_data:
        rows.append(
            [
                row.third_party_name,
                row.bucket_0_30,
                row.bucket_31_60,
                row.bucket_61_90,
                row.bucket_over_90,
                row.total,
            ]
        )

    return _build_excel(
        title=title,
        headers=["Tiers", "0-30", "31-60", "61-90", "> 90", "Total"],
        rows=rows,
    )


def export_aged_balance_to_pdf(rows_data: Sequence[AgedBalanceRow], title: str) -> BytesIO:
    rows: list[list[CellValue]] = []
    for row in rows_data:
        rows.append(
            [
                row.third_party_name,
                row.bucket_0_30,
                row.bucket_31_60,
                row.bucket_61_90,
                row.bucket_over_90,
                row.total,
            ]
        )

    return _build_pdf(
        title=title,
        headers=["Tiers", "0-30", "31-60", "61-90", "> 90", "Total"],
        rows=rows,
    )


def export_pdf_from_html(html_string: str) -> BytesIO:
    """
    Optional WeasyPrint helper.
    IMPORTANT: This imports WeasyPrint lazily so the app can start even when GTK is missing.
    Prefer ReportLab-based exports above on Windows.
    """
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "WeasyPrint is unavailable on this system. "
            "Use the ReportLab PDF export functions instead, "
            "or install GTK/Pango/GObject native libraries."
        ) from exc

    pdf_bytes = HTML(string=html_string).write_pdf()
    buffer = BytesIO(pdf_bytes)
    buffer.seek(0)
    return buffer