from datetime import date

from app.models import Client, Invoice


def test_create_client(client, db_session):
    resp = client.post(
        "/clients",
        data={
            "name": "Acme",
            "tax_id": "X123",
            "address_line1": "Main",
            "address_line2": "",
            "city": "City",
            "postal_code": "000",
            "country": "CT",
            "phone": "123",
            "email": "a@test.com",
            "payment_terms_days": "5",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    saved = db_session.query(Client).filter_by(name="Acme").first()
    assert saved is not None

    list_resp = client.get("/clients")
    assert list_resp.status_code == 200


def test_delete_client_without_invoices(client, db_session):
    c = Client(name="Solo", tax_id=None)
    db_session.add(c)
    db_session.commit()

    resp = client.post(f"/clients/{c.id}/delete", follow_redirects=False)
    assert resp.status_code in (302, 303)
    db_session.refresh(c)
    assert c.is_deleted is True
    # No debe aparecer en listado activo
    resp_list = client.get("/clients")
    assert "Solo" not in resp_list.text
    # Debe aparecer en eliminados
    resp_deleted = client.get("/clients/deleted")
    assert "Solo" in resp_deleted.text


def test_delete_client_with_invoices_blocked(client, db_session):
    c = Client(name="Blocked", tax_id=None)
    db_session.add(c)
    db_session.commit()
    inv = Invoice(
        status="draft",
        series=None,
        number=None,
        issue_date=date.today(),
        due_date=date.today(),
        client_id=c.id,
        currency="EUR",
        igi_rate=0,
        notes="",
    )
    db_session.add(inv)
    db_session.commit()

    resp = client.post(f"/clients/{c.id}/delete", follow_redirects=False)
    assert resp.status_code in (400, 200)  # could render error template
    db_session.refresh(c)
    assert c.is_deleted is False


def test_clients_list_order_desc(client, db_session):
    older = Client(name="Old", tax_id=None)
    newer = Client(name="New", tax_id=None)
    db_session.add_all([older, newer])
    db_session.commit()

    resp = client.get("/clients")
    assert resp.status_code == 200
    body = resp.text
    pos_old = body.index("Old")
    pos_new = body.index("New")
    assert pos_new < pos_old  # newer appears first


def test_restore_deleted_client(client, db_session):
    c = Client(name="RestoreMe", tax_id=None, is_deleted=True)
    db_session.add(c)
    db_session.commit()

    resp = client.post(f"/clients/{c.id}/restore", follow_redirects=False)
    assert resp.status_code in (302, 303)
    db_session.refresh(c)
    assert c.is_deleted is False
    active = client.get("/clients")
    assert "RestoreMe" in active.text
