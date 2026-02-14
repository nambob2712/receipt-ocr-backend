import uuid
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import (
    Column, String, DateTime, Date, Numeric, JSON, ForeignKey, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    receipts = relationship("Receipt", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.email}>"


class Receipt(Base):
    __tablename__ = "receipts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    merchant_name = Column(String(255), nullable=False)
    merchant_address = Column(Text, nullable=True)
    date = Column(Date, nullable=True)
    time = Column(String(10), nullable=True)

    total_amount = Column(Numeric(12, 2), nullable=False)
    subtotal = Column(Numeric(12, 2), nullable=True)
    tax_amount = Column(Numeric(12, 2), nullable=True)
    tax_rate = Column(String(20), nullable=True)
    currency = Column(String(10), default="JPY", nullable=False)

    category = Column(String(50), nullable=False)
    payment_method = Column(String(50), nullable=True)

    items = Column(JSON, nullable=True)
    image_url = Column(Text, nullable=True)
    confidence = Column(Numeric(5, 4), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="receipts")

    def __repr__(self):
        return f"<Receipt {self.merchant_name} {self.total_amount}>"
