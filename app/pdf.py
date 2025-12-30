from decimal import Decimal
from io import BytesIO
from typing import Dict, Iterable, List

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .models import Invoice, InvoiceLine
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
        igi_rate = invoice.igi_rate_snapshot
    else:
        client_name = invoice.client_name_snapshot or (invoice.client.name if invoice.client else "")
        client_tax_id = invoice.client_tax_id_snapshot or (invoice.client.tax_id if invoice.client else "")
        igi_rate = invoice.igi_rate_snapshot if invoice.igi_rate_snapshot is not None else invoice.igi_rate

    return {
        "invoice_number": invoice.invoice_number or str(invoice.id),
        "status": invoice.status,
        "client_name": client_name,
        "client_tax_id": client_tax_id,
        "issue_date": invoice.issue_date,
        "due_date": invoice.due_date,
        "currency": invoice.currency,
        "igi_rate": igi_rate,
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


def render_invoice_pdf(payload: Dict) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 40
    pdf.setFont("Helvetica-Bold", 16)
    title = f"Factura {payload['invoice_number']}"
    pdf.drawString(40, y, title)

    pdf.setFont("Helvetica", 10)
    y -= 18
    pdf.drawString(40, y, f"Estado: {payload['status']}")
    y -= 14
    pdf.drawString(40, y, f"Cliente: {payload['client_name']}")
    y -= 14
    pdf.drawString(40, y, f"Tax ID: {payload['client_tax_id']}")
    y -= 14
    pdf.drawString(40, y, f"Emisión: {payload['issue_date']}   Vencimiento: {payload['due_date']}")
    y -= 14
    pdf.drawString(
        40,
        y,
        f"Moneda: {payload['currency']}   IGI %: {payload['igi_rate']}",
    )

    y -= 22
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(40, y, "Líneas")
    y -= 16
    pdf.setFont("Helvetica", 9)
    headers = ["#", "Descripción", "Cantidad", "Precio", "Desc %", "Importe"]
    col_x = [40, 70, 320, 400, 470, 520]
    for hx, text in zip(col_x, headers):
        pdf.drawString(hx, y, text)
    y -= 12

    for item in payload["lines"]:
        if y < 60:
            pdf.showPage()
            y = height - 60
            pdf.setFont("Helvetica", 9)
        pdf.drawString(col_x[0], y, str(item["index"]))
        pdf.drawString(col_x[1], y, item["description"][:60])
        pdf.drawRightString(col_x[2] + 40, y, f"{item['qty']:.2f}")
        pdf.drawRightString(col_x[3] + 40, y, f"{item['unit_price']:.2f}")
        pdf.drawRightString(col_x[4] + 30, y, f"{item['discount_pct']:.2f}")
        pdf.drawRightString(col_x[5] + 40, y, f"{item['total']:.2f}")
        y -= 12

    totals = payload["totals"]
    y -= 18
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(40, y, "Totales")
    pdf.setFont("Helvetica", 10)
    y -= 14
    pdf.drawString(40, y, f"Subtotal: {totals['subtotal']:.2f} {payload['currency']}")
    y -= 14
    pdf.drawString(40, y, f"IGI: {totals['igi']:.2f} {payload['currency']}")
    y -= 14
    pdf.drawString(40, y, f"Total: {totals['total']:.2f} {payload['currency']}")

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()
