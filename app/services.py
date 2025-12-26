from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, List, Tuple

from .models import Invoice, InvoiceLine


def money_round(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compute_line_amounts(lines: Iterable[InvoiceLine]) -> List[Tuple[InvoiceLine, Decimal, Decimal, Decimal]]:
    result = []
    for line in lines:
        qty = Decimal(line.qty or 0)
        price = Decimal(line.unit_price or 0)
        discount_pct = Decimal(line.discount_pct or 0)
        line_subtotal = money_round(qty * price)
        line_discount = money_round(line_subtotal * (discount_pct / Decimal("100")))
        line_total = money_round(line_subtotal - line_discount)
        result.append((line, line_subtotal, line_discount, line_total))
    return result


def compute_totals(invoice: Invoice, lines: Iterable[InvoiceLine]):
    subtotal = Decimal("0")
    discount_total = Decimal("0")
    for _, line_subtotal, line_discount, _ in compute_line_amounts(lines):
        subtotal += line_subtotal
        discount_total += line_discount

    base = subtotal - discount_total
    igi_rate = Decimal(invoice.igi_rate or 0)
    igi_amount = money_round(base * (igi_rate / Decimal("100")))
    total = money_round(base + igi_amount)

    return {
        "subtotal": money_round(subtotal),
        "discount": money_round(discount_total),
        "base": money_round(base),
        "igi": igi_amount,
        "total": total,
    }
