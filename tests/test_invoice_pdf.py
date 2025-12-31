from datetime import date
from decimal import Decimal

import pytest

from app.pdf import build_invoice_pdf_payload, render_invoice_pdf
from app.models import Client, Company, Invoice, InvoiceLine


def _create_issued_invoice(client, db_session, issue_date: date):
    c = Client(name="Client PDF", tax_id="TXPDF")
    db_session.add(c)
    db_session.commit()
    client.post(
        "/invoices/new",
        data={
            "client_id": str(c.id),
            "issue_date": issue_date.isoformat(),
            "currency": "EUR",
            "igi_rate": "0",
            "notes": "",
        },
        follow_redirects=False,
    )
    inv = db_session.query(Invoice).order_by(Invoice.id.desc()).first()
    client.post(
        f"/invoices/{inv.id}/lines",
        data={"description": "l1", "qty": "1", "unit_price": "10", "discount_pct": "0"},
        follow_redirects=False,
    )
    client.post(f"/invoices/{inv.id}/issue", follow_redirects=False)
    db_session.refresh(inv)
    return inv


def test_pdf_for_issued_invoice_returns_pdf(client, db_session):
    inv = _create_issued_invoice(client, db_session, date(2026, 1, 1))
    resp = client.get(f"/invoices/{inv.id}/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.content.startswith(b"%PDF")


def test_pdf_rejected_for_draft(client, db_session):
    c = Client(name="DraftClient", tax_id="DRAFT")
    db_session.add(c)
    db_session.commit()
    client.post(
        "/invoices/new",
        data={
            "client_id": str(c.id),
            "issue_date": date.today().isoformat(),
            "currency": "EUR",
            "igi_rate": "0",
            "notes": "",
        },
        follow_redirects=False,
    )
    inv = db_session.query(Invoice).order_by(Invoice.id.desc()).first()
    resp = client.get(f"/invoices/{inv.id}/pdf")
    assert resp.status_code == 400
    assert not resp.headers["content-type"].startswith("application/pdf")


def test_pdf_uses_snapshot_client_name(client, db_session):
    inv = _create_issued_invoice(client, db_session, date(2026, 2, 1))
    original_name = inv.client_name_snapshot
    client_obj = db_session.get(Client, inv.client_id)
    client_obj.name = "Changed Client"
    db_session.commit()
    db_session.refresh(inv)

    payload = build_invoice_pdf_payload(inv, inv.lines)
    assert payload["client_name"] == original_name
    assert payload["client_name"] != "Changed Client"


def test_pdf_payload_issued_requires_client_name_snapshot(client, db_session):
    inv = _create_issued_invoice(client, db_session, date(2026, 3, 1))
    inv.client_name_snapshot = None
    db_session.commit()
    db_session.refresh(inv)

    with pytest.raises(ValueError):
        build_invoice_pdf_payload(inv, inv.lines)


def test_pdf_payload_issued_requires_client_tax_id_snapshot(client, db_session):
    inv = _create_issued_invoice(client, db_session, date(2026, 4, 1))
    inv.client_tax_id_snapshot = None
    db_session.commit()
    db_session.refresh(inv)

    with pytest.raises(ValueError):
        build_invoice_pdf_payload(inv, inv.lines)


def test_pdf_payload_footer_exempt_when_igi_zero(client, db_session):
    inv = _create_issued_invoice(client, db_session, date(2026, 5, 1))
    inv.igi_rate_snapshot = 0
    db_session.commit()
    db_session.refresh(inv)

    payload = build_invoice_pdf_payload(inv, inv.lines)
    assert payload["show_igi_exempt_footer"] is True


def test_pdf_payload_footer_not_exempt_when_igi_gt_zero(client, db_session):
    inv = _create_issued_invoice(client, db_session, date(2026, 6, 1))
    inv.igi_rate_snapshot = 5
    db_session.commit()
    db_session.refresh(inv)

    payload = build_invoice_pdf_payload(inv, inv.lines)
    assert payload["show_igi_exempt_footer"] is False


def test_pdf_render_stress_many_lines(client, db_session):
    inv = _create_issued_invoice(client, db_session, date(2026, 7, 1))
    # add a company for header
    comp = Company(name="ACME Consulting", tax_id="ACME123", address_line1="Main St 1", city="City", country="ES")
    db_session.add(comp)
    # add many lines directly (invoice already issued)
    for i in range(50):
        db_session.add(
            InvoiceLine(
                invoice_id=inv.id,
                description=f"Línea muy larga número {i} " * 3,
                qty=Decimal("1.00"),
                unit_price=Decimal("10.00"),
                discount_pct=Decimal("0"),
                sort_order=100 + i,
            )
        )
    db_session.commit()
    db_session.refresh(inv)
    payload = build_invoice_pdf_payload(inv, inv.lines)
    pdf_bytes = render_invoice_pdf(payload, company=comp, client=inv.client)
    assert pdf_bytes.startswith(b"%PDF")
