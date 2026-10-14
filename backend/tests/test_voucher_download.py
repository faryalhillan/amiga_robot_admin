# backend/tests/test_voucher_download.py
"""
Tests for Task 30 — GET /requests/{id}/voucher-pdf (download and SENT_TO_CLIENT transition)

Covers:
  - 30.1: Endpoint implementation (role guard, assignment guard, status guard,
            PDF fetch, idempotency, audit events, status transition)
  - 30.2: Authorization guards
  - 30.3: pytest tests as specified

Requirements: 16.1, 16.2, 16.3, 16.4, 16.5
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.audit import AuditEvent, AuditEventType
from app.models.request import InvoiceRequest, RequestStatus
from app.models.user import User, UserRole
from app.models.voucher import VoucherPDF
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


def _make_voucher_pdf(request_id: uuid.UUID, generated_by: uuid.UUID) -> VoucherPDF:
    return VoucherPDF(
        voucher_pdf_id=uuid.uuid4(),
        request_id=request_id,
        file_key=f"vouchers/{request_id}/test.pdf",
        generated_at=datetime.now(timezone.utc),
        generated_by=generated_by,
        disclaimer_hash="abc123",
        template_version="v1.0",
        template_hash="def456",
    )


# ─── Mock DB session factory ──────────────────────────────────────────────────


class _MockSession:
    """
    A configurable mock AsyncSession. Each call to execute() pops the next
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
        mock_result.scalar.return_value = None
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
    r.scalar.return_value = None
    return r


def _scalar_count_result(count: int):
    """Build a mock result whose .scalar() returns a count (for idempotency check)."""
    r = MagicMock()
    r.scalar.return_value = count if count > 0 else None
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


class TestStatusGuardBlocked:
    """30.2 / 30.3: Request not in AMIGA_REVIEWED or SENT_TO_CLIENT → 400 with message."""

    def test_ready_for_review_status_blocked(self):
        """
        GET to the endpoint when request.status == READY_FOR_REVIEW → 400
        with a message stating voucher is not yet available.
        """
        user = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(status=RequestStatus.READY_FOR_REVIEW)

        mock_session = _MockSession([_scalar_result(req)])

        app = _build_app(mock_session, user)

        with patch(
            "app.routes.voucher.user_repository.is_assignment_active",
            new=AsyncMock(return_value=True),
        ):
            with TestClient(app) as client:
                resp = client.get(
                    f"/requests/{req.request_id}/voucher-pdf",
                    headers={"Authorization": "Bearer dummy"},
                )

        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "not yet available" in detail.lower() or "independent review" in detail.lower()

    @pytest.mark.parametrize(
        "bad_status",
        [
            RequestStatus.QUEUED,
            RequestStatus.PROCESSING,
            RequestStatus.READY_FOR_REVIEW,
            RequestStatus.EXCEPTION,
            RequestStatus.REJECTED,
        ],
    )
    def test_all_non_downloadable_statuses_blocked(self, bad_status: RequestStatus):
        """Any status other than AMIGA_REVIEWED or SENT_TO_CLIENT is rejected with 400."""
        user = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(status=bad_status)
        mock_session = _MockSession([_scalar_result(req)])
        app = _build_app(mock_session, user)

        with patch(
            "app.routes.voucher.user_repository.is_assignment_active",
            new=AsyncMock(return_value=True),
        ):
            with TestClient(app) as client:
                resp = client.get(
                    f"/requests/{req.request_id}/voucher-pdf",
                    headers={"Authorization": "Bearer dummy"},
                )

        assert resp.status_code == 400


class TestMissingAssignmentBlocked:
    """30.2 / 30.3: No active ClientAssignment → 403 with no client data."""

    def test_missing_assignment_blocked(self):
        """
        GET to the endpoint when user has no active ClientAssignment for the client → 403
        """
        user = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(status=RequestStatus.AMIGA_REVIEWED)

        mock_session = _MockSession([_scalar_result(req)])
        app = _build_app(mock_session, user)

        with patch(
            "app.routes.voucher.user_repository.is_assignment_active",
            new=AsyncMock(return_value=False),
        ):
            with TestClient(app) as client:
                resp = client.get(
                    f"/requests/{req.request_id}/voucher-pdf",
                    headers={"Authorization": "Bearer dummy"},
                )

        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert "not authorized" in detail.lower() or "client" in detail.lower()
        # Ensure no client data is leaked
        assert req.client_id.hex not in str(resp.json())


class TestFirstDownloadTransition:
    """30.1 / 30.3: First download transitions to SENT_TO_CLIENT with audit events."""

    def test_first_download_triggers_sent_to_client_transition(self):
        """
        GET to endpoint when request.status == AMIGA_REVIEWED → 200, PDF streamed,
        VOUCHER_DOWNLOADED and STATUS_CHANGED events written, status → SENT_TO_CLIENT.
        """
        user = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(status=RequestStatus.AMIGA_REVIEWED)
        voucher_pdf = _make_voucher_pdf(req.request_id, user.user_id)

        # DB execute() calls in order:
        # 1. select(InvoiceRequest) → req
        # 2. select().where(status == SENT_TO_CLIENT) for idempotency → None
        # 3. select(VoucherPDF) → voucher_pdf
        mock_session = _MockSession(
            [
                _scalar_result(req),
                _empty_result(),  # No prior SENT_TO_CLIENT event
                _scalar_result(voucher_pdf),
            ]
        )

        app = _build_app(mock_session, user)

        with patch(
            "app.routes.voucher.user_repository.is_assignment_active",
            new=AsyncMock(return_value=True),
        ):
            with patch(
                "app.routes.voucher.file_store.download",
                new=AsyncMock(return_value=b"%PDF-1.4 fake"),
            ):
                with TestClient(app) as client:
                    resp = client.get(
                        f"/requests/{req.request_id}/voucher-pdf",
                        headers={"Authorization": "Bearer dummy"},
                    )

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content == b"%PDF-1.4 fake"

        # Verify request status was transitioned to SENT_TO_CLIENT
        assert req.status == RequestStatus.SENT_TO_CLIENT

        # Verify VOUCHER_DOWNLOADED and STATUS_CHANGED events were written
        audit_events = [obj for obj in mock_session.added if isinstance(obj, AuditEvent)]
        assert len(audit_events) == 2
        event_types = [e.event_type for e in audit_events]
        assert AuditEventType.VOUCHER_DOWNLOADED in event_types
        assert AuditEventType.STATUS_CHANGED in event_types

        # Verify session was committed
        assert mock_session.committed is True

    def test_first_download_audit_event_contains_metadata(self):
        """Verify VOUCHER_DOWNLOADED event contains correct metadata."""
        user = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(status=RequestStatus.AMIGA_REVIEWED)
        voucher_pdf = _make_voucher_pdf(req.request_id, user.user_id)

        mock_session = _MockSession(
            [
                _scalar_result(req),
                _empty_result(),
                _scalar_result(voucher_pdf),
            ]
        )
        app = _build_app(mock_session, user)

        with patch(
            "app.routes.voucher.user_repository.is_assignment_active",
            new=AsyncMock(return_value=True),
        ):
            with patch(
                "app.routes.voucher.file_store.download",
                new=AsyncMock(return_value=b"%PDF-1.4 fake"),
            ):
                with TestClient(app) as client:
                    resp = client.get(
                        f"/requests/{req.request_id}/voucher-pdf",
                        headers={"Authorization": "Bearer dummy"},
                    )

        assert resp.status_code == 200

        # Find VOUCHER_DOWNLOADED event
        audit_events = [obj for obj in mock_session.added if isinstance(obj, AuditEvent)]
        vd_event = [e for e in audit_events if e.event_type == AuditEventType.VOUCHER_DOWNLOADED]
        assert len(vd_event) == 1
        assert vd_event[0].request_id == req.request_id
        assert vd_event[0].actor_id == user.user_id
        assert "voucher_pdf_id" in vd_event[0].payload
        assert "file_key" in vd_event[0].payload

    def test_first_download_status_changed_event_contains_metadata(self):
        """Verify STATUS_CHANGED event contains correct old/new status."""
        user = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(status=RequestStatus.AMIGA_REVIEWED)
        voucher_pdf = _make_voucher_pdf(req.request_id, user.user_id)

        mock_session = _MockSession(
            [
                _scalar_result(req),
                _empty_result(),
                _scalar_result(voucher_pdf),
            ]
        )
        app = _build_app(mock_session, user)

        with patch(
            "app.routes.voucher.user_repository.is_assignment_active",
            new=AsyncMock(return_value=True),
        ):
            with patch(
                "app.routes.voucher.file_store.download",
                new=AsyncMock(return_value=b"%PDF-1.4 fake"),
            ):
                with TestClient(app) as client:
                    resp = client.get(
                        f"/requests/{req.request_id}/voucher-pdf",
                        headers={"Authorization": "Bearer dummy"},
                    )

        assert resp.status_code == 200

        # Find STATUS_CHANGED event
        audit_events = [obj for obj in mock_session.added if isinstance(obj, AuditEvent)]
        sc_event = [e for e in audit_events if e.event_type == AuditEventType.STATUS_CHANGED]
        assert len(sc_event) == 1
        assert sc_event[0].payload["old_status"] == RequestStatus.AMIGA_REVIEWED.value
        assert sc_event[0].payload["new_status"] == RequestStatus.SENT_TO_CLIENT.value


class TestSecondDownloadIdempotency:
    """30.1 / 30.3: Second download does NOT create duplicate SENT_TO_CLIENT event."""

    def test_second_download_no_duplicate_event(self):
        """
        GET to endpoint when request.status == SENT_TO_CLIENT → 200, PDF streamed,
        but no new VOUCHER_DOWNLOADED or STATUS_CHANGED events written.
        """
        user = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(status=RequestStatus.SENT_TO_CLIENT)
        voucher_pdf = _make_voucher_pdf(req.request_id, user.user_id)

        # DB execute() calls in order:
        # 1. select(InvoiceRequest) → req (already in SENT_TO_CLIENT)
        # 2. select(VoucherPDF) → voucher_pdf
        mock_session = _MockSession(
            [
                _scalar_result(req),
                _scalar_result(voucher_pdf),
            ]
        )

        app = _build_app(mock_session, user)

        with patch(
            "app.routes.voucher.user_repository.is_assignment_active",
            new=AsyncMock(return_value=True),
        ):
            with patch(
                "app.routes.voucher.file_store.download",
                new=AsyncMock(return_value=b"%PDF-1.4 fake"),
            ):
                with TestClient(app) as client:
                    resp = client.get(
                        f"/requests/{req.request_id}/voucher-pdf",
                        headers={"Authorization": "Bearer dummy"},
                    )

        assert resp.status_code == 200
        assert resp.content == b"%PDF-1.4 fake"

        # Verify NO audit events were added (idempotency)
        audit_events = [obj for obj in mock_session.added if isinstance(obj, AuditEvent)]
        assert len(audit_events) == 0

        # Verify request status remained SENT_TO_CLIENT
        assert req.status == RequestStatus.SENT_TO_CLIENT

        # Verify session was NOT committed (no transaction)
        assert mock_session.committed is False

    def test_multiple_downloads_all_return_same_pdf(self):
        """
        Simulate multiple consecutive downloads; all return the same PDF,
        and only the first one creates audit events.
        """
        user = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(status=RequestStatus.AMIGA_REVIEWED)
        voucher_pdf = _make_voucher_pdf(req.request_id, user.user_id)
        expected_pdf_bytes = b"%PDF-1.4 multi-download"

        # First download: AMIGA_REVIEWED → SENT_TO_CLIENT
        mock_session_1 = _MockSession(
            [
                _scalar_result(req),
                _empty_result(),
                _scalar_result(voucher_pdf),
            ]
        )
        app = _build_app(mock_session_1, user)

        with patch(
            "app.routes.voucher.user_repository.is_assignment_active",
            new=AsyncMock(return_value=True),
        ):
            with patch(
                "app.routes.voucher.file_store.download",
                new=AsyncMock(return_value=expected_pdf_bytes),
            ):
                with TestClient(app) as client:
                    resp1 = client.get(
                        f"/requests/{req.request_id}/voucher-pdf",
                        headers={"Authorization": "Bearer dummy"},
                    )

        assert resp1.status_code == 200
        assert resp1.content == expected_pdf_bytes
        assert req.status == RequestStatus.SENT_TO_CLIENT

        # Reset request object for second download (normally would be fresh from DB)
        req.status = RequestStatus.SENT_TO_CLIENT

        # Second download: still SENT_TO_CLIENT, no new events
        mock_session_2 = _MockSession(
            [
                _scalar_result(req),
                _scalar_result(voucher_pdf),
            ]
        )
        app2 = _build_app(mock_session_2, user)

        with patch(
            "app.routes.voucher.user_repository.is_assignment_active",
            new=AsyncMock(return_value=True),
        ):
            with patch(
                "app.routes.voucher.file_store.download",
                new=AsyncMock(return_value=expected_pdf_bytes),
            ):
                with TestClient(app2) as client:
                    resp2 = client.get(
                        f"/requests/{req.request_id}/voucher-pdf",
                        headers={"Authorization": "Bearer dummy"},
                    )

        assert resp2.status_code == 200
        assert resp2.content == expected_pdf_bytes
        audit_events = [obj for obj in mock_session_2.added if isinstance(obj, AuditEvent)]
        assert len(audit_events) == 0


class TestPdfNotFound:
    """30.1: If no VoucherPDF has been generated for request → 404."""

    def test_no_voucher_pdf_generated_yet(self):
        """
        GET to endpoint when no VoucherPDF row exists for the request → 404
        with message stating no PDF has been generated.
        """
        user = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(status=RequestStatus.AMIGA_REVIEWED)

        # DB execute() calls:
        # 1. select(InvoiceRequest) → req
        # 2. select(VoucherPDF) → None
        mock_session = _MockSession(
            [
                _scalar_result(req),
                _empty_result(),  # No VoucherPDF found
            ]
        )

        app = _build_app(mock_session, user)

        with patch(
            "app.routes.voucher.user_repository.is_assignment_active",
            new=AsyncMock(return_value=True),
        ):
            with TestClient(app) as client:
                resp = client.get(
                    f"/requests/{req.request_id}/voucher-pdf",
                    headers={"Authorization": "Bearer dummy"},
                )

        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert "no voucher pdf" in detail.lower() or "generated" in detail.lower()
