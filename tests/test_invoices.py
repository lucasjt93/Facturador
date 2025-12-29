from datetime import date, timedelta

from app.models import Client, Invoice, InvoiceLine


def create_client(db_session, name="ClientX"):
    c = Client(name=name, tax_id="TX")
    db_session.add(c)
    db_session.commit()
    return c


def test_create_invoice_draft(client, db_session):
    c = create_client(db_session)
    issue = date.today()
    resp = client.post(
        "/invoices/new",
        data={
            "client_id": str(c.id),
            "issue_date": issue.isoformat(),
            "currency": "EUR",
            "igi_rate": "0",
            "notes": "n",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    inv = db_session.query(Invoice).order_by(Invoice.id.desc()).first()
    assert inv.status == "draft"
    assert inv.issue_date == issue
    assert inv.due_date == issue  # fallback 0 days


def test_client_select_excludes_deleted(client, db_session):
    c1 = Client(name="Active", tax_id=None)
    c2 = Client(name="Deleted", tax_id=None, is_deleted=True)
    db_session.add_all([c1, c2])
    db_session.commit()
    resp = client.get("/invoices/new")
    assert resp.status_code == 200
    body = resp.text
    assert "Active" in body
    assert "Deleted" not in body


def test_issue_invoice(client, db_session):
    c = create_client(db_session)
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
    resp = client.post(f"/invoices/{inv.id}/issue", follow_redirects=False)
    assert resp.status_code in (302, 303, 400)
    db_session.refresh(inv)
    if not inv.lines:
        assert resp.status_code == 400
    else:
        assert inv.status == "issued"


def test_add_line_rejected_when_issued(client, db_session):
    c = create_client(db_session)
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
    # make it issued without lines
    db_session.refresh(inv)
    inv.status = "issued"
    db_session.commit()
    resp = client.post(
        f"/invoices/{inv.id}/lines",
        data={"description": "x", "qty": "1", "unit_price": "1", "discount_pct": "0"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert db_session.query(InvoiceLine).filter_by(invoice_id=inv.id).count() == 0


def test_delete_line_rejected_when_issued(client, db_session):
    c = create_client(db_session)
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
    line = InvoiceLine(
        invoice_id=inv.id, description="l1", qty=1, unit_price=1, discount_pct=0, sort_order=1
    )
    db_session.add(line)
    inv.status = "issued"
    db_session.commit()

    resp = client.post(
        f"/invoices/{inv.id}/lines/{line.id}/delete",
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert db_session.query(InvoiceLine).filter_by(id=line.id).first() is not None


def test_add_lines_sort_order_and_append(client, db_session):
    c = create_client(db_session)
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

    for i in range(3):
        resp = client.post(
            f"/invoices/{inv.id}/lines",
            data={
                "description": f"line{i}",
                "qty": "1",
                "unit_price": "1",
                "discount_pct": "0",
            },
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    orders = [ln.sort_order for ln in db_session.query(InvoiceLine).filter_by(invoice_id=inv.id).order_by(InvoiceLine.id)]
    assert orders == [1, 2, 3]

    # delete middle
    mid = db_session.query(InvoiceLine).filter_by(invoice_id=inv.id, sort_order=2).first()
    client.post(f"/invoices/{inv.id}/lines/{mid.id}/delete", follow_redirects=False)
    # add another should go to max+1 (4)
    client.post(
        f"/invoices/{inv.id}/lines",
        data={"description": "new", "qty": "1", "unit_price": "1", "discount_pct": "0"},
        follow_redirects=False,
    )
    orders = [ln.sort_order for ln in db_session.query(InvoiceLine).filter_by(invoice_id=inv.id).order_by(InvoiceLine.sort_order)]
    assert orders[-1] == max(orders)
    assert orders == sorted(orders)


def test_line_validations(client, db_session):
    c = create_client(db_session)
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

    bad_cases = [
        {"description": "bad", "qty": "0", "unit_price": "1", "discount_pct": "0"},
        {"description": "bad", "qty": "1", "unit_price": "-1", "discount_pct": "0"},
        {"description": "bad", "qty": "1", "unit_price": "1", "discount_pct": "-1"},
        {"description": "bad", "qty": "1", "unit_price": "1", "discount_pct": "101"},
    ]
    for data in bad_cases:
        resp = client.post(f"/invoices/{inv.id}/lines", data=data, follow_redirects=False)
        assert resp.status_code == 400
    assert db_session.query(InvoiceLine).filter_by(invoice_id=inv.id).count() == 0


def test_delete_invoice_cascades_lines(client, db_session):
    c = create_client(db_session)
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
    client.post(
        f"/invoices/{inv.id}/lines",
        data={"description": "l1", "qty": "1", "unit_price": "2", "discount_pct": "0"},
        follow_redirects=False,
    )
    client.post(f"/invoices/{inv.id}/delete", follow_redirects=False)
    assert db_session.query(Invoice).filter_by(id=inv.id).first() is None
    assert db_session.query(InvoiceLine).filter_by(invoice_id=inv.id).count() == 0


def test_smoke_pages(client, db_session):
    assert client.get("/clients").status_code == 200
    assert client.get("/invoices").status_code == 200

    c = create_client(db_session)
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
    assert client.get(f"/invoices/{inv.id}").status_code == 200


def _create_invoice_with_date(client, db_session, issue_date: date):
    c = create_client(db_session)
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
        data={"description": "l1", "qty": "1", "unit_price": "1", "discount_pct": "0"},
        follow_redirects=False,
    )
    return db_session.get(Invoice, inv.id)


def test_issue_assigns_number_format_TCYYNN(client, db_session):
    inv = _create_invoice_with_date(client, db_session, date(2026, 1, 15))
    resp = client.post(f"/invoices/{inv.id}/issue", follow_redirects=False)
    assert resp.status_code in (302, 303)
    db_session.refresh(inv)
    assert inv.invoice_number == "TC2601"


def test_sequence_increments_same_year(client, db_session):
    inv1 = _create_invoice_with_date(client, db_session, date(2026, 2, 1))
    inv2 = _create_invoice_with_date(client, db_session, date(2026, 3, 1))
    client.post(f"/invoices/{inv1.id}/issue", follow_redirects=False)
    client.post(f"/invoices/{inv2.id}/issue", follow_redirects=False)
    db_session.refresh(inv1)
    db_session.refresh(inv2)
    assert inv1.invoice_number == "TC2601"
    assert inv2.invoice_number == "TC2602"


def test_sequence_resets_next_year(client, db_session):
    inv1 = _create_invoice_with_date(client, db_session, date(2026, 5, 1))
    inv2 = _create_invoice_with_date(client, db_session, date(2027, 1, 1))
    client.post(f"/invoices/{inv1.id}/issue", follow_redirects=False)
    client.post(f"/invoices/{inv2.id}/issue", follow_redirects=False)
    db_session.refresh(inv1)
    db_session.refresh(inv2)
    assert inv1.invoice_number == "TC2601"
    assert inv2.invoice_number == "TC2701"


def test_reissue_idempotent_keeps_number(client, db_session):
    inv = _create_invoice_with_date(client, db_session, date(2026, 6, 1))
    client.post(f"/invoices/{inv.id}/issue", follow_redirects=False)
    db_session.refresh(inv)
    number_first = inv.invoice_number
    resp = client.post(f"/invoices/{inv.id}/issue", follow_redirects=False)
    assert resp.status_code in (302, 303)
    db_session.refresh(inv)
    assert inv.invoice_number == number_first
