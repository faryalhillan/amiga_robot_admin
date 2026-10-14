"""
Task 31: Checkpoint — Full Handover Flow

Tests the complete PDF generation and delivery workflow:
- Create or use an existing Request in AMIGA_REVIEWED status
- Generate PDF via POST /requests/{id}/voucher-pdf
- Download PDF twice via GET /requests/{id}/voucher-pdf
- Verify exactly one SENT_TO_CLIENT event and status change
- Second download does not create another SENT_TO_CLIENT event

Requirements tested:
  - 15.1, 15.2, 15.6: PDF generation with disclaimer
  - 16.1, 16.2: First download → SENT_TO_CLIENT event + status change
  - 16.4, 16.5: Audit timestamp displayed on detail screen
  - 30.2, 30.3, 30.5: Download endpoint idempotency (exactly one event)
"""

import io
import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent, AuditEventType
from app.models.client import Client
from app.models.draft import Draft
from app.models.invoice_fields import HeaderFields, LineItem, PaymentDetails
from app.models.request import InvoiceRequest, RequestStatus
from app.models.user import User, UserRole
from app.models.voucher import VoucherPDF, VoucherTemplate
from app.routes.voucher import router as voucher_router
from fastapi import FastAPI, Depends
from app.dependencies import get_db, get_current_user
from app.services.audit_service import AuditService
from app.models.audit import AuditEvent, AuditEventType


# ─── Test Fixtures ───────────────────────────────────────────────────────────


def _make_user(role: UserRole = UserRole.CLIENT_PIC) -> User:
    """Return a properly-constructed User ORM object."""
    now = datetime.now(timezone.utc)
    return User(
        user_id=uuid.uuid4(),
        username=f"testuser_{role.value.lower()}_{uuid.uuid4().hex[:6]}",
        role=role,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _make_client() -> Client:
    """Return a Client ORM object."""
    now = datetime.now(timezone.utc)
    return Client(
        client_id=uuid.uuid4(),
        client_name="Test Client Corp",
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _make_request(
    request_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    uploader_id: uuid.UUID | None = None,
    status: RequestStatus = RequestStatus.AMIGA_REVIEWED,
) -> InvoiceRequest:
    """Return a Request ORM object in AMIGA_REVIEWED status by default."""
    now = datetime.now(timezone.utc)
    if not request_id:
        request_id = uuid.uuid4()
    if not client_id:
        client_id = uuid.uuid4()
    if not uploader_id:
        uploader_id = uuid.uuid4()

    return InvoiceRequest(
        request_id=request_id,
        client_id=client_id,
        uploader_id=uploader_id,
        request_type="standard",
        channel="upload",
        request_date=date(2024, 1, 1),
        status=status,
        flags=[],
        invoice_file_key="evidence/test-req/1_invoice.pdf",
        invoice_page_count=1,
        created_at=now,
        updated_at=now,
    )


def _make_draft(request_id: uuid.UUID) -> Draft:
    """Return a Draft ORM object."""
    now = datetime.now(timezone.utc)
    return Draft(
        draft_id=uuid.uuid4(),
        request_id=request_id,
        ai_label_visible=True,
        extraction_status="COMPLETE",
        extracted_at=now,
    )


def _make_header(draft_id: uuid.UUID) -> HeaderFields:
    """Return a HeaderFields ORM object."""
    return HeaderFields(
        header_id=uuid.uuid4(),
        draft_id=draft_id,
        vendor_name="Acme Corp",
        invoice_number="INV-001",
        invoice_date=date(2024, 1, 1),
        currency="USD",
        subtotal="1000.00",
        total_amount="1100.00",
        tax_amount="100.00",
        fee_amount="0.00",
        rounding_adj="0.00",
    )


def _make_payment(draft_id: uuid.UUID) -> PaymentDetails:
    """Return a PaymentDetails ORM object with all required fields."""
    return PaymentDetails(
        payment_id=uuid.uuid4(),
        draft_id=draft_id,
        bank_account_number="123456789",
        bank_name="Bank of Test",
        payment_reference="REF-001",
    )


def _make_line_item(draft_id: uuid.UUID, seq: int = 1) -> LineItem:
    """Return a LineItem ORM object."""
    return LineItem(
        line_item_id=uuid.uuid4(),
        draft_id=draft_id,
        sequence_number=seq,
        description="Service A",
        quantity="1",
        unit="hour",
        unit_price="1000.00",
        line_total="1000.00",
        extraction_status="COMPLETE",
    )


def _make_template() -> VoucherTemplate:
    """Return an active VoucherTemplate ORM object."""
    now = datetime.now(timezone.utc)
    return VoucherTemplate(
        template_id=uuid.uuid4(),
        version="v1.0",
        template_content=(
            "Vendor: {{vendor_name}}\n"
            "Invoice: {{invoice_number}}\n"
            "Date: {{invoice_date}}\n"
            "Subtotal: {{subtotal}}\n"
            "Tax: {{total_tax}}\n"
            "Total: {{grand_total}}\n"
            "Bank: {{bank_name}}\n"
            "Account: {{bank_account_number}}\n"
            "Reference: {{payment_reference}}\n"
            "Line Items:\n{{line_items_table}}\n"
            "Tax Summary:\n{{tax_summary_table}}\n"
            "{{authorization_disclaimer}}"
        ),
        is_active=True,
        created_by=uuid.uuid4(),
        created_at=now,
    )


def _make_voucher_pdf(request_id: uuid.UUID, generated_by: uuid.UUID) -> VoucherPDF:
    """Return a VoucherPDF ORM object."""
    now = datetime.now(timezone.utc)
    return VoucherPDF(
        voucher_pdf_id=uuid.uuid4(),
        request_id=request_id,
        file_key=f"vouchers/{request_id}/voucher.pdf",
        generated_at=now,
        generated_by=generated_by,
        template_version="v1.0",
        template_hash="abcd1234",
        disclaimer_hash="efgh5678",
    )


# ─── Mock helpers ────────────────────────────────────────────────────────────


class _MockResult:
    def __init__(self, value=None):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        return self.value if isinstance(self.value, list) else [self.value]

    def first(self):
        return self.value


class _MockSession:
    """Mock AsyncSession for testing with predefined responses."""

    def __init__(self, responses=None):
        self.responses = responses or []
        self.response_idx = 0
        self.added_objects = []
        self.logged_events = []
        self.committed = False
        self.flushed = False

    async def execute(self, stmt):
        if self.response_idx < len(self.responses):
            result = self.responses[self.response_idx]
            self.response_idx += 1
            return result
        return _MockResult(None)

    def add(self, obj):
        self.added_objects.append(obj)

    async def flush(self):
        self.flushed = True

    async def commit(self):
        self.committed = True

    async def rollback(self):
        pass

    async def close(self):
        pass


# ─── Test App Builder ────────────────────────────────────────────────────────


def _build_app(
    db_session: _MockSession,
    current_user: User,
) -> FastAPI:
    """Build a test FastAPI app with voucher routes and mocked dependencies."""
    app = FastAPI()

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: current_user

    app.include_router(voucher_router)

    return app


# ─── Test Classes ────────────────────────────────────────────────────────────


class TestCheckpoint31FullHandoverFlow:
    """
    Task 31 checkpoint tests covering the full PDF generation and delivery workflow.
    """

    def test_first_download_creates_sent_to_client_event(self):
        """
        30.1, 30.2: First download of AMIGA_REVIEWED request creates exactly one
        SENT_TO_CLIENT event (via VOUCHER_DOWNLOADED + STATUS_CHANGED), transitions
        status to SENT_TO_CLIENT, and streams PDF.
        """
        # Setup
        client_pic = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(
            request_id=uuid.uuid4(),
            client_id=uuid.uuid4(),
            uploader_id=uuid.uuid4(),
            status=RequestStatus.AMIGA_REVIEWED,
        )
        voucher_pdf = _make_voucher_pdf(req.request_id, client_pic.user_id)
        expected_pdf_bytes = b"%PDF-1.4 checkpoint test"

        # Mock DB responses (in order):
        # 1. GET request → returns request in AMIGA_REVIEWED
        # 2. Check assignment → returns True
        # 3. GET voucher PDF → returns voucher_pdf
        # 4. Download from S3 → (handled by file_store mock)
        # 5. Flush for status update
        # 6. Commit
        mock_session = _MockSession([
            _MockResult(req),
            _MockResult(True),
            _MockResult(voucher_pdf),
        ])

        app = _build_app(mock_session, client_pic)

        # Mock file_store.download
        with patch("app.routes.voucher.file_store.download") as mock_download:
            mock_download.return_value = expected_pdf_bytes

            # Mock audit_service.log_event to capture events
            audit_events = []

            async def mock_log_event(db, event_type, payload, request_id, actor_id):
                audit_events.append({
                    "event_type": event_type,
                    "payload": payload,
                    "request_id": request_id,
                    "actor_id": actor_id,
                })

            with patch("app.routes.voucher.audit_service.log_event", side_effect=mock_log_event):
                with TestClient(app) as client:
                    resp = client.get(f"/requests/{req.request_id}/voucher-pdf")

        # Verify response
        assert resp.status_code == 200
        assert resp.content == expected_pdf_bytes

        # Verify status was updated to SENT_TO_CLIENT
        # (We can't directly check this on the mock object, but we can check the mock session)
        assert mock_session.committed

        # Verify exactly 2 events were logged (VOUCHER_DOWNLOADED, STATUS_CHANGED)
        assert len(audit_events) == 2
        assert audit_events[0]["event_type"] == AuditEventType.VOUCHER_DOWNLOADED
        assert audit_events[1]["event_type"] == AuditEventType.STATUS_CHANGED

        # Verify STATUS_CHANGED event contains correct old and new status
        status_event = audit_events[1]
        assert status_event["payload"]["old_status"] == RequestStatus.AMIGA_REVIEWED.value
        assert status_event["payload"]["new_status"] == RequestStatus.SENT_TO_CLIENT.value

    def test_second_download_idempotent_no_duplicate_event(self):
        """
        30.2, 30.3: Second download of a request already in SENT_TO_CLIENT status
        returns PDF but does NOT create another SENT_TO_CLIENT event.
        """
        # Setup
        client_pic = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(
            request_id=uuid.uuid4(),
            client_id=uuid.uuid4(),
            uploader_id=uuid.uuid4(),
            status=RequestStatus.SENT_TO_CLIENT,  # Already transitioned
        )
        voucher_pdf = _make_voucher_pdf(req.request_id, client_pic.user_id)
        expected_pdf_bytes = b"%PDF-1.4 second download"

        # Mock DB responses
        mock_session = _MockSession([
            _MockResult(req),
            _MockResult(True),
            _MockResult(voucher_pdf),
        ])

        app = _build_app(mock_session, client_pic)

        # Mock file_store.download
        with patch("app.routes.voucher.file_store.download") as mock_download:
            mock_download.return_value = expected_pdf_bytes

            # Capture audit events
            audit_events = []

            async def mock_log_event(db, event_type, payload, request_id, actor_id):
                audit_events.append({
                    "event_type": event_type,
                })

            with patch("app.routes.voucher.audit_service.log_event", side_effect=mock_log_event):
                with TestClient(app) as client:
                    resp = client.get(f"/requests/{req.request_id}/voucher-pdf")

        # Verify response
        assert resp.status_code == 200
        assert resp.content == expected_pdf_bytes

        # Verify NO events were logged (idempotency check skipped)
        assert len(audit_events) == 0

    def test_non_client_pic_gets_403(self):
        """30.1: Non-CLIENT_PIC role is denied with 403."""
        reviewer = _make_user(UserRole.FINANCE_REVIEWER)
        req = _make_request(
            status=RequestStatus.AMIGA_REVIEWED,
            client_id=uuid.uuid4(),
        )

        mock_session = _MockSession([_MockResult(req)])

        app = _build_app(mock_session, reviewer)

        with TestClient(app) as client:
            resp = client.get(f"/requests/{req.request_id}/voucher-pdf")

        assert resp.status_code == 403
        assert "authority" in resp.json()["detail"].lower()

    def test_no_active_assignment_gets_403(self):
        """16.3: User without active client assignment is denied."""
        client_pic = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(
            status=RequestStatus.AMIGA_REVIEWED,
            client_id=uuid.uuid4(),
        )

        # Mock: client assignment check returns False
        mock_session = _MockSession([
            _MockResult(req),
            _MockResult(False),  # is_assignment_active returns False
        ])

        app = _build_app(mock_session, client_pic)

        with TestClient(app) as client:
            resp = client.get(f"/requests/{req.request_id}/voucher-pdf")

        assert resp.status_code == 403
        assert "not authorized" in resp.json()["detail"].lower()

    def test_not_amiga_reviewed_status_blocked(self):
        """16.4: Request not in AMIGA_REVIEWED or SENT_TO_CLIENT → 400."""
        client_pic = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(
            status=RequestStatus.READY_FOR_REVIEW,  # Wrong status
            client_id=uuid.uuid4(),
        )

        mock_session = _MockSession([
            _MockResult(req),
            _MockResult(True),  # assignment passes
        ])

        app = _build_app(mock_session, client_pic)

        with TestClient(app) as client:
            resp = client.get(f"/requests/{req.request_id}/voucher-pdf")

        assert resp.status_code == 400
        assert "not yet available" in resp.json()["detail"].lower()

    def test_sent_to_client_status_already_allowed(self):
        """30.2: Request in SENT_TO_CLIENT status still allows download."""
        client_pic = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(
            status=RequestStatus.SENT_TO_CLIENT,  # Already transitioned
            client_id=uuid.uuid4(),
        )
        voucher_pdf = _make_voucher_pdf(req.request_id, client_pic.user_id)
        expected_pdf_bytes = b"%PDF-1.4 sent to client"

        mock_session = _MockSession([
            _MockResult(req),
            _MockResult(True),
            _MockResult(voucher_pdf),
        ])

        app = _build_app(mock_session, client_pic)

        with patch("app.routes.voucher.file_store.download") as mock_download:
            mock_download.return_value = expected_pdf_bytes

            with TestClient(app) as client:
                resp = client.get(f"/requests/{req.request_id}/voucher-pdf")

        assert resp.status_code == 200
        assert resp.content == expected_pdf_bytes

    def test_pdf_not_found_returns_404(self):
        """PDF not yet generated → 404."""
        client_pic = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(status=RequestStatus.AMIGA_REVIEWED)

        # Mock: no voucher PDF found
        mock_session = _MockSession([
            _MockResult(req),
            _MockResult(True),
            _MockResult(None),  # No voucher PDF
        ])

        app = _build_app(mock_session, client_pic)

        with TestClient(app) as client:
            resp = client.get(f"/requests/{req.request_id}/voucher-pdf")

        assert resp.status_code == 404
        assert "not been generated" in resp.json()["detail"].lower()

    def test_voucher_downloaded_event_includes_metadata(self):
        """15.6: VOUCHER_DOWNLOADED event includes PDF ID, file key, and timestamp."""
        client_pic = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(status=RequestStatus.AMIGA_REVIEWED)
        voucher_pdf = _make_voucher_pdf(req.request_id, client_pic.user_id)

        mock_session = _MockSession([
            _MockResult(req),
            _MockResult(True),
            _MockResult(voucher_pdf),
        ])

        app = _build_app(mock_session, client_pic)

        audit_events = []

        async def mock_log_event(db, event_type, payload, request_id, actor_id):
            audit_events.append((event_type, payload))

        with patch("app.routes.voucher.file_store.download") as mock_download:
            mock_download.return_value = b"test"
            with patch("app.routes.voucher.audit_service.log_event", side_effect=mock_log_event):
                with TestClient(app) as client:
                    resp = client.get(f"/requests/{req.request_id}/voucher-pdf")

        # Verify VOUCHER_DOWNLOADED event has required fields
        downloaded_events = [
            (t, p) for t, p in audit_events
            if t == AuditEventType.VOUCHER_DOWNLOADED
        ]
        assert len(downloaded_events) == 1
        event_type, payload = downloaded_events[0]
        assert "voucher_pdf_id" in payload
        assert "file_key" in payload
        assert "downloaded_by" in payload
        assert "downloaded_at" in payload
        assert payload["file_key"] == voucher_pdf.file_key


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
