from datetime import date

from app.models import Client, Invoice, InvoiceLine


def _create_company(client):
    return client.post(
        "/company",
        data={
            "name": "Comp A",
            "tax_id": "TA",
            "phone": "",
            "address_line1": "",
            "address_line2": "",
            "city": "",
            "postal_code": "",
            "country": "",
            "email": "",
            "bank_account": "",
            "bank_swift": "",
            "payment_terms_days": "",
            "notes": "",
        },
        follow_redirects=False,
    )


def _create_client_via_form(client, name="Client A"):
    resp = client.post(
        "/clients",
        data={
            "name": name,
            "tax_id": "TX",
            "address_line1": "",
            "address_line2": "",
            "city": "",
            "postal_code": "",
            "country": "",
            "phone": "",
            "email": "",
            "payment_terms_days": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    return name


def _create_invoice_with_line(client, db_session, issue_date: date, client_obj: Client):
    resp = client.post(
        "/invoices/new",
        data={
            "client_id": str(client_obj.id),
            "issue_date": issue_date.isoformat(),
            "currency": "EUR",
            "igi_rate": "0",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    inv = db_session.query(Invoice).order_by(Invoice.id.desc()).first()
    # create line
    client.post(
        f"/invoices/{inv.id}/lines",
        data={"description": "L1", "qty": "1", "unit_price": "10", "discount_pct": "0"},
        follow_redirects=False,
    )
    return inv


def test_issued_invoice_reflects_client_changes_or_not(client, db_session):
    _create_company(client)
    name_initial = _create_client_via_form(client, "Cliente Inicial")
    client_obj = db_session.query(Client).filter_by(name=name_initial).first()
    invoice = _create_invoice_with_line(client, db_session, date(2026, 1, 1), client_obj)
    client.post(f"/invoices/{invoice.id}/issue", follow_redirects=False)

    resp_before = client.get(f"/invoices/{invoice.id}")
    assert resp_before.status_code == 200
    assert "Cliente Inicial" in resp_before.text

    # Edit client name
    client.post(
        f"/clients/{client_obj.id}/edit",
        data={
            "name": "Cliente Modificado",
            "tax_id": "TX2",
            "address_line1": "",
            "address_line2": "",
            "city": "",
            "postal_code": "",
            "country": "",
            "phone": "",
            "email": "",
            "payment_terms_days": "",
        },
        follow_redirects=False,
    )
    resp_after = client.get(f"/invoices/{invoice.id}")
    assert resp_after.status_code == 200
    # Snapshot: no refleja el cambio
    assert "Cliente Inicial" in resp_after.text
    assert "Cliente Modificado" not in resp_after.text


def test_issued_invoice_reflects_company_changes_or_not(client, db_session):
    _create_company(client)
    name_initial = _create_client_via_form(client, "Cliente Cia")
    client_obj = db_session.query(Client).filter_by(name=name_initial).first()
    invoice = _create_invoice_with_line(client, db_session, date(2026, 1, 1), client_obj)
    client.post(f"/invoices/{invoice.id}/issue", follow_redirects=False)

    resp_before = client.get(f"/invoices/{invoice.id}")
    assert resp_before.status_code == 200
    # La plantilla actual no muestra datos de Company en el detalle.
    assert "Comp A" not in resp_before.text

    # Edit company name
    client.post(
        "/company",
        data={
            "name": "Comp Modificada",
            "tax_id": "TA",
            "phone": "",
            "address_line1": "",
            "address_line2": "",
            "city": "",
            "postal_code": "",
            "country": "",
            "email": "",
            "bank_account": "",
            "bank_swift": "",
            "payment_terms_days": "",
            "notes": "",
        },
        follow_redirects=False,
    )
    resp_after = client.get(f"/invoices/{invoice.id}")
    assert resp_after.status_code == 200
    # Sigue sin mostrarse el nombre de la empresa (la vista no lo renderiza).
    assert "Comp Modificada" not in resp_after.text


def test_issued_invoice_totals_are_computed_live(client, db_session):
    _create_company(client)
    name_initial = _create_client_via_form(client, "Cliente Totales")
    client_obj = db_session.query(Client).filter_by(name=name_initial).first()
    invoice = _create_invoice_with_line(client, db_session, date(2026, 1, 1), client_obj)
    client.post(f"/invoices/{invoice.id}/issue", follow_redirects=False)

    resp_before = client.get(f"/invoices/{invoice.id}")
    assert resp_before.status_code == 200
    assert "10.00" in resp_before.text

    # Modificamos la línea directamente en DB para ver si la vista refleja cambio (live computation)
    line = db_session.query(InvoiceLine).filter_by(invoice_id=invoice.id).first()
    line.unit_price = 20
    db_session.commit()

    resp_after = client.get(f"/invoices/{invoice.id}")
    assert resp_after.status_code == 200
    # Si se calcula en vivo desde líneas, debería reflejar 20.00; si estuviera persistido, seguiría 10.00
    assert "20.00" in resp_after.text


def test_issued_invoice_does_not_reflect_client_changes_after_snapshot(client, db_session):
    _create_company(client)
    name_initial = _create_client_via_form(client, "Cliente Snapshot")
    client_obj = db_session.query(Client).filter_by(name=name_initial).first()
    invoice = _create_invoice_with_line(client, db_session, date(2026, 1, 1), client_obj)
    client.post(f"/invoices/{invoice.id}/issue", follow_redirects=False)
    resp_before = client.get(f"/invoices/{invoice.id}")
    assert resp_before.status_code == 200
    assert "Cliente Snapshot" in resp_before.text

    client.post(
        f"/clients/{client_obj.id}/edit",
        data={
            "name": "Cliente Cambiado",
            "tax_id": "TX3",
            "address_line1": "",
            "address_line2": "",
            "city": "",
            "postal_code": "",
            "country": "",
            "phone": "",
            "email": "",
            "payment_terms_days": "",
        },
        follow_redirects=False,
    )
    resp_after = client.get(f"/invoices/{invoice.id}")
    assert resp_after.status_code == 200
    # Esperado tras snapshot: NO refleja el cambio
    assert "Cliente Snapshot" in resp_after.text
    assert "Cliente Cambiado" not in resp_after.text


def test_issued_invoice_totals_do_not_change_if_lines_change(client, db_session):
    _create_company(client)
    name_initial = _create_client_via_form(client, "Cliente Totales Snapshot")
    client_obj = db_session.query(Client).filter_by(name=name_initial).first()
    invoice = _create_invoice_with_line(client, db_session, date(2026, 1, 1), client_obj)
    client.post(f"/invoices/{invoice.id}/issue", follow_redirects=False)

    resp_before = client.get(f"/invoices/{invoice.id}")
    assert resp_before.status_code == 200
    assert "10.00" in resp_before.text

    line = db_session.query(InvoiceLine).filter_by(invoice_id=invoice.id).first()
    line.unit_price = 20
    db_session.commit()

    resp_after = client.get(f"/invoices/{invoice.id}")
    assert resp_after.status_code == 200
    # Tras snapshot, el total debería permanecer en 10.00
    assert "Total: 10.00" in resp_after.text


def test_reissue_does_not_recompute_snapshot(client, db_session):
    _create_company(client)
    name_initial = _create_client_via_form(client, "Cliente Reissue")
    client_obj = db_session.query(Client).filter_by(name=name_initial).first()
    invoice = _create_invoice_with_line(client, db_session, date(2026, 1, 1), client_obj)
    client.post(f"/invoices/{invoice.id}/issue", follow_redirects=False)
    resp_first = client.get(f"/invoices/{invoice.id}")
    assert "10.00" in resp_first.text

    line = db_session.query(InvoiceLine).filter_by(invoice_id=invoice.id).first()
    line.unit_price = 30
    db_session.commit()

    client.post(f"/invoices/{invoice.id}/issue", follow_redirects=False)
    resp_after = client.get(f"/invoices/{invoice.id}")
    # snapshot no debe recalcularse
    assert "Total: 10.00" in resp_after.text
