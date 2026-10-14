# backend/app/routes/requests.py
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_role, require_client_assignment
from app.models.audit import AuditEventType
from app.models.extraction_job import ExtractionJob, ExtractionJobStatus
from app.models.request import InvoiceRequest, RequestStatus
from app.models.user import User, UserRole
from app.repositories.request_repository import request_repository
from app.repositories.user_repository import user_repository
from app.schemas.request_schemas import CreateRequestResponse, RequestDetail, RejectionRequest
from app.services.audit_service import log_event
from app.services.request_service import RequestIdGenerationError, generate_request_id
from app.storage import StorageError, file_store

router = APIRouter(prefix="/requests", tags=["requests"])

MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024   # 20 MB per file
MAX_FILES_PER_SESSION = 20
ACCEPTED_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/jpg"}


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CreateRequestResponse)
async def upload_invoice(
    files: List[UploadFile],
    client_id: uuid.UUID = Form(..., description="Use GET /clients to find your client_id"),
    request_date: date = Form(..., description="Invoice date, e.g. 2026-10-14"),
    request_type: str = Form(default="standard", description="Type of request (default: standard)"),
    channel: str = Form(default="upload", description="Submission channel (default: upload)"),
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
            raise HTTPException(502, detail=f"S3 upload failed for '{name}': {exc}")
        except Exception as exc:
            raise HTTPException(502, detail=f"File storage error for '{name}': {exc}")
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


@router.post("/{request_id}/approve", status_code=status.HTTP_200_OK)
async def approve_request(
    request_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Finance Reviewer approval of a READY_FOR_REVIEW request.

    Authorization rules (in order):
    1. SYSTEM_ADMIN attempts are logged as UNAUTHORIZED_APPROVAL_ATTEMPT then rejected.
    2. Any role other than FINANCE_REVIEWER is rejected with 403.
    3. FINANCE_REVIEWER must hold an active ClientAssignment for the request's client.
    4. Segregation of duties: uploader cannot approve their own request.
    5. Request must not be in EXCEPTION status.
    6. Request must be in READY_FOR_REVIEW status.
    """
    # ── Step 1: Block SYSTEM_ADMIN (and log the attempt) ──────────────────────
    if current_user.role == UserRole.SYSTEM_ADMIN:
        req_for_log = await request_repository.get_by_id(db, request_id)
        await log_event(
            db,
            AuditEventType.UNAUTHORIZED_APPROVAL_ATTEMPT,
            payload={
                "request_id": str(request_id),
                "actor_id": str(current_user.user_id),
                "actor_role": current_user.role.value,
                "attempted_at": datetime.now(timezone.utc).isoformat(),
            },
            request_id=request_id if req_for_log else None,
            actor_id=current_user.user_id,
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have authority to approve Requests.",
        )

    # ── Step 2: Enforce FINANCE_REVIEWER role ─────────────────────────────────
    if current_user.role != UserRole.FINANCE_REVIEWER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have authority to approve Requests.",
        )

    # ── Step 3: Check active ClientAssignment ─────────────────────────────────
    req = await request_repository.get_by_id(db, request_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")

    active = await user_repository.is_assignment_active(db, current_user.user_id, req.client_id)
    if not active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access Requests for this client.",
        )

    # ── Step 4: Segregation of duties ─────────────────────────────────────────
    if req.uploader_id == current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-approval is not permitted.",
        )

    # ── Step 5: Block approval when in EXCEPTION status ───────────────────────
    if req.status == RequestStatus.EXCEPTION:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unresolved exceptions must be addressed before this Request can be approved.",
        )

    # ── Step 6: Require READY_FOR_REVIEW status ────────────────────────────────
    if req.status != RequestStatus.READY_FOR_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Request is not in READY_FOR_REVIEW status.",
        )

    # ── Transition to AMIGA_REVIEWED ──────────────────────────────────────────
    await request_repository.update_status(db, request_id, RequestStatus.AMIGA_REVIEWED)

    # ── Persist APPROVED AuditEvent ───────────────────────────────────────────
    await log_event(
        db,
        AuditEventType.APPROVED,
        payload={
            "request_id": str(request_id),
            "approver_id": str(current_user.user_id),
            "approved_at": datetime.now(timezone.utc).isoformat(),
        },
        request_id=request_id,
        actor_id=current_user.user_id,
    )

    await db.commit()
    return {"status": "approved", "request_id": str(request_id)}


@router.post("/{request_id}/dismiss-duplicate", status_code=status.HTTP_200_OK)
async def dismiss_duplicate(
    request_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("FINANCE_REVIEWER")),
):
    """
    Remove the POSSIBLE_DUPLICATE flag from a request.
    Only Finance Reviewer role can dismiss duplicates.
    Requires active client assignment for the request's client.
    """
    # Verify client assignment
    req = await request_repository.get_by_id(db, request_id)
    if req is None:
        raise HTTPException(404, "Request not found.")
    
    active = await user_repository.is_assignment_active(db, current_user.user_id, req.client_id)
    if not active:
        raise HTTPException(403, "You are not authorized to access this request.")
    
    # Fetch the request (already done above for assignment check)
    if req is None:
        raise HTTPException(404, "Request not found.")

    # Check active client assignment (done inline since require_client_assignment
    # cannot be used as a default parameter value with a path param reference)
    active = await user_repository.is_assignment_active(db, current_user.user_id, req.client_id)
    if not active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access Requests for this client.",
        )

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


@router.post("/{request_id}/reject", status_code=status.HTTP_200_OK)
async def reject_request(
    request_id: uuid.UUID,
    body: RejectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Finance Reviewer rejection of a READY_FOR_REVIEW or EXCEPTION request.

    Authorization rules (in order):
    1. Caller must hold FINANCE_REVIEWER role.
    2. Caller must hold an active ClientAssignment for the request's client.
    3. Segregation of duties: uploader cannot reject their own request.
    4. Request must be in READY_FOR_REVIEW or EXCEPTION status.

    Body: { "rejection_reason": "<1–500 chars>" }
    FastAPI returns 422 automatically when the Pydantic constraint is violated.
    """
    # ── Step 1: Enforce FINANCE_REVIEWER role ─────────────────────────────────
    if current_user.role != UserRole.FINANCE_REVIEWER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have authority to reject Requests.",
        )

    # ── Step 2: Load request + active ClientAssignment check ──────────────────
    req = await request_repository.get_by_id(db, request_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")

    active = await user_repository.is_assignment_active(db, current_user.user_id, req.client_id)
    if not active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access Requests for this client.",
        )

    # ── Step 3: Segregation of duties ─────────────────────────────────────────
    if req.uploader_id == current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-rejection is not permitted.",
        )

    # ── Step 4: Status guard ───────────────────────────────────────────────────
    rejectable_statuses = {RequestStatus.READY_FOR_REVIEW, RequestStatus.EXCEPTION}
    if req.status not in rejectable_statuses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Request cannot be rejected from status '{req.status.value}'. "
                "Only READY_FOR_REVIEW or EXCEPTION requests may be rejected."
            ),
        )

    # ── Persist rejection reason ───────────────────────────────────────────────
    await request_repository.set_rejection_reason(db, request_id, body.rejection_reason)

    # ── Transition to REJECTED ─────────────────────────────────────────────────
    await request_repository.update_status(db, request_id, RequestStatus.REJECTED)

    # ── Persist REJECTED AuditEvent ───────────────────────────────────────────
    now_utc = datetime.now(timezone.utc)
    await log_event(
        db,
        AuditEventType.REJECTED,
        payload={
            "request_id": str(request_id),
            "rejection_reason": body.rejection_reason,
            "reviewer_user_id": str(current_user.user_id),
            "timestamp": now_utc.isoformat(),
        },
        request_id=request_id,
        actor_id=current_user.user_id,
    )

    await db.commit()
    return {"status": "rejected", "request_id": str(request_id)}


@router.get("/{request_id}", status_code=status.HTTP_200_OK, response_model=RequestDetail)
async def get_request_detail(
    request_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return full request detail.

    Authorization:
    - Finance_Reviewer, Service_Lead, System_Admin: require active ClientAssignment.
    - Client_PIC: require active ClientAssignment; rejection_reason is included.
    - Other roles: 403.

    The rejection_reason field is visible to all authorized roles so that
    Client_PICs can see why a Request was rejected (Requirement 13.3).
    """
    # ── Permitted roles ────────────────────────────────────────────────────────
    permitted = {
        UserRole.FINANCE_REVIEWER,
        UserRole.SERVICE_LEAD,
        UserRole.SYSTEM_ADMIN,
        UserRole.CLIENT_PIC,
    }
    if current_user.role not in permitted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have authority to perform this action.",
        )

    # ── Load request ───────────────────────────────────────────────────────────
    req = await request_repository.get_by_id(db, request_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")

    # ── Active ClientAssignment check ──────────────────────────────────────────
    active = await user_repository.is_assignment_active(db, current_user.user_id, req.client_id)
    if not active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access Requests for this client.",
        )

    return req
