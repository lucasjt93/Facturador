from decimal import Decimal
from io import BytesIO
from typing import Dict, Iterable, List, Optional

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .models import Client, Company, Invoice, InvoiceLine
from .services import compute_line_amounts, compute_totals


def _pdf_totals(invoice: Invoice, lines: Iterable[InvoiceLine]) -> Dict[str, Decimal]:
    if invoice.status in ("issued", "paid") and invoice.total_snapshot is not None:
        subtotal = Decimal(invoice.subtotal_snapshot or 0)
        igi_amount = Decimal(invoice.igi_amount_snapshot or 0)
        total = Decimal(invoice.total_snapshot or 0)
        base = total - igi_amount
        return {
            "subtotal": subtotal,
            "discount": Decimal("0.00"),
            "base": base,
            "igi": igi_amount,
            "total": total,
        }
    return compute_totals(invoice, lines)


def build_invoice_pdf_payload(invoice: Invoice, lines: List[InvoiceLine]) -> Dict:
    sorted_lines = sorted(lines, key=lambda l: (l.sort_order, l.id))
    is_final = invoice.status in ("issued", "paid")

    if is_final:
        required = {
            "client_name_snapshot": invoice.client_name_snapshot,
            "client_tax_id_snapshot": invoice.client_tax_id_snapshot,
            "subtotal_snapshot": invoice.subtotal_snapshot,
            "igi_amount_snapshot": invoice.igi_amount_snapshot,
            "total_snapshot": invoice.total_snapshot,
            "igi_rate_snapshot": invoice.igi_rate_snapshot,
        }
        for field, value in required.items():
            if value is None:
                raise ValueError(f"Missing snapshot: {field} for invoice {invoice.id}")
        totals = {
            "subtotal": Decimal(str(invoice.subtotal_snapshot)),
            "discount": Decimal("0.00"),
            "base": Decimal(str(invoice.total_snapshot)) - Decimal(str(invoice.igi_amount_snapshot)),
            "igi": Decimal(str(invoice.igi_amount_snapshot)),
            "total": Decimal(str(invoice.total_snapshot)),
        }
    else:
        totals = _pdf_totals(invoice, sorted_lines)

    line_amounts = compute_line_amounts(sorted_lines)
    if is_final:
        client_name = invoice.client_name_snapshot
        client_tax_id = invoice.client_tax_id_snapshot
        igi_rate = Decimal(str(invoice.igi_rate_snapshot))
    else:
        client_name = invoice.client_name_snapshot or (invoice.client.name if invoice.client else "")
        client_tax_id = invoice.client_tax_id_snapshot or (invoice.client.tax_id if invoice.client else "")
        igi_rate = (
            Decimal(str(invoice.igi_rate_snapshot))
            if invoice.igi_rate_snapshot is not None
            else Decimal(str(invoice.igi_rate))
        )
    show_igi_exempt_footer = igi_rate == Decimal("0")

    return {
        "invoice_number": invoice.invoice_number or str(invoice.id),
        "status": invoice.status,
        "client_name": client_name,
        "client_tax_id": client_tax_id,
        "issue_date": invoice.issue_date,
        "due_date": invoice.due_date,
        "currency": invoice.currency,
        "igi_rate": igi_rate,
        "show_igi_exempt_footer": show_igi_exempt_footer,
        "totals": totals,
        "lines": [
            {
                "index": idx,
                "description": line.description or "",
                "qty": Decimal(line.qty or 0),
                "unit_price": Decimal(line.unit_price or 0),
                "discount_pct": Decimal(line.discount_pct or 0),
                "total": line_total,
            }
            for idx, (line, _, _, line_total) in enumerate(line_amounts, start=1)
        ],
    }


def render_invoice_pdf(
    payload: Dict,
    company: Optional[Company] = None,
    client: Optional[Client] = None,
) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    def wrap_text(text: str, max_width: float, font_name: str = "Helvetica", font_size: int = 9) -> List[str]:
        pdf.setFont(font_name, font_size)
        words = text.split()
        lines: List[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if pdf.stringWidth(candidate, font_name, font_size) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines or [""]

    def draw_header(y_pos: float) -> float:
        y = y_pos
        if company:
            pdf.setFont("Helvetica-Bold", 11)
            pdf.drawString(40, y, company.name or "")
            y -= 12
            pdf.setFont("Helvetica", 9)
            if company.tax_id:
                pdf.drawString(40, y, f"NIF: {company.tax_id}")
                y -= 11
            addr_parts = [
                company.address_line1,
                company.address_line2,
                company.postal_code,
                company.city,
                company.country,
            ]
            addr = " ".join([p for p in addr_parts if p])
            for line in wrap_text(addr, max_width=230, font_size=8):
                pdf.drawString(40, y, line)
                y -= 10
            if company.email:
                pdf.drawString(40, y, company.email)
                y -= 10
            if company.phone:
                pdf.drawString(40, y, f"Tel: {company.phone}")
                y -= 10
        pdf.setFont("Helvetica-Bold", 22)
        pdf.drawRightString(width - 40, y_pos, "FACTURA")
        pdf.setFont("Helvetica-Bold", 28)
        pdf.drawRightString(width - 40, y_pos - 24, str(payload["invoice_number"]))
        return y - 6

    def draw_company_and_dates(y_pos: float) -> float:
        box_w = 200
        box_h = 52
        box_x = width - 40 - box_w
        box_y = y_pos - box_h
        pdf.rect(box_x, box_y, box_w, box_h, stroke=1, fill=0)
        pdf.setFont("Helvetica", 9)
        pdf.drawString(box_x + 8, box_y + box_h - 12, f"Emisión: {payload['issue_date']}")
        pdf.drawString(box_x + 8, box_y + box_h - 24, f"Vencimiento: {payload['due_date']}")
        pdf.drawString(box_x + 8, box_y + box_h - 36, f"Moneda: {payload['currency']} | IGI: {payload['igi_rate']}%")
        return box_y - 12
        y = y_pos
        if company:
            pdf.setFont("Helvetica-Bold", 11)
            pdf.drawString(40, y, company.name or "")
            y -= 12
            pdf.setFont("Helvetica", 10)
            if company.tax_id:
                pdf.drawString(40, y, f"NIF: {company.tax_id}")
                y -= 12
            addr_parts = [
                company.address_line1,
                company.address_line2,
                company.postal_code,
                company.city,
                company.country,
            ]
            addr = " ".join([p for p in addr_parts if p])
            for line in wrap_text(addr, max_width=240, font_size=9):
                pdf.drawString(40, y, line)
                y -= 11
            if company.email:
                pdf.drawString(40, y, company.email)
                y -= 11
            if company.phone:
                pdf.drawString(40, y, f"Tel: {company.phone}")
                y -= 11
        pdf.setFont("Helvetica", 10)
        pdf.drawRightString(width - 40, y_pos, f"Emisión: {payload['issue_date']}")
        pdf.drawRightString(width - 40, y_pos - 12, f"Vencimiento: {payload['due_date']}")
        pdf.drawRightString(
            width - 40, y_pos - 24, f"Moneda: {payload['currency']} | IGI %: {payload['igi_rate']}"
        )
        return y - 12

    def draw_client_block(y_pos: float) -> float:
        y = y_pos
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(40, y, "Cliente")
        y -= 14
        pdf.setFont("Helvetica", 10)
        pdf.drawString(40, y, payload["client_name"])
        y -= 12
        pdf.drawString(40, y, f"Tax ID: {payload['client_tax_id']}")
        y -= 12
        if client:
            addr_parts = [
                client.address_line1 or client.address,
                client.address_line2,
                client.postal_code,
                client.city,
                client.country,
            ]
            addr = " ".join([p for p in addr_parts if p])
            for line in wrap_text(addr, max_width=400, font_size=9):
                pdf.drawString(40, y, line)
                y -= 11
        return y - 8

    def draw_table_header(y_pos: float) -> float:
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(40, y_pos, "CONCEPTO")
        pdf.drawRightString(430, y_pos, "CANTIDAD")
        pdf.drawRightString(width - 40, y_pos, "IMPORTE")
        pdf.line(40, y_pos - 2, width - 40, y_pos - 2)
        return y_pos - 14

    y = height - 40
    y = draw_header(y)
    y = draw_company_and_dates(y)
    y = draw_client_block(y)
    y = draw_table_header(y - 6)
    pdf.setFont("Helvetica", 9)

    for item in payload["lines"]:
        concept_lines = wrap_text(item["description"], max_width=360, font_size=9)
        line_height = 12
        needed_height = max(line_height * len(concept_lines), line_height) + 4
        if y - needed_height < 80:
            pdf.showPage()
            y = height - 40
            y = draw_header(y)
            y = draw_company_and_dates(y)
            y = draw_client_block(y)
            y = draw_table_header(y - 6)
            pdf.setFont("Helvetica", 9)

        start_y = y
        for idx, text in enumerate(concept_lines):
            pdf.drawString(40, start_y - (idx * line_height), text)
        pdf.drawRightString(430, start_y, f"{item['qty']:.2f}")
        pdf.drawRightString(width - 40, start_y, f"{item['total']:.2f} €")
        y = start_y - needed_height

    # Totales box a la derecha
    box_width = 180
    box_height = 50
    box_x = width - box_width - 40
    box_y = y - 10
    pdf.rect(box_x, box_y - box_height, box_width, box_height, stroke=1, fill=0)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(box_x + 8, box_y - 12, "Totales")
    pdf.setFont("Helvetica", 10)
    pdf.drawRightString(box_x + box_width - 8, box_y - 22, f"Subtotal: {payload['totals']['subtotal']:.2f} €")
    pdf.drawRightString(box_x + box_width - 8, box_y - 34, f"IGI: {payload['totals']['igi']:.2f} €")
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawRightString(box_x + box_width - 8, box_y - 46, f"TOTAL: {payload['totals']['total']:.2f} €")

    if payload.get("show_igi_exempt_footer"):
        pdf.setFont("Helvetica", 8)
        footer_text = (
            "Operació exempta de l’Impost General Indirecte, d’acord amb l’article 43 de la Llei 11/2012"
        )
        pdf.drawString(40, 40, footer_text)

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()
