from datetime import date, timedelta

from app.models import Client, Company, Invoice


def test_company_payment_terms_fallback(client, db_session):
    company = Company(name="Comp", payment_terms_days=10)
    db_session.add(company)
    db_session.commit()

    resp_client = client.post(
        "/clients",
        data={"name": "NoTerms", "tax_id": "T1", "payment_terms_days": ""},
        follow_redirects=False,
    )
    assert resp_client.status_code in (302, 303)
    created_client = db_session.query(Client).filter_by(name="NoTerms").first()
    assert created_client is not None

    issue = date.today()
    resp_inv = client.post(
        "/invoices/new",
        data={
            "client_id": str(created_client.id),
            "issue_date": issue.isoformat(),
            "currency": "EUR",
            "igi_rate": "0",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert resp_inv.status_code in (302, 303)
    inv = db_session.query(Invoice).order_by(Invoice.id.desc()).first()
    assert inv.due_date == issue + timedelta(days=10)


def test_client_payment_terms_override_company(client, db_session):
    company = Company(name="Comp2", payment_terms_days=3)
    db_session.add(company)
    db_session.commit()

    resp_client = client.post(
        "/clients",
        data={"name": "WithTerms", "tax_id": "T2", "payment_terms_days": "5"},
        follow_redirects=False,
    )
    assert resp_client.status_code in (302, 303)
    created_client = db_session.query(Client).filter_by(name="WithTerms").first()
    assert created_client is not None

    issue = date.today()
    resp_inv = client.post(
        "/invoices/new",
        data={
            "client_id": str(created_client.id),
            "issue_date": issue.isoformat(),
            "currency": "EUR",
            "igi_rate": "0",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert resp_inv.status_code in (302, 303)
    inv = db_session.query(Invoice).order_by(Invoice.id.desc()).first()
    assert inv.due_date == issue + timedelta(days=5)
