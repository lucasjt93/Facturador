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

    margin_x = 40
    gap = 12
    invoice_box_w = 220
    invoice_box_h = 66

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

    def client_box_needed_height(box_w: float) -> float:
        pad_top = 14
        line_h = 11
        min_h = 70

        lines_count = 3  # Cliente, nombre, Tax ID

        if client:
            addr_parts = [
                client.address_line1 or client.address,
                client.address_line2,
                client.postal_code,
                client.city,
                client.country,
            ]
            addr = " ".join([p for p in addr_parts if p])
            addr_lines = wrap_text(addr, max_width=box_w - 2 * 8, font_size=9)
            lines_count += len(addr_lines)

        return max(min_h, pad_top + (lines_count * line_h) + 10)

    def company_header_needed_height(box_w: float) -> float:
        """
        Cabecera limpia (sin box). Calcula altura aproximada para que el layout no “cuelgue”.
        """
        pad_top = 0
        line_h = 10

        if not company:
            return invoice_box_h

        lines_count = 0
        lines_count += 1  # Nombre

        if company.tax_id:
            lines_count += 1

        addr_parts = [
            company.address_line1,
            company.address_line2,
            company.postal_code,
            company.city,
            company.country,
        ]
        addr = " ".join([p for p in addr_parts if p])
        addr_lines = wrap_text(addr, max_width=box_w, font_size=8)
        lines_count += len(addr_lines)

        if company.email:
            lines_count += 1
        if company.phone:
            lines_count += 1

        return max(invoice_box_h, pad_top + (lines_count * line_h) + 6)

    def draw_header(y_pos: float, box_h: int = invoice_box_h) -> float:
        """
        Company header SIN box: tipografía + jerarquía.
        Devuelve el y debajo del bloque.
        """
        box_w = 320
        x = margin_x

        box_h = int(company_header_needed_height(box_w))
        top_y = y_pos
        bottom_y = top_y - box_h

        if not company:
            return bottom_y - 12

        ty = top_y

        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(x, ty, company.name or "")
        ty -= 14

        pdf.setFont("Helvetica", 9)
        if company.tax_id:
            pdf.drawString(x, ty, f"NIF: {company.tax_id}")
            ty -= 12

        addr_parts = [
            company.address_line1,
            company.address_line2,
            company.postal_code,
            company.city,
            company.country,
        ]
        addr = " ".join([p for p in addr_parts if p])
        for line in wrap_text(addr, max_width=box_w, font_size=8):
            if ty <= bottom_y + 10:
                break
            pdf.setFont("Helvetica", 8)
            pdf.drawString(x, ty, line)
            ty -= 10

        pdf.setFont("Helvetica", 8)
        if company.email and ty > bottom_y + 10:
            pdf.drawString(x, ty, company.email)
            ty -= 10
        if company.phone and ty > bottom_y + 10:
            pdf.drawString(x, ty, f"Tel: {company.phone}")
            ty -= 10

        # línea separadora fina (ancla el header con el resto)
        pdf.setLineWidth(0.6)
        pdf.setStrokeColorRGB(0.75, 0.75, 0.75)
        pdf.line(margin_x, bottom_y + 8 , width - margin_x, bottom_y + 8)

        pdf.setStrokeColorRGB(0, 0, 0)
        pdf.setLineWidth(1)

        return bottom_y - 4

    def draw_company_and_dates(y_pos: float, box_h: int) -> float:
        box_w = invoice_box_w
        box_x = width - margin_x - box_w
        box_y = y_pos - box_h

        pdf.setLineWidth(0.8)
        pdf.setStrokeColorRGB(0.2, 0.2, 0.2)
        pdf.rect(box_x, box_y, box_w, box_h, stroke=1, fill=0)

        pad_x = 8
        line_h = 12
        y_text = box_y + box_h - 14

        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(box_x + pad_x, y_text, f"Factura Nº: {payload['invoice_number']}")
        y_text -= line_h

        pdf.setFont("Helvetica", 9)
        pdf.drawString(box_x + pad_x, y_text, f"Emisión: {payload['issue_date']}")
        y_text -= line_h
        pdf.drawString(box_x + pad_x, y_text, f"Vencimiento: {payload['due_date']}")
        y_text -= line_h
        pdf.drawString(box_x + pad_x, y_text, f"Moneda: {payload['currency']} | IGI: {payload['igi_rate']}%")

        return box_y - 12

    def draw_client_block(y_pos: float, box_h: int) -> float:
        box_x = margin_x
        box_w = width - 2 * margin_x - invoice_box_w - gap
        box_y = y_pos - box_h

        pad_x = 8
        pad_top = 14
        line_h = 11

        lines: List[str] = [
            "Cliente",
            payload["client_name"],
            f"Tax ID: {payload['client_tax_id']}",
        ]

        if client:
            addr_parts = [
                client.address_line1 or client.address,
                client.address_line2,
                client.postal_code,
                client.city,
                client.country,
            ]
            addr = " ".join([p for p in addr_parts if p])
            addr_lines = wrap_text(addr, max_width=box_w - 2 * pad_x, font_size=9)
            lines.extend(addr_lines)

        pdf.setLineWidth(0.8)  # FIX: antes estaba 0. y el borde podía “desaparecer”
        pdf.setStrokeColorRGB(0.2, 0.2, 0.2)
        pdf.rect(box_x, box_y, box_w, box_h, stroke=1, fill=0)

        tx = box_x + pad_x
        ty = box_y + box_h - pad_top

        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(tx, ty, lines[0])
        ty -= 14

        pdf.setFont("Helvetica", 9)
        for line in lines[1:]:
            if ty <= box_y + 10:
                break
            pdf.drawString(tx, ty, line)
            ty -= line_h

        return box_y - 12

    def draw_table_header(y_pos: float) -> float:
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(margin_x, y_pos, "CONCEPTO")
        pdf.drawRightString(430, y_pos, "CANTIDAD")
        pdf.drawRightString(width - margin_x, y_pos, "IMPORTE")
        pdf.line(margin_x, y_pos - 2, width - margin_x, y_pos - 2)
        return y_pos - 14

    def header_block() -> float:
        y_top = height - 40

        client_w = width - 2 * margin_x - invoice_box_w - gap
        needed_client_h = client_box_needed_height(client_w)
        row2_h = max(needed_client_h, invoice_box_h)

        company_h = int(company_header_needed_height(320))
        company_top = y_top - (row2_h - company_h)
        y_after_company = draw_header(company_top, box_h=company_h)

        row2_top = y_after_company - 6
        y_after_client = draw_client_block(row2_top, box_h=int(row2_h))
        y_after_invoice = draw_company_and_dates(row2_top, box_h=int(row2_h))

        return min(y_after_client, y_after_invoice)

    y = header_block()
    y = draw_table_header(y - 6)
    pdf.setFont("Helvetica", 9)

    for item in payload["lines"]:
        concept_lines = wrap_text(item["description"], max_width=360, font_size=9)
        line_height = 12
        needed_height = max(line_height * len(concept_lines), line_height) + 4

        if y - needed_height < 80:
            pdf.showPage()
            y = header_block()
            y = draw_table_header(y - 6)
            pdf.setFont("Helvetica", 9)

        start_y = y
        for idx, text in enumerate(concept_lines):
            pdf.drawString(margin_x, start_y - (idx * line_height), text)

        pdf.drawRightString(430, start_y, f"{item['qty']:.2f}")
        pdf.drawRightString(width - margin_x, start_y, f"{item['total']:.2f} €")
        y = start_y - needed_height


    footer_y = 30

    box_width = 190
    box_height = 66
    box_x = width - box_width - margin_x

    footer_gap = 22
    bottom_limit = footer_y + footer_gap

    box_top = bottom_limit + box_height
    box_y = box_top - box_height

    pdf.setLineWidth(0.8)
    pdf.setStrokeColorRGB(0.2, 0.2, 0.2)
    pdf.rect(box_x, box_y, box_width, box_height, stroke=1, fill=0)

    pad_x = 10
    y_cursor = box_top - 14

    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(box_x + pad_x, y_cursor, "Totales")
    y_cursor -= 16

    pdf.setFont("Helvetica", 10)
    pdf.drawRightString(
        box_x + box_width - pad_x,
        y_cursor,
        f"Base: {payload['totals']['subtotal']:.2f} €",
    )
    y_cursor -= 14

    pdf.drawRightString(
        box_x + box_width - pad_x,
        y_cursor,
        f"IGI: {payload['totals']['igi']:.2f} €",
    )
    y_cursor -= 18

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawRightString(
        box_x + box_width - pad_x,
        y_cursor,
        f"TOTAL: {payload['totals']['total']:.2f} €",
    )

    if payload.get("show_igi_exempt_footer"):
        # Línea separadora antes del texto legal
        pdf.setLineWidth(0.6)
        pdf.setStrokeColorRGB(0.75, 0.75, 0.75)
        pdf.line(margin_x, footer_y + 14, width - margin_x, footer_y + 14)

        pdf.setStrokeColorRGB(0, 0, 0)
        pdf.setLineWidth(1)

        pdf.setFont("Helvetica", 8)
        footer_text = (
            "Operació exempta de l’Impost General Indirecte, d’acord amb l’article 43 de la Llei 11/2012"
        )
        pdf.drawCentredString(width / 2, footer_y, footer_text)

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()
