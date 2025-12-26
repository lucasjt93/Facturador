from typing import Dict, Optional

from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .database import get_db
from .models import Client, Company

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
                "payment_terms_days": client.payment_terms_days or "",
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
        "payment_terms_days": company.payment_terms_days if company else "",
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
