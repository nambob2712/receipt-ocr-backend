import logging
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query, Header, Body, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db, create_tables
from app.models import User, Receipt
from app.schemas import (
    UserRegister, UserLogin, UserResponse, TokenResponse,
    ReceiptCreate, ReceiptResponse, ReceiptListResponse,
    OCRResult, DuplicateWarning,
    SummaryResponse, CategorySummary, DateSummary,
)
from app.auth import (
    hash_password, verify_password, create_access_token, get_current_user,
)
from app.services.ocr import OCRService
from app.services.storage import upload_image
import google.generativeai as genai

logger = logging.getLogger(__name__)
settings = get_settings()


# ─────────────────── Lifespan ───────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — attempting to create DB tables...")
    await create_tables()          # non-fatal: already wrapped in try/except
    logger.info("Startup complete.")
    yield


app = FastAPI(
    title="Receipt OCR API",
    description="FastAPI backend for Receipt OCR mobile app",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




# ══════════════════════════════════════════════════════════
#  AUTH ENDPOINTS
# ══════════════════════════════════════════════════════════

@app.post("/api/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    # Check existing
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@app.post("/api/auth/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user.id)
    return TokenResponse(access_token=token)


@app.get("/api/auth/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


# ══════════════════════════════════════════════════════════
#  RECEIPT ENDPOINTS
# ══════════════════════════════════════════════════════════

@app.post("/api/receipts/scan", response_model=OCRResult)
async def scan_receipt(
    file: UploadFile = File(...),
    api_key: str = Header(..., alias="X-Gemini-API-Key"),
    current_user: User = Depends(get_current_user),
):
    """Upload a receipt image, run OCR with user-provided API key."""
    if not api_key or not api_key.startswith("AIza"):
        raise HTTPException(status_code=400, detail="Invalid Gemini API key")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")

    # OCR with user-provided key
    try:
        ocr_service = OCRService(api_key=api_key)
        result = ocr_service.process_image(contents)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"OCR processing failed: {str(e)}")

    # Upload image to Cloudinary (best-effort)
    try:
        upload_result = upload_image(contents)
        result["image_url"] = upload_result["url"]
    except Exception:
        result["image_url"] = None

    return result


@app.post("/api/receipts", response_model=ReceiptResponse, status_code=status.HTTP_201_CREATED)
async def create_receipt(
    data: ReceiptCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save a receipt. Returns 409 with warning if a duplicate is detected."""
    # ── Duplicate detection ──
    if data.date:
        dup_query = select(Receipt).where(
            and_(
                Receipt.user_id == current_user.id,
                Receipt.date == data.date,
                func.lower(Receipt.merchant_name) == data.merchant_name.lower(),
                func.abs(Receipt.total_amount - data.total_amount) <= Decimal("0.5"),
            )
        )
        dup_result = await db.execute(dup_query)
        existing = dup_result.scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=409,
                detail={
                    "warning": "Possible duplicate receipt detected",
                    "existing_receipt_id": str(existing.id),
                },
            )

    receipt = Receipt(
        user_id=current_user.id,
        merchant_name=data.merchant_name,
        merchant_address=data.merchant_address,
        date=data.date,
        time=data.time,
        total_amount=data.total_amount,
        subtotal=data.subtotal,
        tax_amount=data.tax_amount,
        tax_rate=data.tax_rate,
        currency=data.currency,
        category=data.category,
        payment_method=data.payment_method,
        items=data.items,
        image_url=data.image_url,
        confidence=data.confidence,
    )
    db.add(receipt)
    await db.flush()
    await db.refresh(receipt)
    return receipt


@app.get("/api/receipts", response_model=ReceiptListResponse)
async def list_receipts(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List user receipts with pagination and optional filters."""
    query = select(Receipt).where(Receipt.user_id == current_user.id)

    if category:
        query = query.where(Receipt.category == category)
    if start_date:
        query = query.where(Receipt.date >= start_date)
    if end_date:
        query = query.where(Receipt.date <= end_date)

    # Total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginated results
    query = query.order_by(Receipt.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    receipts = result.scalars().all()

    pages = (total + per_page - 1) // per_page  # ceil division

    return ReceiptListResponse(
        receipts=receipts,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@app.get("/api/receipts/{receipt_id}", response_model=ReceiptResponse)
async def get_receipt(
    receipt_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Receipt).where(
            and_(Receipt.id == receipt_id, Receipt.user_id == current_user.id)
        )
    )
    receipt = result.scalar_one_or_none()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return receipt


@app.delete("/api/receipts/{receipt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_receipt(
    receipt_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Receipt).where(
            and_(Receipt.id == receipt_id, Receipt.user_id == current_user.id)
        )
    )
    receipt = result.scalar_one_or_none()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    await db.delete(receipt)
    return None


# ══════════════════════════════════════════════════════════
#  ANALYTICS ENDPOINTS
# ══════════════════════════════════════════════════════════

@app.get("/api/analytics/summary", response_model=SummaryResponse)
async def analytics_summary(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base = select(Receipt).where(Receipt.user_id == current_user.id)
    if start_date:
        base = base.where(Receipt.date >= start_date)
    if end_date:
        base = base.where(Receipt.date <= end_date)

    sub = base.subquery()

    # Aggregates
    agg = await db.execute(
        select(
            func.count(sub.c.id).label("cnt"),
            func.coalesce(func.sum(sub.c.total_amount), 0).label("total"),
        )
    )
    row = agg.one()
    total_receipts = row.cnt
    total_spent = float(row.total)
    avg = total_spent / total_receipts if total_receipts > 0 else 0

    # Top category
    cat_q = (
        select(sub.c.category, func.sum(sub.c.total_amount).label("cat_total"))
        .group_by(sub.c.category)
        .order_by(func.sum(sub.c.total_amount).desc())
        .limit(1)
    )
    cat_row = (await db.execute(cat_q)).first()
    top_category = cat_row.category if cat_row else None

    # Top merchant
    mer_q = (
        select(sub.c.merchant_name, func.count(sub.c.id).label("mer_cnt"))
        .group_by(sub.c.merchant_name)
        .order_by(func.count(sub.c.id).desc())
        .limit(1)
    )
    mer_row = (await db.execute(mer_q)).first()
    top_merchant = mer_row.merchant_name if mer_row else None

    return SummaryResponse(
        total_receipts=total_receipts,
        total_spent=total_spent,
        average_per_receipt=round(avg, 2),
        top_category=top_category,
        top_merchant=top_merchant,
    )


@app.get("/api/analytics/by-category", response_model=list[CategorySummary])
async def analytics_by_category(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Receipt).where(Receipt.user_id == current_user.id)
    if start_date:
        query = query.where(Receipt.date >= start_date)
    if end_date:
        query = query.where(Receipt.date <= end_date)

    sub = query.subquery()

    result = await db.execute(
        select(
            sub.c.category,
            func.sum(sub.c.total_amount).label("total"),
            func.count(sub.c.id).label("cnt"),
        )
        .group_by(sub.c.category)
        .order_by(func.sum(sub.c.total_amount).desc())
    )
    rows = result.all()

    grand_total = sum(float(r.total) for r in rows) or 1
    return [
        CategorySummary(
            category=r.category,
            total=float(r.total),
            count=r.cnt,
            percentage=round(float(r.total) / grand_total * 100, 1),
        )
        for r in rows
    ]


@app.get("/api/analytics/by-date", response_model=list[DateSummary])
async def analytics_by_date(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    group_by: str = Query("day", regex="^(day|week|month)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Receipt).where(
        and_(Receipt.user_id == current_user.id, Receipt.date.isnot(None))
    )
    if start_date:
        query = query.where(Receipt.date >= start_date)
    if end_date:
        query = query.where(Receipt.date <= end_date)

    sub = query.subquery()

    if group_by == "day":
        date_col = func.to_char(sub.c.date, "YYYY-MM-DD").label("period")
    elif group_by == "week":
        date_col = func.to_char(sub.c.date, "IYYY-IW").label("period")
    else:  # month
        date_col = func.to_char(sub.c.date, "YYYY-MM").label("period")

    result = await db.execute(
        select(
            date_col,
            func.sum(sub.c.total_amount).label("total"),
            func.count(sub.c.id).label("cnt"),
        )
        .group_by(date_col)
        .order_by(date_col)
    )
    rows = result.all()

    return [
        DateSummary(date=r.period, total=float(r.total), count=r.cnt)
        for r in rows
    ]


# ══════════════════════════════════════════════════════════
#  SETTINGS ENDPOINTS
# ══════════════════════════════════════════════════════════

@app.post("/api/settings/verify-api-key")
async def verify_api_key(api_key: str = Body(..., embed=True)):
    """Test if a Gemini API key is valid by making a simple request."""
    if not api_key or not api_key.startswith("AIza"):
        return {"valid": False, "message": "API key must start with 'AIza'"}

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        model.generate_content("Say OK")
        return {"valid": True, "message": "API key is valid"}
    except Exception as e:
        return {"valid": False, "message": str(e)}


# ─────────────────── Health check ───────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}
