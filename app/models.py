from sqlalchemy import Column, Integer, String

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
