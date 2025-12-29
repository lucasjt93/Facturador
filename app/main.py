from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, Optional

from fastapi import Depends, FastAPI, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from .database import get_db
from .models import Client, Company, Invoice, InvoiceLine, InvoiceSequence
from .pdf import build_invoice_pdf_payload, render_invoice_pdf
from .services import compute_line_amounts, compute_totals

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

def render_error(request: Request, message: str, status_code: int = 400) -> HTMLResponse:
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "message": message},
        status_code=status_code,
        media_type="text/html; charset=utf-8",
    )


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/clients", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get("/clients", response_class=HTMLResponse)
def list_clients(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    clients = (
        db.query(Client).filter(Client.is_deleted.is_(False)).order_by(desc(Client.id)).all()
    )
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
        "show_deleted": False,
    },
    )


@app.get("/clients/new", response_class=HTMLResponse)
def new_client(request: Request) -> HTMLResponse:
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


@app.post("/clients")
def create_client(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(""),
    tax_id: str = Form(""),
    address_line1: str = Form(""),
    address_line2: str = Form(""),
    city: str = Form(""),
    postal_code: str = Form(""),
    country: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    payment_terms_days: str = Form(""),
) -> HTMLResponse:
    data = {
        "name": name.strip(),
        "tax_id": tax_id.strip(),
        "address_line1": address_line1.strip(),
        "address_line2": address_line2.strip(),
        "city": city.strip(),
        "postal_code": postal_code.strip(),
        "country": country.strip(),
        "phone": phone.strip(),
        "email": email.strip(),
        "payment_terms_days": payment_terms_days.strip(),
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


def render_error(request: Request, message: str, status_code: int = 400) -> HTMLResponse:
    return templates.TemplateResponse(
        "error.html", {"request": request, "message": message}, status_code=status_code
    )


@app.get("/clients/{client_id}/edit", response_class=HTMLResponse)
def edit_client(
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


@app.post("/clients/{client_id}/edit")
def update_client(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(""),
    tax_id: str = Form(""),
    address_line1: str = Form(""),
    address_line2: str = Form(""),
    city: str = Form(""),
    postal_code: str = Form(""),
    country: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    payment_terms_days: str = Form(""),
) -> HTMLResponse:
    client = _get_client(db, client_id)
    if not client:
        return HTMLResponse(content="Cliente no encontrado", status_code=404)

    data = {
        "name": name.strip(),
        "tax_id": tax_id.strip(),
        "address_line1": address_line1.strip(),
        "address_line2": address_line2.strip(),
        "city": city.strip(),
        "postal_code": postal_code.strip(),
        "country": country.strip(),
        "phone": phone.strip(),
        "email": email.strip(),
        "payment_terms_days": payment_terms_days.strip(),
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
def company_settings(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
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


@app.post("/company")
def update_company(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(""),
    tax_id: str = Form(""),
    phone: str = Form(""),
    address_line1: str = Form(""),
    address_line2: str = Form(""),
    city: str = Form(""),
    postal_code: str = Form(""),
    country: str = Form(""),
    email: str = Form(""),
    bank_account: str = Form(""),
    bank_swift: str = Form(""),
    payment_terms_days: str = Form(""),
    notes: str = Form(""),
) -> HTMLResponse:
    data = {
        "name": name.strip(),
        "tax_id": tax_id.strip(),
        "phone": phone.strip(),
        "address_line1": address_line1.strip(),
        "address_line2": address_line2.strip(),
        "city": city.strip(),
        "postal_code": postal_code.strip(),
        "country": country.strip(),
        "email": email.strip(),
        "bank_account": bank_account.strip(),
        "bank_swift": bank_swift.strip(),
        "payment_terms_days": payment_terms_days.strip(),
        "notes": notes.strip(),
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

    return errors


@app.post("/invoices/{invoice_id}/lines")
def add_line(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    description: str = Form(""),
    qty: str = Form(""),
    unit_price: str = Form(""),
    discount_pct: str = Form(""),
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

    data = {
        "description": description.strip(),
        "qty": qty.strip() or "1",
        "unit_price": unit_price.strip() or "0",
        "discount_pct": discount_pct.strip() or "0",
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

    next_sort_order = 1
    if invoice.lines:
        next_sort_order = max(line.sort_order for line in invoice.lines) + 1

    line = InvoiceLine(
        invoice_id=invoice.id,
        description=data["description"],
        qty=Decimal(data["qty"]),
        unit_price=Decimal(data["unit_price"]),
        discount_pct=Decimal(data["discount_pct"]),
        sort_order=next_sort_order,
    )
    db.add(line)
    db.commit()
    return RedirectResponse(
        url=f"/invoices/{invoice.id}", status_code=status.HTTP_303_SEE_OTHER
    )


@app.post("/invoices/{invoice_id}/lines/{line_id}/delete")
def delete_line(
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


@app.post("/invoices/{invoice_id}/issue")
def issue_invoice(
    invoice_id: int, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    invoice = (
        db.query(Invoice)
        .options(selectinload(Invoice.lines), joinedload(Invoice.client))
        .filter(Invoice.id == invoice_id)
        .first()
    )
    if not invoice:
        return render_error(request, "Factura no encontrada", status_code=404)
    if invoice.status != "draft":
        return RedirectResponse(
            url=f"/invoices/{invoice.id}", status_code=status.HTTP_303_SEE_OTHER
        )
    if not invoice.lines:
        return render_error(
            request,
            "No se puede emitir una factura sin líneas.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    year_full = invoice.issue_date.year if invoice.issue_date else date.today().year
    terms_applied = _effective_payment_terms_days(
        invoice.client, _get_company(db)
    ) or 0
    totals = compute_totals(invoice, invoice.lines)

    def assign_number_and_snapshot():
        seq = (
            db.query(InvoiceSequence)
            .filter(InvoiceSequence.year_full == year_full)
            .with_for_update()
            .first()
        )
        if not seq:
            seq = InvoiceSequence(year_full=year_full, next_number=1)
            db.add(seq)
            db.flush()
        n = seq.next_number
        seq.next_number = n + 1
        code = f"TC{year_full % 100:02d}{n:02d}"
        invoice.number = n
        invoice.invoice_number = code
        invoice.status = "issued"
        invoice.client_name_snapshot = invoice.client.name
        invoice.client_tax_id_snapshot = invoice.client.tax_id
        invoice.subtotal_snapshot = totals["subtotal"]
        invoice.igi_amount_snapshot = totals["igi"]
        invoice.total_snapshot = totals["total"]
        invoice.payment_terms_days_applied = terms_applied
        invoice.igi_rate_snapshot = invoice.igi_rate

    for attempt in range(2):
        try:
            assign_number_and_snapshot()
            db.commit()
            break
        except IntegrityError:
            db.rollback()
            if attempt == 1:
                raise
    return RedirectResponse(
        url=f"/invoices/{invoice.id}", status_code=status.HTTP_303_SEE_OTHER
    )


@app.get("/invoices", response_class=HTMLResponse)
def list_invoices(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
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
def new_invoice(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    clients = db.query(Client).filter(Client.is_deleted.is_(False)).order_by(Client.name).all()
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


@app.post("/invoices/new")
def create_invoice(
    request: Request,
    db: Session = Depends(get_db),
    client_id: str = Form(""),
    issue_date: str = Form(""),
    currency: str = Form("EUR"),
    igi_rate: str = Form(""),
    notes: str = Form(""),
) -> HTMLResponse:
    data = {
        "client_id": client_id.strip(),
        "issue_date": issue_date.strip(),
        "currency": currency.strip() or "EUR",
        "igi_rate": igi_rate.strip(),
        "notes": notes.strip(),
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
def invoice_detail(
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


@app.get("/invoices/{invoice_id}/pdf")
def invoice_pdf(invoice_id: int, request: Request, db: Session = Depends(get_db)) -> Response:
    invoice = (
        db.query(Invoice)
        .options(joinedload(Invoice.client), selectinload(Invoice.lines))
        .filter(Invoice.id == invoice_id)
        .first()
    )
    if not invoice:
        return render_error(request, "Factura no encontrada", status_code=404)
    if invoice.status not in ("issued", "paid"):
        return render_error(
            request,
            "Solo se puede generar PDF para facturas emitidas.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    lines = sorted(invoice.lines, key=lambda l: (l.sort_order, l.id))
    payload = build_invoice_pdf_payload(invoice, lines)
    pdf_bytes = render_invoice_pdf(payload)
    filename = f"invoice_{invoice.invoice_number or invoice.id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename=\"{filename}\"'},
    )


@app.post("/clients/{client_id}/delete")
def delete_client(
    client_id: int, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    client = _get_client(db, client_id)
    if not client:
        return HTMLResponse(content="Cliente no encontrado", status_code=404)
    client.is_deleted = True
    db.commit()
    return RedirectResponse(url="/clients", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/invoices/{invoice_id}/delete")
def delete_invoice(invoice_id: int, db: Session = Depends(get_db)) -> HTMLResponse:
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        return HTMLResponse(content="Factura no encontrada", status_code=404)
    db.delete(invoice)
    db.commit()
    return RedirectResponse(url="/invoices", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/clients/deleted", response_class=HTMLResponse)
def list_deleted_clients(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    clients = (
        db.query(Client).filter(Client.is_deleted.is_(True)).order_by(desc(Client.id)).all()
    )
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
            "show_deleted": True,
        },
    )


@app.post("/clients/{client_id}/restore")
def restore_client(
    client_id: int, db: Session = Depends(get_db)
) -> HTMLResponse:
    client = _get_client(db, client_id)
    if not client:
        return HTMLResponse(content="Cliente no encontrado", status_code=404)
    client.is_deleted = False
    db.commit()
    return RedirectResponse(url="/clients", status_code=status.HTTP_303_SEE_OTHER)


