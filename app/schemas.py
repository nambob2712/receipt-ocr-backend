from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ───────────────────────── Auth ─────────────────────────

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ───────────────────────── Receipt Items ────────────────

class LineItem(BaseModel):
    description: str
    quantity: Optional[float] = 1
    unit_price: Optional[float] = 0
    total_price: Optional[float] = 0


# ───────────────────────── OCR Result ───────────────────

class OCRResult(BaseModel):
    merchant_name: Optional[str] = None
    merchant_address: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    currency: Optional[str] = "JPY"
    line_items: Optional[List[LineItem]] = []
    subtotal: Optional[float] = None
    tax_amount: Optional[float] = None
    tax_rate: Optional[str] = None
    total_amount: Optional[float] = 0
    payment_method: Optional[str] = None
    category: Optional[str] = "Other"
    confidence: Optional[float] = 0
    processing_time_ms: Optional[float] = None
    image_url: Optional[str] = None


# ───────────────────────── Receipt CRUD ─────────────────

class ReceiptCreate(BaseModel):
    merchant_name: str
    merchant_address: Optional[str] = None
    date: Optional[date] = None
    time: Optional[str] = None
    total_amount: Decimal
    subtotal: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    tax_rate: Optional[str] = None
    currency: str = "JPY"
    category: str = "Other"
    payment_method: Optional[str] = None
    items: Optional[List[dict]] = None
    image_url: Optional[str] = None
    confidence: Optional[Decimal] = None


class ReceiptResponse(BaseModel):
    id: UUID
    user_id: UUID
    merchant_name: str
    merchant_address: Optional[str] = None
    date: Optional[date] = None
    time: Optional[str] = None
    total_amount: Decimal
    subtotal: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    tax_rate: Optional[str] = None
    currency: str
    category: str
    payment_method: Optional[str] = None
    items: Optional[Any] = None
    image_url: Optional[str] = None
    confidence: Optional[Decimal] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ReceiptListResponse(BaseModel):
    receipts: List[ReceiptResponse]
    total: int
    page: int
    per_page: int
    pages: int


class DuplicateWarning(BaseModel):
    warning: str
    existing_receipt_id: UUID
    receipt: ReceiptResponse


# ───────────────────────── Analytics ────────────────────

class SummaryResponse(BaseModel):
    total_receipts: int
    total_spent: float
    average_per_receipt: float
    top_category: Optional[str] = None
    top_merchant: Optional[str] = None


class CategorySummary(BaseModel):
    category: str
    total: float
    count: int
    percentage: float


class DateSummary(BaseModel):
    date: str
    total: float
    count: int
