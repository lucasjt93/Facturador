from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from .models import Invoice, InvoiceLine


def money_round(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compute_totals(invoice: Invoice, lines: Iterable[InvoiceLine]):
    subtotal = Decimal("0")
    discount_total = Decimal("0")
    for line in lines:
        qty = Decimal(line.qty or 0)
        price = Decimal(line.unit_price or 0)
        discount_pct = Decimal(line.discount_pct or 0)
        line_subtotal = qty * price
        line_discount = line_subtotal * (discount_pct / Decimal("100"))
        subtotal += line_subtotal
        discount_total += line_discount

    base = subtotal - discount_total
    igi_rate = Decimal(invoice.igi_rate or 0)
    igi_amount = base * (igi_rate / Decimal("100"))
    total = base + igi_amount

    return {
        "subtotal": money_round(subtotal),
        "discount": money_round(discount_total),
        "base": money_round(base),
        "igi": money_round(igi_amount),
        "total": money_round(total),
    }
