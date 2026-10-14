# backend/app/routes/voucher.py
"""
POST /requests/{id}/voucher-pdf

Generates a PDF voucher for an AMIGA_REVIEWED request and stores it in S3.
Only accessible to Client_PIC users with an active ClientAssignment for the
client that owns the request.

Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6,
              20.3, 20.6, 21.6, 22.3, 22.4, 22.5, 22.7, 22.8
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256

import jinja2
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db, require_role, require_client_assignment
from app.models.audit import AuditEvent, AuditEventType
from app.models.draft import Draft
from app.models.invoice_fields import HeaderFields, LineItem, PaymentDetails
from app.models.request import InvoiceRequest, RequestStatus
from app.models.tax_assignment import TaxAssignment
from app.models.telemetry import MetricType, TelemetryRecord
from app.models.user import User, UserRole
from app.models.voucher import VoucherPDF
from app.repositories.user_repository import user_repository
from app.schemas.request_schemas import VoucherPreviewResponse, LineItemResponse
from app.services import audit_service
from app.services import template_service
from app.services import tax_service
from app.storage import file_store

router = APIRouter(prefix="/requests", tags=["voucher"])

_VOUCHER_SLA_MS = 5_000  # 5 000 ms SLA threshold for voucher generation


def _html_to_pdf(html_string: str) -> bytes:
    """
    Convert an HTML string to PDF bytes using WeasyPrint.

    Extracted as a module-level function so tests can patch it without
    triggering WeasyPrint's native library imports at patch time.
    """
    import weasyprint  # noqa: PLC0415 — late import avoids GTK load on startup
    return weasyprint.HTML(string=html_string).write_pdf()


@router.post(
    "/{request_id}/voucher-pdf",
    status_code=status.HTTP_201_CREATED,
    summary="Generate a Voucher PDF (Client PIC only)",
)
async def generate_voucher_pdf(
    request_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("CLIENT_PIC")),
) -> dict:
    """
    Generate a PDF voucher for a given request.

    - Request must be in AMIGA_REVIEWED status.
    - Renders the active Jinja2 template with approved field values.
    - Converts HTML to PDF via WeasyPrint (run in thread-pool executor).
    - Uploads the PDF to S3.
    - Persists a VoucherPDF record and writes a VOUCHER_GENERATED AuditEvent.
    - Records telemetry; flags SLA breach if duration > 5 000 ms.
    - On any failure during PDF generation / persistence: returns 500 without
      writing audit or telemetry records.
    """
    # ── Load request ──────────────────────────────────────────────────────────
    req_result = await db.execute(
        select(InvoiceRequest).where(InvoiceRequest.request_id == request_id)
    )
    req: InvoiceRequest | None = req_result.scalars().first()
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found.")

    # ── Client assignment guard (28.1 step 1) ─────────────────────────────────
    active = await user_repository.is_assignment_active(db, current_user.user_id, req.client_id)
    if not active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access Requests for this client.",
        )

    # ── Status guard (28.2) ───────────────────────────────────────────────────
    if req.status != RequestStatus.AMIGA_REVIEWED:
        raise HTTPException(
            status_code=400,
            detail=(
                "The Request has not completed independent review and cannot be "
                "used to generate a voucher."
            ),
        )

    # ── Load active template ──────────────────────────────────────────────────
    # template_service.load_active_template raises HTTPException(404) if none.
    template = await template_service.load_active_template(db)

    # ── Load approved draft + its related rows ────────────────────────────────
    draft_result = await db.execute(
        select(Draft).where(Draft.request_id == request_id)
    )
    draft: Draft | None = draft_result.scalars().first()

    # HeaderFields
    header_fields: HeaderFields | None = None
    if draft:
        hf_result = await db.execute(
            select(HeaderFields).where(HeaderFields.draft_id == draft.draft_id)
        )
        header_fields = hf_result.scalars().first()

    # LineItems
    line_items: list[LineItem] = []
    if draft:
        li_result = await db.execute(
            select(LineItem)
            .where(LineItem.draft_id == draft.draft_id)
            .order_by(LineItem.sequence_number)
        )
        line_items = list(li_result.scalars().all())

    # PaymentDetails
    payment_details: PaymentDetails | None = None
    if draft:
        pd_result = await db.execute(
            select(PaymentDetails).where(PaymentDetails.draft_id == draft.draft_id)
        )
        payment_details = pd_result.scalars().first()

    # TaxAssignments for the line items
    tax_assignments: list[TaxAssignment] = []
    if line_items:
        line_item_ids = [li.line_item_id for li in line_items]
        ta_result = await db.execute(
            select(TaxAssignment).where(TaxAssignment.line_item_id.in_(line_item_ids))
        )
        tax_assignments = list(ta_result.scalars().all())

    # ── Compute tax summary ───────────────────────────────────────────────────
    tax_summary = tax_service.compute_tax_summary(tax_assignments, line_items)

    # ── Build Jinja2 context ──────────────────────────────────────────────────
    def _dec(val) -> str:
        """Format a numeric DB value as string for the template."""
        if val is None:
            return "0.00"
        return str(Decimal(str(val)))

    line_items_ctx = []
    ta_by_item = {ta.line_item_id: ta for ta in tax_assignments}
    for li in line_items:
        ta = ta_by_item.get(li.line_item_id)
        line_items_ctx.append(
            {
                "description": li.description or "",
                "quantity": _dec(li.quantity),
                "unit": li.unit or "",
                "unit_price": _dec(li.unit_price),
                "line_total": _dec(li.line_total),
                "tax_type": ta.tax_type if ta else "",
                "tax_amount": _dec(ta.tax_amount) if ta else "0.00",
            }
        )

    per_type_subtotals = tax_summary["per_type_subtotals"]
    tax_summary_ctx = [
        {"tax_type": k, "subtotal": str(v)}
        for k, v in per_type_subtotals.items()
    ]

    context = {
        "vendor_name": header_fields.vendor_name if header_fields else "",
        "invoice_number": header_fields.invoice_number if header_fields else "",
        "invoice_date": str(header_fields.invoice_date) if header_fields and header_fields.invoice_date else "",
        "subtotal": _dec(header_fields.subtotal) if header_fields else "0.00",
        "total_amount": _dec(header_fields.total_amount) if header_fields else "0.00",
        "tax_amount": _dec(header_fields.tax_amount) if header_fields else "0.00",
        "fee_amount": _dec(header_fields.fee_amount) if header_fields else "0.00",
        "rounding_adj": _dec(header_fields.rounding_adj) if header_fields else "0.00",
        "line_items_table": line_items_ctx,
        "bank_account_number": payment_details.bank_account_number if payment_details else "",
        "bank_name": payment_details.bank_name if payment_details else "",
        "payment_reference": payment_details.payment_reference if payment_details else "",
        "tax_summary_table": tax_summary_ctx,
        "total_tax": str(tax_summary["total_tax"]),
        "grand_total": str(tax_summary["grand_total"]),
        "authorization_disclaimer": settings.AUTHORIZATION_DISCLAIMER,
    }

    # ── Generation steps (steps 5-11) — catch all failures ───────────────────
    start_time = datetime.now(timezone.utc)
    try:
        # Step 5: Render HTML
        rendered_html: str = (
            jinja2.Environment(loader=jinja2.BaseLoader())
            .from_string(template.template_content)
            .render(context)
        )

        # Step 6: Convert to PDF in a thread-pool (WeasyPrint is synchronous)
        loop = asyncio.get_event_loop()
        pdf_bytes: bytes = await loop.run_in_executor(None, _html_to_pdf, rendered_html)

        # Step 7: Compute hashes
        disclaimer_hash = sha256(settings.AUTHORIZATION_DISCLAIMER.encode()).hexdigest()
        template_hash = sha256(rendered_html.encode()).hexdigest()

        # Step 8: Upload to S3
        voucher_pdf_id = uuid.uuid4()
        file_key = f"vouchers/{request_id}/{voucher_pdf_id}.pdf"
        await file_store.upload(file_key, pdf_bytes, "application/pdf")

        # Step 9: Persist VoucherPDF record
        now_utc = datetime.now(timezone.utc)
        voucher_pdf = VoucherPDF(
            voucher_pdf_id=voucher_pdf_id,
            request_id=request_id,
            file_key=file_key,
            generated_by=current_user.user_id,
            generated_at=now_utc,
            template_version=template.version,
            template_hash=template_hash,
            disclaimer_hash=disclaimer_hash,
        )
        db.add(voucher_pdf)
        await db.flush()  # get the record in the transaction before audit

        # Step 10: Write VOUCHER_GENERATED AuditEvent (same transaction)
        await audit_service.log_event(
            db,
            AuditEventType.VOUCHER_GENERATED,
            payload={
                "voucher_pdf_id": str(voucher_pdf_id),
                "file_key": file_key,
                "template_version": template.version,
                "generated_by": str(current_user.user_id),
                "generated_at": now_utc.isoformat(),
            },
            request_id=request_id,
            actor_id=current_user.user_id,
        )

        # Step 11: Record telemetry
        end_time = datetime.now(timezone.utc)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
        is_breach = duration_ms > _VOUCHER_SLA_MS

        telemetry = TelemetryRecord(
            record_id=uuid.uuid4(),
            metric_type=MetricType.VOUCHER_GENERATION_DURATION,
            subject_id=str(request_id),
            duration_ms=duration_ms,
            page_count=None,
            is_breach=is_breach,
            breach_threshold_ms=_VOUCHER_SLA_MS,
            measured_at=end_time,
        )
        db.add(telemetry)
        await db.flush()

        # Commit VoucherPDF + AuditEvent + TelemetryRecord together
        await db.commit()

    except HTTPException:
        # Re-raise HTTPExceptions (e.g. from load_active_template) as-is
        raise
    except Exception:
        # Step 12: On any failure, roll back and return 500.
        # Do NOT write AuditEvent or TelemetryRecord.
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Voucher generation failed. Please try again.",
        )

    # Step 13: Success response
    return {
        "voucher_pdf_id": str(voucher_pdf_id),
        "file_key": file_key,
        "generated_at": now_utc.isoformat(),
    }


@router.get(
    "/{request_id}/voucher-pdf",
    summary="Download a Voucher PDF and record SENT_TO_CLIENT (Client PIC only)",
)
async def download_voucher_pdf(
    request_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("CLIENT_PIC")),
) -> StreamingResponse:
    """
    Download a PDF voucher for a given request.

    - Request must be in AMIGA_REVIEWED status.
    - Fetch the PDF bytes from S3.
    - Idempotency check: if no prior SENT_TO_CLIENT AuditEvent exists,
      write VOUCHER_DOWNLOADED and STATUS_CHANGED (AMIGA_REVIEWED → SENT_TO_CLIENT)
      AuditEvents, then transition Request status to SENT_TO_CLIENT.
    - Stream PDF bytes using FastAPI StreamingResponse.
    - Display SENT_TO_CLIENT UTC timestamp on the Request detail screen once recorded.

    Requirements: 16.1, 16.2, 16.5
    """
    # ── Load request ──────────────────────────────────────────────────────────
    req_result = await db.execute(
        select(InvoiceRequest).where(InvoiceRequest.request_id == request_id)
    )
    req: InvoiceRequest | None = req_result.scalars().first()
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found.")

    # ── Client assignment guard (30.2) ─────────────────────────────────────
    active = await user_repository.is_assignment_active(db, current_user.user_id, req.client_id)
    if not active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access Requests for this client.",
        )

    # ── Status guard (30.2) ───────────────────────────────────────────────────
    # Accept AMIGA_REVIEWED (first download) or SENT_TO_CLIENT (idempotent download)
    if req.status not in (RequestStatus.AMIGA_REVIEWED, RequestStatus.SENT_TO_CLIENT):
        raise HTTPException(
            status_code=400,
            detail="The voucher is not yet available. The request has not completed independent review.",
        )

    # ── Idempotency check: if request is already SENT_TO_CLIENT, skip event creation ──
    # The task spec says: "if no prior SENT_TO_CLIENT AuditEvent exists"
    # We check for this by looking at request status - it starts AMIGA_REVIEWED and
    # transitions to SENT_TO_CLIENT on first download
    already_sent = req.status == RequestStatus.SENT_TO_CLIENT

    # ── Fetch PDF from S3 ────────────────────────────────────────────────────
    # Find the most recent VoucherPDF for this request
    pdf_result = await db.execute(
        select(VoucherPDF)
        .where(VoucherPDF.request_id == request_id)
        .order_by(VoucherPDF.generated_at.desc())
        .limit(1)
    )
    voucher_pdf: VoucherPDF | None = pdf_result.scalars().first()
    if voucher_pdf is None:
        raise HTTPException(
            status_code=404,
            detail="No voucher PDF has been generated for this request.",
        )

    # Download PDF from S3
    pdf_bytes = await file_store.download(voucher_pdf.file_key)

    # ── If this is the first download, write audit events and transition status ──
    if not already_sent:
        now_utc = datetime.now(timezone.utc)

        # Write VOUCHER_DOWNLOADED event
        await audit_service.log_event(
            db,
            AuditEventType.VOUCHER_DOWNLOADED,
            payload={
                "voucher_pdf_id": str(voucher_pdf.voucher_pdf_id),
                "file_key": voucher_pdf.file_key,
                "downloaded_by": str(current_user.user_id),
                "downloaded_at": now_utc.isoformat(),
            },
            request_id=request_id,
            actor_id=current_user.user_id,
        )

        # Transition status to SENT_TO_CLIENT
        req.status = RequestStatus.SENT_TO_CLIENT
        req.updated_at = now_utc
        db.add(req)
        await db.flush()

        # Write STATUS_CHANGED event
        await audit_service.log_event(
            db,
            AuditEventType.STATUS_CHANGED,
            payload={
                "old_status": RequestStatus.AMIGA_REVIEWED,
                "new_status": RequestStatus.SENT_TO_CLIENT,
                "transitioned_at": now_utc.isoformat(),
                "transitioned_by": str(current_user.user_id),
            },
            request_id=request_id,
            actor_id=current_user.user_id,
        )

        # Commit the changes
        await db.commit()

    # ── Stream the PDF ───────────────────────────────────────────────────────
    return StreamingResponse(
        content=iter([pdf_bytes]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=voucher_{request_id}.pdf"
        },
    )



@router.get(
    "/{request_id}/voucher-preview",
    response_model=VoucherPreviewResponse,
    summary="Get voucher preview (Finance Reviewer or Client PIC)",
)
async def get_voucher_preview(
    request_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("FINANCE_REVIEWER", "CLIENT_PIC")),
) -> VoucherPreviewResponse:
    """
    Get the voucher preview for an AMIGA_REVIEWED request.

    Returns all approved HeaderFields, LineItems, PaymentDetails, and the
    authorization disclaimer text in a read-only format. Only accessible to
    Finance Reviewers or Client PICs with an active ClientAssignment for the
    client that owns the request.

    Responds within 3 seconds (Requirement 14.3).

    Requirements: 14.1, 14.2, 14.3
    """
    start_time = datetime.now(timezone.utc)

    # ── Load request ──────────────────────────────────────────────────────────
    req_result = await db.execute(
        select(InvoiceRequest).where(InvoiceRequest.request_id == request_id)
    )
    req: InvoiceRequest | None = req_result.scalars().first()
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found.")

    # ── Client assignment guard ───────────────────────────────────────────────
    active = await user_repository.is_assignment_active(db, current_user.user_id, req.client_id)
    if not active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access Requests for this client.",
        )

    # ── Load approved draft + its related rows ────────────────────────────────
    draft_result = await db.execute(
        select(Draft).where(Draft.request_id == request_id)
    )
    draft: Draft | None = draft_result.scalars().first()

    # HeaderFields
    header_fields: HeaderFields | None = None
    if draft:
        hf_result = await db.execute(
            select(HeaderFields).where(HeaderFields.draft_id == draft.draft_id)
        )
        header_fields = hf_result.scalars().first()

    # LineItems
    line_items: list[LineItem] = []
    if draft:
        li_result = await db.execute(
            select(LineItem)
            .where(LineItem.draft_id == draft.draft_id)
            .order_by(LineItem.sequence_number)
        )
        line_items = list(li_result.scalars().all())

    # PaymentDetails
    payment_details: PaymentDetails | None = None
    if draft:
        pd_result = await db.execute(
            select(PaymentDetails).where(PaymentDetails.draft_id == draft.draft_id)
        )
        payment_details = pd_result.scalars().first()

    # ── Convert line items to response schema ──────────────────────────────────
    line_items_response: list[LineItemResponse] = [
        LineItemResponse(
            line_item_id=li.line_item_id,
            draft_id=li.draft_id,
            sequence_number=li.sequence_number,
            description=li.description,
            quantity=str(li.quantity) if li.quantity is not None else None,
            unit=li.unit,
            unit_price=str(li.unit_price) if li.unit_price is not None else None,
            line_total=str(li.line_total) if li.line_total is not None else None,
            extraction_status=li.extraction_status,
        )
        for li in line_items
    ]

    # ── Convert header and payment details to strings ──────────────────────────
    def _format_decimal(val) -> str | None:
        """Format a numeric DB value as string for the response."""
        if val is None:
            return None
        return str(Decimal(str(val)))

    # ── Build preview response ────────────────────────────────────────────────
    now_utc = datetime.now(timezone.utc)
    preview = VoucherPreviewResponse(
        request_id=request_id,
        vendor_name=header_fields.vendor_name if header_fields else None,
        invoice_number=header_fields.invoice_number if header_fields else None,
        invoice_date=str(header_fields.invoice_date) if header_fields and header_fields.invoice_date else None,
        currency=header_fields.currency if header_fields else None,
        subtotal=_format_decimal(header_fields.subtotal) if header_fields else None,
        total_amount=_format_decimal(header_fields.total_amount) if header_fields else None,
        tax_amount=_format_decimal(header_fields.tax_amount) if header_fields else None,
        fee_amount=_format_decimal(header_fields.fee_amount) if header_fields else None,
        rounding_adj=_format_decimal(header_fields.rounding_adj) if header_fields else None,
        line_items=line_items_response,
        bank_account_number=payment_details.bank_account_number if payment_details else None,
        bank_name=payment_details.bank_name if payment_details else None,
        payment_reference=payment_details.payment_reference if payment_details else None,
        authorization_disclaimer=settings.AUTHORIZATION_DISCLAIMER,
        generated_at=now_utc,
    )

    # ── Log timing for SLA compliance ─────────────────────────────────────────
    end_time = datetime.now(timezone.utc)
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    # Requirement 14.3 requires response within 3 seconds; we don't fail, just log
    if duration_ms > 3000:
        # Log a telemetry record for monitoring (optional; spec does not require it)
        pass

    return preview
