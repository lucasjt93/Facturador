from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, Optional

from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload, selectinload

from .database import get_db
from .models import Client, Company, Invoice, InvoiceLine
from .services import compute_line_amounts, compute_totals

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/clients", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get("/clients", response_class=HTMLResponse)
async def list_clients(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    clients = db.query(Client).order_by(Client.name).all()
    company = _get_company(db)
    effective_terms = {
        client.id: _effective_payment_terms_days(client, company) for client in clients
    }
    return templates.TemplateResponse(
        "clients/list.html",
        {
            "request": request,
            "clients": clients,
            "default_payment_terms_days": company.payment_terms_days if company else None,
            "effective_payment_terms_days": effective_terms,
        },
    )


@app.get("/clients/new", response_class=HTMLResponse)
async def new_client(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "clients/form.html",
        {
            "request": request,
            "form_action": "/clients",
            "form_title": "Nuevo Cliente",
            "client": {
                "name": "",
                "tax_id": "",
                "address_line1": "",
                "address_line2": "",
                "city": "",
                "postal_code": "",
                "country": "",
                "phone": "",
                "email": "",
                "payment_terms_days": "",
            },
            "errors": {},
        },
    )


def _validate_client_form(data: Dict[str, str]) -> Dict[str, str]:
    errors: Dict[str, str] = {}
    if not data.get("name", "").strip():
        errors["name"] = "El nombre es requerido."
    if data.get("payment_terms_days"):
        try:
            days = int(data["payment_terms_days"])
            if days < 0:
                errors["payment_terms_days"] = "Los días de pago deben ser 0 o más."
        except ValueError:
            errors["payment_terms_days"] = "Los días de pago deben ser numéricos."
    return errors


def _validate_company_form(data: Dict[str, str]) -> Dict[str, str]:
    errors: Dict[str, str] = {}
    if not data.get("name", "").strip():
        errors["name"] = "El nombre de la empresa es requerido."
    if data.get("payment_terms_days"):
        try:
            days = int(data["payment_terms_days"])
            if days < 0:
                errors["payment_terms_days"] = "Los días de pago deben ser 0 o más."
        except ValueError:
            errors["payment_terms_days"] = "Los días de pago deben ser numéricos."
    return errors


def _parse_payment_terms_days(value: str) -> Optional[int]:
    if not value:
        return None
    days = int(value)
    if days < 0:
        raise ValueError("negative")
    return days


@app.post("/clients", response_class=HTMLResponse)
async def create_client(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    form = await request.form()
    data = {
        "name": form.get("name", "").strip(),
        "tax_id": form.get("tax_id", "").strip(),
        "address_line1": form.get("address_line1", "").strip(),
        "address_line2": form.get("address_line2", "").strip(),
        "city": form.get("city", "").strip(),
        "postal_code": form.get("postal_code", "").strip(),
        "country": form.get("country", "").strip(),
        "phone": form.get("phone", "").strip(),
        "email": form.get("email", "").strip(),
        "payment_terms_days": form.get("payment_terms_days", "").strip(),
    }
    errors = _validate_client_form(data)
    if errors:
        return templates.TemplateResponse(
            "clients/form.html",
            {
                "request": request,
                "form_action": "/clients",
                "form_title": "Nuevo Cliente",
                "client": data,
                "errors": errors,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    payment_terms_days = (
        _parse_payment_terms_days(data["payment_terms_days"])
        if data["payment_terms_days"]
        else None
    )

    client = Client(
        name=data["name"],
        tax_id=data["tax_id"],
        address=data["address_line1"],  # legacy single-line convenience
        address_line1=data["address_line1"],
        address_line2=data["address_line2"],
        city=data["city"],
        postal_code=data["postal_code"],
        country=data["country"],
        phone=data["phone"],
        email=data["email"],
        payment_terms_days=payment_terms_days,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return RedirectResponse(url="/clients", status_code=status.HTTP_303_SEE_OTHER)


def _get_client(db: Session, client_id: int) -> Optional[Client]:
    return db.query(Client).filter(Client.id == client_id).first()


def _get_company(db: Session) -> Optional[Company]:
    return db.query(Company).first()


def _effective_payment_terms_days(
    client: Client, company: Optional[Company]
) -> Optional[int]:
    if client.payment_terms_days is not None:
        return client.payment_terms_days
    if company and company.payment_terms_days is not None:
        return company.payment_terms_days
    return None


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


@app.get("/clients/{client_id}/edit", response_class=HTMLResponse)
async def edit_client(
    client_id: int, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    client = _get_client(db, client_id)
    if not client:
        return HTMLResponse(content="Cliente no encontrado", status_code=404)

    return templates.TemplateResponse(
        "clients/form.html",
        {
            "request": request,
            "form_action": f"/clients/{client_id}/edit",
            "form_title": "Editar Cliente",
            "client": {
                "id": client.id,
                "name": client.name or "",
                "tax_id": client.tax_id or "",
                "address_line1": client.address_line1 or client.address or "",
                "address_line2": client.address_line2 or "",
                "city": client.city or "",
                "postal_code": client.postal_code or "",
                "country": client.country or "",
                "phone": client.phone or "",
                "email": client.email or "",
                "payment_terms_days": "" if client.payment_terms_days is None else client.payment_terms_days,
            },
            "errors": {},
        },
    )


@app.post("/clients/{client_id}/edit", response_class=HTMLResponse)
async def update_client(
    client_id: int, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    client = _get_client(db, client_id)
    if not client:
        return HTMLResponse(content="Cliente no encontrado", status_code=404)

    form = await request.form()
    data = {
        "name": form.get("name", "").strip(),
        "tax_id": form.get("tax_id", "").strip(),
        "address_line1": form.get("address_line1", "").strip(),
        "address_line2": form.get("address_line2", "").strip(),
        "city": form.get("city", "").strip(),
        "postal_code": form.get("postal_code", "").strip(),
        "country": form.get("country", "").strip(),
        "phone": form.get("phone", "").strip(),
        "email": form.get("email", "").strip(),
        "payment_terms_days": form.get("payment_terms_days", "").strip(),
    }
    errors = _validate_client_form(data)
    if errors:
        return templates.TemplateResponse(
            "clients/form.html",
            {
                "request": request,
                "form_action": f"/clients/{client_id}/edit",
                "form_title": "Editar Cliente",
                "client": {"id": client_id, **data},
                "errors": errors,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    client.name = data["name"]
    client.tax_id = data["tax_id"]
    client.address = data["address_line1"]
    client.address_line1 = data["address_line1"]
    client.address_line2 = data["address_line2"]
    client.city = data["city"]
    client.postal_code = data["postal_code"]
    client.country = data["country"]
    client.phone = data["phone"]
    client.email = data["email"]
    client.payment_terms_days = (
        _parse_payment_terms_days(data["payment_terms_days"])
        if data["payment_terms_days"]
        else None
    )
    db.commit()
    return RedirectResponse(url="/clients", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/company", response_class=HTMLResponse)
async def company_settings(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    company = _get_company(db)
    company_data = {
        "name": company.name if company else "",
        "tax_id": company.tax_id if company else "",
        "phone": company.phone if company else "",
        "address_line1": company.address_line1 if company else "",
        "address_line2": company.address_line2 if company else "",
        "city": company.city if company else "",
        "postal_code": company.postal_code if company else "",
        "country": company.country if company else "",
        "email": company.email if company else "",
        "bank_account": company.bank_account if company else "",
        "bank_swift": company.bank_swift if company else "",
        "payment_terms_days": "" if not company or company.payment_terms_days is None else company.payment_terms_days,
        "notes": company.notes if company else "",
    }
    return templates.TemplateResponse(
        "company/form.html",
        {
            "request": request,
            "form_action": "/company",
            "form_title": "Datos de la empresa",
            "company": company_data,
            "errors": {},
        },
    )


@app.post("/company", response_class=HTMLResponse)
async def update_company(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    form = await request.form()
    data = {
        "name": form.get("name", "").strip(),
        "tax_id": form.get("tax_id", "").strip(),
        "phone": form.get("phone", "").strip(),
        "address_line1": form.get("address_line1", "").strip(),
        "address_line2": form.get("address_line2", "").strip(),
        "city": form.get("city", "").strip(),
        "postal_code": form.get("postal_code", "").strip(),
        "country": form.get("country", "").strip(),
        "email": form.get("email", "").strip(),
        "bank_account": form.get("bank_account", "").strip(),
        "bank_swift": form.get("bank_swift", "").strip(),
        "payment_terms_days": form.get("payment_terms_days", "").strip(),
        "notes": form.get("notes", "").strip(),
    }
    errors = _validate_company_form(data)
    if errors:
        return templates.TemplateResponse(
            "company/form.html",
            {
                "request": request,
                "form_action": "/company",
                "form_title": "Datos de la empresa",
                "company": data,
                "errors": errors,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    company = _get_company(db)
    parsed_payment_terms_days = (
        _parse_payment_terms_days(data["payment_terms_days"])
        if data["payment_terms_days"]
        else None
    )
    if company:
        for key, value in data.items():
            if key == "payment_terms_days":
                setattr(company, key, parsed_payment_terms_days)
            else:
                setattr(company, key, value)
    else:
        company = Company(
            **{
                **data,
                "payment_terms_days": parsed_payment_terms_days,
            }
        )
        db.add(company)
    db.commit()
    return RedirectResponse(url="/company", status_code=status.HTTP_303_SEE_OTHER)


def _invoice_status_guard(invoice: Invoice) -> Optional[HTMLResponse]:
    if invoice.status != "draft":
        return HTMLResponse(
            content="La factura no está en borrador, no se puede modificar.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return None


def _validate_line_form(data: Dict[str, str]) -> Dict[str, str]:
    errors: Dict[str, str] = {}
    desc = data.get("description", "").strip()
    if not desc:
        errors["description"] = "La descripción es obligatoria."
    elif len(desc) > 500:
        errors["description"] = "Máximo 500 caracteres."

    # qty
    try:
        qty_val = Decimal(data.get("qty", "0"))
        if qty_val <= 0:
            errors["qty"] = "La cantidad debe ser mayor a 0."
    except Exception:
        errors["qty"] = "Valor numérico inválido."

    # unit_price
    try:
        price_val = Decimal(data.get("unit_price", "0"))
        if price_val < 0:
            errors["unit_price"] = "El precio no puede ser negativo."
    except Exception:
        errors["unit_price"] = "Valor numérico inválido."

    # discount_pct
    try:
        disc_val = Decimal(data.get("discount_pct", "0"))
        if disc_val < 0 or disc_val > 100:
            errors["discount_pct"] = "El descuento debe estar entre 0 y 100."
    except Exception:
        errors["discount_pct"] = "Valor numérico inválido."

    # sort_order
    try:
        sort_val = int(data.get("sort_order", "1"))
        if sort_val < 1:
            errors["sort_order"] = "El orden debe ser entero positivo."
    except Exception:
        errors["sort_order"] = "Valor numérico inválido."

    return errors


@app.post("/invoices/{invoice_id}/lines", response_class=HTMLResponse)
async def add_line(
    invoice_id: int, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    invoice = (
        db.query(Invoice)
        .options(joinedload(Invoice.client), selectinload(Invoice.lines))
        .filter(Invoice.id == invoice_id)
        .first()
    )
    if not invoice:
        return HTMLResponse(content="Factura no encontrada", status_code=404)
    guard = _invoice_status_guard(invoice)
    if guard:
        return guard

    form = await request.form()
    data = {
        "description": form.get("description", "").strip(),
        "qty": form.get("qty", "").strip() or "1",
        "unit_price": form.get("unit_price", "").strip() or "0",
        "discount_pct": form.get("discount_pct", "").strip() or "0",
        "sort_order": form.get("sort_order", "").strip() or "1",
    }
    errors = _validate_line_form(data)
    if errors:
        lines = sorted(invoice.lines, key=lambda l: (l.sort_order, l.id))
        totals = compute_totals(invoice, lines)
        line_amounts = [
            {"line": ln, "subtotal": ls, "discount": ld, "total": lt}
            for ln, ls, ld, lt in compute_line_amounts(lines)
        ]
        return templates.TemplateResponse(
            "invoices/detail.html",
            {
                "request": request,
                "invoice": invoice,
                "client": invoice.client,
                "lines": lines,
                "line_amounts": line_amounts,
                "totals": totals,
                "errors": errors,
                "form_action": f"/invoices/{invoice.id}/lines",
                "form_data": data,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    line = InvoiceLine(
        invoice_id=invoice.id,
        description=data["description"],
        qty=Decimal(data["qty"]),
        unit_price=Decimal(data["unit_price"]),
        discount_pct=Decimal(data["discount_pct"]),
        sort_order=int(data["sort_order"]),
    )
    db.add(line)
    db.commit()
    return RedirectResponse(
        url=f"/invoices/{invoice.id}", status_code=status.HTTP_303_SEE_OTHER
    )


@app.post("/invoices/{invoice_id}/lines/{line_id}/delete", response_class=HTMLResponse)
async def delete_line(
    invoice_id: int, line_id: int, db: Session = Depends(get_db)
) -> HTMLResponse:
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        return HTMLResponse(content="Factura no encontrada", status_code=404)
    guard = _invoice_status_guard(invoice)
    if guard:
        return guard

    line = (
        db.query(InvoiceLine)
        .filter(InvoiceLine.id == line_id, InvoiceLine.invoice_id == invoice_id)
        .first()
    )
    if not line:
        return HTMLResponse(content="Línea no encontrada", status_code=404)

    db.delete(line)
    db.commit()
    return RedirectResponse(
        url=f"/invoices/{invoice.id}", status_code=status.HTTP_303_SEE_OTHER
    )


@app.post("/invoices/{invoice_id}/issue", response_class=HTMLResponse)
async def issue_invoice(
    invoice_id: int, db: Session = Depends(get_db)
) -> HTMLResponse:
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        return HTMLResponse(content="Factura no encontrada", status_code=404)
    if invoice.status != "draft":
        return HTMLResponse(
            content="La factura ya fue emitida o no está en borrador.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    invoice.status = "issued"
    db.commit()
    return RedirectResponse(
        url=f"/invoices/{invoice.id}", status_code=status.HTTP_303_SEE_OTHER
    )


@app.get("/invoices", response_class=HTMLResponse)
async def list_invoices(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    invoices = (
        db.query(Invoice)
        .options(joinedload(Invoice.client), selectinload(Invoice.lines))
        .order_by(Invoice.issue_date.desc(), Invoice.id.desc())
        .all()
    )
    invoice_totals = {}
    for inv in invoices:
        lines = sorted(inv.lines, key=lambda l: (l.sort_order, l.id))
        invoice_totals[inv.id] = compute_totals(inv, lines)
    return templates.TemplateResponse(
        "invoices/list.html",
        {"request": request, "invoices": invoices, "invoice_totals": invoice_totals},
    )


@app.get("/invoices/new", response_class=HTMLResponse)
async def new_invoice(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    clients = db.query(Client).order_by(Client.name).all()
    today_str = date.today().isoformat()
    return templates.TemplateResponse(
        "invoices/new.html",
        {
            "request": request,
            "clients": clients,
            "form_action": "/invoices/new",
            "data": {
                "client_id": "",
                "issue_date": today_str,
                "currency": "EUR",
                "igi_rate": "0",
                "notes": "",
            },
            "errors": {},
        },
    )


def _validate_invoice_form(data: Dict[str, str], db: Session) -> Dict[str, str]:
    errors: Dict[str, str] = {}
    client_id = data.get("client_id")
    if not client_id:
        errors["client_id"] = "Selecciona un cliente."
    else:
        try:
            int(client_id)
        except ValueError:
            errors["client_id"] = "Cliente inválido."
        else:
            if not db.query(Client).filter(Client.id == int(client_id)).first():
                errors["client_id"] = "Cliente no encontrado."

    if data.get("issue_date"):
        try:
            _parse_date(data["issue_date"])
        except ValueError:
            errors["issue_date"] = "Fecha inválida."

    if data.get("igi_rate"):
        try:
            rate = Decimal(data["igi_rate"])
            if rate < 0:
                errors["igi_rate"] = "No puede ser negativo."
        except Exception:
            errors["igi_rate"] = "Formato numérico inválido."

    return errors


@app.post("/invoices/new", response_class=HTMLResponse)
async def create_invoice(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    form = await request.form()
    data = {
        "client_id": form.get("client_id", "").strip(),
        "issue_date": form.get("issue_date", "").strip(),
        "currency": form.get("currency", "EUR").strip() or "EUR",
        "igi_rate": form.get("igi_rate", "").strip(),
        "notes": form.get("notes", "").strip(),
    }
    clients = db.query(Client).order_by(Client.name).all()
    errors = _validate_invoice_form(data, db)
    if errors:
        return templates.TemplateResponse(
            "invoices/new.html",
            {
                "request": request,
                "clients": clients,
                "form_action": "/invoices/new",
                "data": data,
                "errors": errors,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    client = _get_client(db, int(data["client_id"]))
    company = _get_company(db)
    issue_date = _parse_date(data["issue_date"]) if data["issue_date"] else date.today()
    terms_days = _effective_payment_terms_days(client, company) or 0
    due_date = issue_date + timedelta(days=terms_days)
    igi_rate = Decimal(data["igi_rate"] or "0")

    invoice = Invoice(
        status="draft",
        series=None,
        number=None,
        issue_date=issue_date,
        due_date=due_date,
        client_id=client.id,
        currency=data["currency"] or "EUR",
        igi_rate=igi_rate,
        notes=data["notes"],
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return RedirectResponse(
        url=f"/invoices/{invoice.id}", status_code=status.HTTP_303_SEE_OTHER
    )


@app.get("/invoices/{invoice_id}", response_class=HTMLResponse)
async def invoice_detail(
    invoice_id: int, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    invoice = (
        db.query(Invoice)
        .options(joinedload(Invoice.client), selectinload(Invoice.lines))
        .filter(Invoice.id == invoice_id)
        .first()
    )
    if not invoice:
        return HTMLResponse(content="Factura no encontrada", status_code=404)

    lines = sorted(invoice.lines, key=lambda l: (l.sort_order, l.id))
    line_amounts = [
        {"line": line, "subtotal": ls, "discount": ld, "total": lt}
        for line, ls, ld, lt in compute_line_amounts(lines)
    ]
    totals = compute_totals(invoice, lines)
    return templates.TemplateResponse(
        "invoices/detail.html",
        {
            "request": request,
            "invoice": invoice,
            "client": invoice.client,
            "lines": lines,
            "line_amounts": line_amounts,
            "totals": totals,
            "errors": {},
            "form_action": f"/invoices/{invoice.id}/lines",
        },
    )
