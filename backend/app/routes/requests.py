# backend/app/routes/requests.py
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_role, require_client_assignment
from app.models.audit import AuditEventType
from app.models.extraction_job import ExtractionJob, ExtractionJobStatus
from app.models.invoice_fields import LineItem
from app.models.request import InvoiceRequest, RequestStatus
from app.models.tax_assignment import IndonesianTaxType, TAX_RATES, TaxAssignment
from app.models.user import User, UserRole
from app.repositories.request_repository import request_repository
from app.repositories.user_repository import user_repository
from app.schemas.request_schemas import CreateRequestResponse
from app.services.audit_service import log_event
from app.services.request_service import RequestIdGenerationError, generate_request_id
from app.services.tax_service import compute_tax_amount, compute_tax_summary
from app.storage import StorageError, file_store

router = APIRouter(prefix="/requests", tags=["requests"])

MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024   # 20 MB per file
MAX_FILES_PER_SESSION = 20
ACCEPTED_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/jpg"}


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CreateRequestResponse)
async def upload_invoice(
    files: List[UploadFile],
    client_id: uuid.UUID = Form(...),
    request_type: str = Form(..., min_length=1, max_length=100),
    channel: str = Form(..., min_length=1, max_length=100),
    request_date: date = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("CLIENT_PIC", "INTAKE_SUPPORT")),
):
    """
    Upload one or more evidence files (PDF/PNG/JPG/JPEG).
    Creates the Request in QUEUED status and inserts an ExtractionJob row
    with status=PENDING. The background worker picks up the job and
    transitions the Request to PROCESSING.
    """
    # ── Validate file count ────────────────────────────────────────────────────
    if not files:
        raise HTTPException(422, "At least one file is required.")
    if len(files) > MAX_FILES_PER_SESSION:
        raise HTTPException(422, f"Maximum {MAX_FILES_PER_SESSION} files per session.")

    # ── INTAKE_SUPPORT assignment check ───────────────────────────────────────
    if current_user.role == UserRole.INTAKE_SUPPORT:
        active = await user_repository.is_assignment_active(db, current_user.user_id, client_id)
        if not active:
            raise HTTPException(403, "You are not authorized to submit for the selected client.")

    # ── Read and validate all files ───────────────────────────────────────────
    validated: list[tuple[str, bytes, str]] = []   # (filename, bytes, content_type)
    for f in files:
        ct = (f.content_type or "").lower()
        name = f.filename or "unknown"
        if ct not in ACCEPTED_TYPES:
            raise HTTPException(
                415,
                f"'{name}': unsupported format '{ct}'. Accepted: PDF, PNG, JPG, JPEG.",
            )
        data = await f.read()
        if len(data) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(413, f"'{name}' exceeds the 20 MB limit.")
        validated.append((name, data, ct))

    # ── Generate request ID ────────────────────────────────────────────────────
    try:
        request_id = await generate_request_id(db)
    except RequestIdGenerationError as exc:
        raise HTTPException(500, str(exc))

    # ── Upload all files to S3 ─────────────────────────────────────────────────
    evidence_keys: list[str] = []
    evidence_meta: list[dict] = []
    for order, (name, data, ct) in enumerate(validated, start=1):
        key = f"evidence/{request_id}/{order}_{name}"
        try:
            await file_store.upload(key, data, ct)
        except StorageError as exc:
            raise HTTPException(502, f"S3 upload failed for '{name}': {exc}")
        evidence_keys.append(key)
        evidence_meta.append(
            {"filename": name, "content_type": ct, "file_key": key, "upload_order": order}
        )

    # ── Create Request in QUEUED status ───────────────────────────────────────
    req = await request_repository.create_request(
        db,
        request_id=request_id,
        client_id=client_id,
        uploader_id=current_user.user_id,
        request_type=request_type,
        channel=channel,
        request_date=request_date,
        invoice_file_key=evidence_keys[0],
        invoice_page_count=None,
    )

    await log_event(
        db,
        AuditEventType.REQUEST_CREATED,
        payload={
            "request_id": str(request_id),
            "client_id": str(client_id),
            "uploader_id": str(current_user.user_id),
            "upload_timestamp": datetime.now(timezone.utc).isoformat(),
            "evidence_files": evidence_meta,
        },
        request_id=request_id,
        actor_id=current_user.user_id,
    )

    # ── Insert ExtractionJob row with status=PENDING ──────────────────────────
    # The background worker picks this up and transitions the Request to PROCESSING.
    now = datetime.now(timezone.utc)
    extraction_job = ExtractionJob(
        job_id=uuid.uuid4(),
        request_id=request_id,
        status=ExtractionJobStatus.PENDING,
        retry_count=0,
        created_at=now,
    )
    db.add(extraction_job)
    await db.flush()

    # ── Commit everything: Request + AuditEvent + ExtractionJob ──────────────
    await db.commit()

    # Reload request to return (still in QUEUED status)
    req = await request_repository.get_by_id(db, request_id)
    return req


@router.post("/{request_id}/dismiss-duplicate", status_code=status.HTTP_200_OK)
async def dismiss_duplicate(
    request_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("FINANCE_REVIEWER")),
    _: None = Depends(require_client_assignment(request_id)),
):
    """
    Remove the POSSIBLE_DUPLICATE flag from a request.
    Only Finance Reviewer role can dismiss duplicates.
    Requires active client assignment for the request's client.
    """
    # Fetch the request
    req = await request_repository.get_by_id(db, request_id)
    if req is None:
        raise HTTPException(404, "Request not found.")

    # Remove the POSSIBLE_DUPLICATE flag
    await request_repository.remove_flag(db, request_id, "POSSIBLE_DUPLICATE")

    # Log the FLAG_DISMISSED event
    await log_event(
        db,
        AuditEventType.FLAG_DISMISSED,
        payload={
            "request_id": str(request_id),
            "flag": "POSSIBLE_DUPLICATE",
        },
        request_id=request_id,
        actor_id=current_user.user_id,
    )

    await db.commit()
    return {"status": "success"}


# ── Tax Assignment Schemas ────────────────────────────────────────────────────


class TaxAssignmentRequest(BaseModel):
    tax_type: str = Field(..., description="Tax type (PPH21, PPH22, PPH23, PPH25, PPN, NO_TAX)")


class TaxAssignmentResponse(BaseModel):
    line_item_id: uuid.UUID
    tax_type: str
    tax_rate: Decimal
    tax_amount: Decimal


class TaxSummaryLineItem(BaseModel):
    line_item_id: uuid.UUID
    description: str | None
    quantity: Decimal | None
    unit: str | None
    unit_price: Decimal | None
    line_total: Decimal | None
    tax_type: str | None
    tax_rate: Decimal | None
    tax_amount: Decimal | None


class TaxSummaryResponse(BaseModel):
    line_items: list[TaxSummaryLineItem]
    per_type_subtotals: dict[str, Decimal]
    total_tax: Decimal
    grand_total: Decimal
    locked: bool = False


# ── Tax Assignment Endpoints ──────────────────────────────────────────────────


@router.put("/{request_id}/line-items/{line_item_id}/tax", status_code=status.HTTP_200_OK, response_model=TaxAssignmentResponse)
async def assign_tax(
    request_id: uuid.UUID,
    line_item_id: uuid.UUID,
    tax_request: TaxAssignmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("FINANCE_REVIEWER")),
    _: None = Depends(require_client_assignment(request_id)),
):
    """
    Assign a tax type to a line item and compute the tax amount.
    Request must be in READY_FOR_REVIEW or EXCEPTION status.
    Rejects with 409 if Request is AMIGA_REVIEWED or later (locked).
    """
    # Fetch the request
    req = await request_repository.get_by_id(db, request_id)
    if req is None:
        raise HTTPException(404, "Request not found.")

    # Check request status - must be READY_FOR_REVIEW or EXCEPTION
    if req.status in (RequestStatus.AMIGA_REVIEWED, RequestStatus.SENT_TO_CLIENT, RequestStatus.REJECTED):
        raise HTTPException(409, "This request is locked and cannot be modified.")

    if req.status not in (RequestStatus.READY_FOR_REVIEW, RequestStatus.EXCEPTION):
        raise HTTPException(400, f"Request must be in READY_FOR_REVIEW or EXCEPTION status, not {req.status.value}.")

    # Validate tax_type
    try:
        tax_type_enum = IndonesianTaxType(tax_request.tax_type)
    except ValueError:
        valid_types = ", ".join([t.value for t in IndonesianTaxType])
        raise HTTPException(422, f"Invalid tax_type. Valid values: {valid_types}")

    # Fetch the line item
    stmt = select(LineItem).where(LineItem.line_item_id == line_item_id)
    result = await db.execute(stmt)
    line_item = result.scalar_one_or_none()

    if line_item is None:
        raise HTTPException(404, "Line item not found.")

    # Verify line item belongs to this request's draft
    from app.models.draft import Draft
    stmt_draft = select(Draft).where(Draft.request_id == request_id)
    result_draft = await db.execute(stmt_draft)
    draft = result_draft.scalar_one_or_none()

    if draft is None or line_item.draft_id != draft.draft_id:
        raise HTTPException(400, "Line item does not belong to this request.")

    # Compute tax amount using Decimal arithmetic
    line_total_decimal = Decimal(str(line_item.line_total)) if line_item.line_total else Decimal("0.00")
    tax_amount = compute_tax_amount(line_total_decimal, tax_type_enum)

    # Get the tax rate
    tax_rate = TAX_RATES[tax_type_enum]

    # Get or create tax assignment
    stmt_assignment = select(TaxAssignment).where(TaxAssignment.line_item_id == line_item_id)
    result_assignment = await db.execute(stmt_assignment)
    existing_assignment = result_assignment.scalar_one_or_none()

    if existing_assignment:
        # Record old values for audit
        old_tax_type = existing_assignment.tax_type.value
        old_tax_amount = existing_assignment.tax_amount
        
        # Update existing assignment
        existing_assignment.tax_type = tax_type_enum
        existing_assignment.tax_rate = tax_rate
        existing_assignment.tax_amount = tax_amount
        existing_assignment.assigned_at = datetime.now(timezone.utc)
        existing_assignment.assigned_by = current_user.user_id
        await db.flush()
        
        assignment = existing_assignment
    else:
        # Create new assignment
        old_tax_type = None
        old_tax_amount = None
        
        assignment = TaxAssignment(
            tax_assignment_id=uuid.uuid4(),
            line_item_id=line_item_id,
            tax_type=tax_type_enum,
            tax_rate=tax_rate,
            tax_amount=tax_amount,
            assigned_at=datetime.now(timezone.utc),
            assigned_by=current_user.user_id,
        )
        db.add(assignment)
        await db.flush()

    # Log audit event - FIELD_REVISED
    await log_event(
        db,
        AuditEventType.FIELD_REVISED,
        payload={
            "request_id": str(request_id),
            "line_item_id": str(line_item_id),
            "field_path": f"line_items[{line_item.sequence_number - 1}].tax_type",
            "old_value": old_tax_type,
            "new_value": tax_type_enum.value,
            "computed_tax_amount": str(tax_amount),
        },
        request_id=request_id,
        actor_id=current_user.user_id,
    )

    await db.commit()

    return TaxAssignmentResponse(
        line_item_id=line_item_id,
        tax_type=tax_type_enum.value,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
    )


@router.get("/{request_id}/tax-summary", status_code=status.HTTP_200_OK, response_model=TaxSummaryResponse)
async def get_tax_summary(
    request_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("FINANCE_REVIEWER")),
    _: None = Depends(require_client_assignment(request_id)),
):
    """
    Get tax summary for a request including per-type subtotals and grand total.
    If Request is AMIGA_REVIEWED or later, returns locked: true.
    """
    # Fetch the request
    req = await request_repository.get_by_id(db, request_id)
    if req is None:
        raise HTTPException(404, "Request not found.")

    # Check if request is locked
    is_locked = req.status in (RequestStatus.AMIGA_REVIEWED, RequestStatus.SENT_TO_CLIENT)

    # Fetch the draft
    from app.models.draft import Draft
    stmt_draft = select(Draft).where(Draft.request_id == request_id)
    result_draft = await db.execute(stmt_draft)
    draft = result_draft.scalar_one_or_none()

    if draft is None:
        raise HTTPException(404, "Draft not found for this request.")

    # Fetch all line items for this draft
    stmt_lines = select(LineItem).where(LineItem.draft_id == draft.draft_id).order_by(LineItem.sequence_number)
    result_lines = await db.execute(stmt_lines)
    line_items = list(result_lines.scalars().all())

    # Fetch all tax assignments for the line items
    line_item_ids = [li.line_item_id for li in line_items]
    if line_item_ids:
        stmt_assignments = select(TaxAssignment).where(TaxAssignment.line_item_id.in_(line_item_ids))
        result_assignments = await db.execute(stmt_assignments)
        tax_assignments = list(result_assignments.scalars().all())
    else:
        tax_assignments = []

    # Compute tax summary
    tax_summary = compute_tax_summary(tax_assignments, line_items)

    # Build response line items with tax info
    response_line_items = []
    assignment_map = {ta.line_item_id: ta for ta in tax_assignments}

    for li in line_items:
        assignment = assignment_map.get(li.line_item_id)
        response_line_items.append(
            TaxSummaryLineItem(
                line_item_id=li.line_item_id,
                description=li.description,
                quantity=Decimal(str(li.quantity)) if li.quantity else None,
                unit=li.unit,
                unit_price=Decimal(str(li.unit_price)) if li.unit_price else None,
                line_total=Decimal(str(li.line_total)) if li.line_total else None,
                tax_type=assignment.tax_type.value if assignment else None,
                tax_rate=assignment.tax_rate if assignment else None,
                tax_amount=assignment.tax_amount if assignment else None,
            )
        )

    return TaxSummaryResponse(
        line_items=response_line_items,
        per_type_subtotals=tax_summary["per_type"],
        total_tax=tax_summary["total_tax"],
        grand_total=tax_summary["grand_total"],
        locked=is_locked,
    )
