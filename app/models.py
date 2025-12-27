from sqlalchemy import Column, Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import relationship

from .database import Base


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    tax_id = Column(String(50), nullable=True)
    address = Column(String(255), nullable=True)  # legacy single-line
    address_line1 = Column(String(255), nullable=True)
    address_line2 = Column(String(255), nullable=True)
    city = Column(String(255), nullable=True)
    postal_code = Column(String(20), nullable=True)
    country = Column(String(100), nullable=True)
    phone = Column(String(100), nullable=True)
    email = Column(String(255), nullable=True)
    payment_terms_days = Column(Integer, nullable=True)


class Company(Base):
    __tablename__ = "company"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, default="")
    tax_id = Column(String(50), nullable=True)
    phone = Column(String(100), nullable=True)
    address_line1 = Column(String(255), nullable=True)
    address_line2 = Column(String(255), nullable=True)
    city = Column(String(255), nullable=True)
    postal_code = Column(String(20), nullable=True)
    country = Column(String(100), nullable=True)
    email = Column(String(255), nullable=True)
    bank_account = Column(String(255), nullable=True)
    bank_swift = Column(String(255), nullable=True)
    payment_terms_days = Column(Integer, nullable=True)
    notes = Column(String(500), nullable=True)


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String(20), nullable=False, default="draft")
    series = Column(String(20), nullable=True)
    number = Column(Integer, nullable=True)
    invoice_number = Column(String(20), nullable=True, unique=True)
    issue_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    currency = Column(String(10), nullable=False, default="EUR")
    igi_rate = Column(Numeric(5, 2), nullable=False, default=0)
    notes = Column(String(500), nullable=True)

    client = relationship("Client")
    lines = relationship(
        "InvoiceLine",
        cascade="all, delete-orphan",
        back_populates="invoice",
        order_by="InvoiceLine.sort_order",
    )


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    description = Column(String(500), nullable=False)
    qty = Column(Numeric(12, 2), nullable=False, default=1)
    unit_price = Column(Numeric(12, 2), nullable=False, default=0)
    discount_pct = Column(Numeric(5, 2), nullable=False, default=0)
    sort_order = Column(Integer, nullable=False, default=1)

    invoice = relationship("Invoice", back_populates="lines")


class InvoiceSequence(Base):
    __tablename__ = "invoice_sequences"
    __table_args__ = (UniqueConstraint("year_full"),)

    id = Column(Integer, primary_key=True, index=True)
    year_full = Column(Integer, nullable=False)
    next_number = Column(Integer, nullable=False, default=1)
