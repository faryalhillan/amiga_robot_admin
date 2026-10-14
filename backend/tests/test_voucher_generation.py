# backend/tests/test_voucher_generation.py
"""
Tests for Task 28 — POST /requests/{id}/voucher-pdf

Covers:
  - 28.1: Endpoint implementation (role guard, assignment guard, status guard,
            template loading, HTML rendering, PDF conversion, S3 upload,
            VoucherPDF persistence, AuditEvent, telemetry)
  - 28.2: 400 error when request is not AMIGA_REVIEWED
  - 28.3: pytest tests as specified

Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 20.3, 20.6
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.models.audit import AuditEvent, AuditEventType
from app.models.draft import Draft, ExtractionStatus
from app.models.invoice_fields import HeaderFields, LineItem, LineExtractionStatus, PaymentDetails
from app.models.request import InvoiceRequest, RequestStatus
from app.models.telemetry import TelemetryRecord
from app.models.user import User, UserRole
from app.models.voucher import VoucherTemplate, VoucherPDF
from app.routes.voucher import router


# ─── Fixtures / helpers ───────────────────────────────────────────────────────


def _make_user(role: UserRole = UserRole.CLIENT_PIC) -> User:
    now = datetime.now(timezone.utc)
    return User(
        user_id=uuid.uuid4(),
        username=f"test_{role.value.lower()}_{uuid.uuid4().hex[:6]}",
        role=role,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _make_request(status: RequestStatus = RequestStatus.AMIGA_REVIEWED) -> InvoiceRequest:
    now = datetime.now(timezone.utc)
    return InvoiceRequest(
        request_id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        uploader_id=uuid.uuid4(),
        request_type="standard",
        channel="upload",
        request_date=date.today(),
        status=status,
        flags=[],
        invoice_file_key="evidence/test/invoice.pdf",
        invoice_page_count=1,
        created_at=now,
        updated_at=now,
    )


def _make_template() -> VoucherTemplate:
    return VoucherTemplate(
        template_id=uuid.uuid4(),
        version="v1.0",
        template_content=(
            "<html><body>"
            "{{ vendor_name }}|{{ authorization_disclaimer }}"
            "{% for item in line_items_table %}{{ item.description }}{% endfor %}"
            "{% for row in tax_summary_table %}{{ row.tax_type }}{% endfor %}"
            "</body></html>"
        ),
        is_active=True,
        created_by=None,
        created_at=datetime.now(timezone.utc),
    )


def _make_draft(request_id: uuid.UUID) -> Draft:
    return Draft(
        draft_id=uuid.uuid4(),
        request_id=request_id,
        ai_label_visible=True,
        extraction_status=ExtractionStatus.COMPLETE,
        extracted_at=datetime.now(timezone.utc),
    )


def _make_header(draft_id: uuid.UUID) -> HeaderFields:
    from decimal import Decimal
    return HeaderFields(
        header_id=uuid.uuid4(),
        draft_id=draft_id,
        vendor_name="Acme Corp",
        invoice_number="INV-001",
        invoice_date=date.today(),
        currency="IDR",
        subtotal=Decimal("1000.00"),
        total_amount=Decimal("1100.00"),
        tax_amount=Decimal("100.00"),
        fee_amount=Decimal("0.00"),
        rounding_adj=Decimal("0.00"),
    )


def _make_line_item(draft_id: uuid.UUID) -> LineItem:
    from decimal import Decimal
    return LineItem(
        line_item_id=uuid.uuid4(),
        draft_id=draft_id,
        sequence_number=1,
        description="Consulting services",
        quantity=Decimal("1"),
        unit="hour",
        unit_price=Decimal("1000.00"),
        line_total=Decimal("1000.00"),
        extraction_status=LineExtractionStatus.COMPLETE,
    )


def _make_payment_details(draft_id: uuid.UUID) -> PaymentDetails:
    return PaymentDetails(
        payment_id=uuid.uuid4(),
        draft_id=draft_id,
        bank_account_number="1234567890",
        bank_name="Bank Mandiri",
        payment_reference="PAY-REF-001",
    )


# ─── Mock DB session factory ──────────────────────────────────────────────────

class _MockSession:
    """
    A configurable mock AsyncSession.  Each call to execute() pops the next
    item from `side_effects`; if the list is exhausted it returns a default
    empty result.
    """

    def __init__(self, side_effects: list):
        self._effects = list(side_effects)
        self.added: list = []
        self.committed = False
        self.rolled_back = False
        self.flushed = 0

    def _next_result(self):
        if self._effects:
            return self._effects.pop(0)
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        return mock_result

    async def execute(self, *args, **kwargs):
        return self._next_result()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed += 1

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


def _scalar_result(value):
    """Build a mock result whose .scalars().first() returns *value*."""
    r = MagicMock()
    r.scalars.return_value.first.return_value = value
    r.scalars.return_value.all.return_value = [value] if value is not None else []
    return r


def _scalars_all_result(values: list):
    """Build a mock result whose .scalars().all() returns *values*."""
    r = MagicMock()
    r.scalars.return_value.all.return_value = values
    r.scalars.return_value.first.return_value = values[0] if values else None
    return r


def _empty_result():
    r = MagicMock()
    r.scalars.return_value.first.return_value = None
    r.scalars.return_value.all.return_value = []
    return r


# ─── App builder ─────────────────────────────────────────────────────────────


def _build_app(mock_session: _MockSession, acting_user: User) -> FastAPI:
    """Build a minimal FastAPI app with all relevant overrides."""
    from app.dependencies import get_db, get_current_user

    app = FastAPI()
    app.include_router(router)

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: acting_user
    return app


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestNonAmigaReviewedStatusBlocked:
    """28.2 / 28.3: Request not in AMIGA_REVIEWED → 400 with explicit message."""

    def test_non_amiga_reviewed_status_blocked(self):
        """
        POST to the endpoint when request.status == READY_FOR_REVIEW → 400
        with a message stating independent review is not complete.
        """
        user = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(status=RequestStatus.READY_FOR_REVIEW)

        # DB calls:
        # 1. select(InvoiceRequest) → req
        # 2. is_assignment_active → True (simulated via user_repository patch)
        mock_session = _MockSession([_scalar_result(req)])

        app = _build_app(mock_session, user)

        # Patch user_repository.is_assignment_active to return True
        with patch(
            "app.routes.voucher.user_repository.is_assignment_active",
            new=AsyncMock(return_value=True),
        ):
            with TestClient(app) as client:
                resp = client.post(
                    f"/requests/{req.request_id}/voucher-pdf",
                    headers={"Authorization": "Bearer dummy"},
                )

        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "independent review" in detail.lower() or "not completed" in detail.lower()

    @pytest.mark.parametrize(
        "bad_status",
        [
            RequestStatus.QUEUED,
            RequestStatus.PROCESSING,
            RequestStatus.READY_FOR_REVIEW,
            RequestStatus.EXCEPTION,
            RequestStatus.SENT_TO_CLIENT,
            RequestStatus.REJECTED,
        ],
    )
    def test_all_non_amiga_reviewed_statuses_blocked(self, bad_status: RequestStatus):
        """Any status other than AMIGA_REVIEWED is rejected with 400."""
        user = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(status=bad_status)
        mock_session = _MockSession([_scalar_result(req)])
        app = _build_app(mock_session, user)

        with patch(
            "app.routes.voucher.user_repository.is_assignment_active",
            new=AsyncMock(return_value=True),
        ):
            with TestClient(app) as client:
                resp = client.post(
                    f"/requests/{req.request_id}/voucher-pdf",
                    headers={"Authorization": "Bearer dummy"},
                )

        assert resp.status_code == 400


class TestGenerationSuccess:
    """28.3: Valid AMIGA_REVIEWED request → 201, VoucherPDF row, VOUCHER_GENERATED AuditEvent."""

    def test_generation_success(self):
        """
        AMIGA_REVIEWED request → 201, VoucherPDF persisted, AuditEvent written.
        """
        user = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(status=RequestStatus.AMIGA_REVIEWED)
        template = _make_template()
        draft = _make_draft(req.request_id)
        header = _make_header(draft.draft_id)
        line_item = _make_line_item(draft.draft_id)
        payment = _make_payment_details(draft.draft_id)

        # DB execute() calls in order:
        # 1. select(InvoiceRequest) → req
        # 2. select(VoucherTemplate) via load_active_template → template
        # 3. select(Draft) → draft
        # 4. select(HeaderFields) → header
        # 5. select(LineItem) → [line_item]
        # 6. select(PaymentDetails) → payment
        # 7. select(TaxAssignment) → []
        mock_session = _MockSession(
            [
                _scalar_result(req),
                _scalar_result(template),
                _scalar_result(draft),
                _scalar_result(header),
                _scalars_all_result([line_item]),
                _scalar_result(payment),
                _scalars_all_result([]),  # no tax assignments
            ]
        )

        app = _build_app(mock_session, user)

        with patch(
            "app.routes.voucher.user_repository.is_assignment_active",
            new=AsyncMock(return_value=True),
        ):
            with patch("app.routes.voucher._html_to_pdf", return_value=b"%PDF-1.4 fake"):
                with patch(
                    "app.routes.voucher.file_store.upload",
                    new=AsyncMock(return_value=None),
                ):
                    with TestClient(app) as client:
                        resp = client.post(
                            f"/requests/{req.request_id}/voucher-pdf",
                            headers={"Authorization": "Bearer dummy"},
                        )

        assert resp.status_code == 201
        body = resp.json()
        assert "voucher_pdf_id" in body
        assert "file_key" in body
        assert "generated_at" in body
        assert body["file_key"].startswith(f"vouchers/{req.request_id}/")
        assert body["file_key"].endswith(".pdf")

        # VoucherPDF row and AuditEvent and TelemetryRecord were added
        added_types = {type(obj).__name__ for obj in mock_session.added}
        assert "VoucherPDF" in added_types
        assert "AuditEvent" in added_types
        assert "TelemetryRecord" in added_types

        # Session was committed
        assert mock_session.committed is True

    def test_audit_event_type_is_voucher_generated(self):
        """The AuditEvent added must have type VOUCHER_GENERATED."""
        user = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(status=RequestStatus.AMIGA_REVIEWED)
        template = _make_template()
        draft = _make_draft(req.request_id)
        header = _make_header(draft.draft_id)
        line_item = _make_line_item(draft.draft_id)
        payment = _make_payment_details(draft.draft_id)

        mock_session = _MockSession(
            [
                _scalar_result(req),
                _scalar_result(template),
                _scalar_result(draft),
                _scalar_result(header),
                _scalars_all_result([line_item]),
                _scalar_result(payment),
                _scalars_all_result([]),
            ]
        )
        app = _build_app(mock_session, user)

        with patch(
            "app.routes.voucher.user_repository.is_assignment_active",
            new=AsyncMock(return_value=True),
        ):
            with patch("app.routes.voucher._html_to_pdf", return_value=b"%PDF fake"):
                with patch(
                    "app.routes.voucher.file_store.upload",
                    new=AsyncMock(return_value=None),
                ):
                    with TestClient(app) as client:
                        resp = client.post(
                            f"/requests/{req.request_id}/voucher-pdf",
                            headers={"Authorization": "Bearer dummy"},
                        )

        assert resp.status_code == 201
        audit_events = [obj for obj in mock_session.added if isinstance(obj, AuditEvent)]
        assert len(audit_events) == 1
        assert audit_events[0].event_type == AuditEventType.VOUCHER_GENERATED


class TestGenerationFailureNoAuditEvent:
    """28.3: If write_pdf raises, return 500, no AuditEvent row inserted."""

    def test_generation_failure_no_audit_event(self):
        """
        When weasyprint.HTML(...).write_pdf() raises, the endpoint returns 500
        and NO AuditEvent is written to the session.
        """
        user = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(status=RequestStatus.AMIGA_REVIEWED)
        template = _make_template()
        draft = _make_draft(req.request_id)
        header = _make_header(draft.draft_id)
        line_item = _make_line_item(draft.draft_id)
        payment = _make_payment_details(draft.draft_id)

        mock_session = _MockSession(
            [
                _scalar_result(req),
                _scalar_result(template),
                _scalar_result(draft),
                _scalar_result(header),
                _scalars_all_result([line_item]),
                _scalar_result(payment),
                _scalars_all_result([]),
            ]
        )
        app = _build_app(mock_session, user)

        with patch(
            "app.routes.voucher.user_repository.is_assignment_active",
            new=AsyncMock(return_value=True),
        ):
            with patch(
                "app.routes.voucher._html_to_pdf",
                side_effect=RuntimeError("PDF engine failure"),
            ):
                with TestClient(app, raise_server_exceptions=False) as client:
                    resp = client.post(
                        f"/requests/{req.request_id}/voucher-pdf",
                        headers={"Authorization": "Bearer dummy"},
                    )

        assert resp.status_code == 500
        assert "Voucher generation failed" in resp.json()["detail"]

        # No AuditEvent must have been added
        audit_events = [obj for obj in mock_session.added if isinstance(obj, AuditEvent)]
        assert len(audit_events) == 0

        # Session must have been rolled back
        assert mock_session.rolled_back is True


class TestDisclaimerTextInRenderedHtml:
    """28.3: AUTHORIZATION_DISCLAIMER appears in the rendered HTML passed to WeasyPrint."""

    def test_disclaimer_text_present_in_rendered_html(self):
        """
        Mock WeasyPrint, capture the rendered_html string passed to
        weasyprint.HTML(string=...) and assert settings.AUTHORIZATION_DISCLAIMER
        is present in it.
        """
        user = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(status=RequestStatus.AMIGA_REVIEWED)

        # Use a template that includes the authorization_disclaimer placeholder
        template = VoucherTemplate(
            template_id=uuid.uuid4(),
            version="v1.0",
            template_content=(
                "<html><body>"
                "{{ vendor_name }}"
                "{% for item in line_items_table %}{{ item.description }}{% endfor %}"
                "{% for row in tax_summary_table %}{{ row.tax_type }}{% endfor %}"
                "{{ authorization_disclaimer }}"
                "</body></html>"
            ),
            is_active=True,
            created_by=None,
            created_at=datetime.now(timezone.utc),
        )

        draft = _make_draft(req.request_id)
        header = _make_header(draft.draft_id)
        line_item = _make_line_item(draft.draft_id)
        payment = _make_payment_details(draft.draft_id)

        mock_session = _MockSession(
            [
                _scalar_result(req),
                _scalar_result(template),
                _scalar_result(draft),
                _scalar_result(header),
                _scalars_all_result([line_item]),
                _scalar_result(payment),
                _scalars_all_result([]),
            ]
        )
        app = _build_app(mock_session, user)

        captured_html: list[str] = []

        def _capture_and_mock_html_to_pdf(html_string: str) -> bytes:
            """Capture the rendered HTML and return fake PDF bytes."""
            captured_html.append(html_string)
            return b"%PDF fake"

        with patch(
            "app.routes.voucher.user_repository.is_assignment_active",
            new=AsyncMock(return_value=True),
        ):
            with patch(
                "app.routes.voucher._html_to_pdf",
                side_effect=_capture_and_mock_html_to_pdf,
            ):
                with patch(
                    "app.routes.voucher.file_store.upload",
                    new=AsyncMock(return_value=None),
                ):
                    with TestClient(app) as client:
                        resp = client.post(
                            f"/requests/{req.request_id}/voucher-pdf",
                            headers={"Authorization": "Bearer dummy"},
                        )

        assert resp.status_code == 201, f"Expected 201 but got {resp.status_code}: {resp.text}"
        assert len(captured_html) == 1, "_html_to_pdf should have been called once"
        rendered = captured_html[0]
        assert settings.AUTHORIZATION_DISCLAIMER in rendered, (
            f"Expected disclaimer in rendered HTML.\n"
            f"Disclaimer: {settings.AUTHORIZATION_DISCLAIMER!r}\n"
            f"Rendered HTML (first 500 chars): {rendered[:500]!r}"
        )


class TestRoleGuard:
    """Non-CLIENT_PIC roles are rejected with 403."""

    @pytest.mark.parametrize(
        "role",
        [
            UserRole.FINANCE_REVIEWER,
            UserRole.SYSTEM_ADMIN,
            UserRole.INTAKE_SUPPORT,
            UserRole.SERVICE_LEAD,
        ],
    )
    def test_non_client_pic_gets_403(self, role: UserRole):
        user = _make_user(role)
        req = _make_request(status=RequestStatus.AMIGA_REVIEWED)
        mock_session = _MockSession([_scalar_result(req)])
        app = _build_app(mock_session, user)

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                f"/requests/{req.request_id}/voucher-pdf",
                headers={"Authorization": "Bearer dummy"},
            )
        assert resp.status_code == 403


class TestClientAssignmentGuard:
    """Users without active ClientAssignment are rejected with 403."""

    def test_no_assignment_returns_403(self):
        user = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(status=RequestStatus.AMIGA_REVIEWED)
        mock_session = _MockSession([_scalar_result(req)])
        app = _build_app(mock_session, user)

        with patch(
            "app.routes.voucher.user_repository.is_assignment_active",
            new=AsyncMock(return_value=False),
        ):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    f"/requests/{req.request_id}/voucher-pdf",
                    headers={"Authorization": "Bearer dummy"},
                )
        assert resp.status_code == 403
