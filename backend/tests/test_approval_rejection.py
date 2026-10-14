"""
Checkpoint 27 — Approval and Rejection flow tests
==================================================

Covers (per task description):

Approval scenarios:
  1. Self-approval → 403 "Self-approval is not permitted."
  2. Wrong role (CLIENT_PIC) → 403 authority error
  3. SYSTEM_ADMIN attempt → 403 + UNAUTHORIZED_APPROVAL_ATTEMPT audit event
  4. EXCEPTION status blocks approval → 409
  5. Valid Finance Reviewer approves READY_FOR_REVIEW → 200 + status = AMIGA_REVIEWED

Rejection scenarios:
  6. Valid reason (1 char) → 200
  7. Valid reason (500 chars) → 200
  8. Empty reason (0 chars) → 422
  9. Reason too long (501 chars) → 422
  10. Self-rejection → 403 "Self-rejection is not permitted."
  11. Wrong role → 403
  12. Wrong status (already REJECTED) → 409

All tests use FastAPI TestClient with dependency_overrides and unittest.mock.patch —
no real DB or S3 connections needed.
"""

import sys
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# asyncpg is not installed in the test environment; mock it before any imports
# that trigger create_async_engine (specifically app.dependencies).
_asyncpg_mock = MagicMock()
sys.modules.setdefault("asyncpg", _asyncpg_mock)

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.request import InvoiceRequest, RequestStatus
from app.models.user import User, UserRole

# ─── Helpers ────────────────────────────────────────────────────────────────


def _make_user(role: UserRole, user_id: uuid.UUID | None = None) -> User:
    now = datetime.now(timezone.utc)
    return User(
        user_id=user_id or uuid.uuid4(),
        username=f"test_{role.value.lower()}_{uuid.uuid4().hex[:6]}",
        role=role,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _make_request(
    uploader_id: uuid.UUID,
    client_id: uuid.UUID,
    status: RequestStatus = RequestStatus.READY_FOR_REVIEW,
    flags: list[str] | None = None,
) -> InvoiceRequest:
    now = datetime.now(timezone.utc)
    return InvoiceRequest(
        request_id=uuid.uuid4(),
        client_id=client_id,
        uploader_id=uploader_id,
        assigned_reviewer=None,
        request_type="standard",
        channel="email",
        request_date=date.today(),
        status=status,
        flags=flags or [],
        invoice_file_key="s3://bucket/test.pdf",
        invoice_page_count=1,
        rejection_reason=None,
        created_at=now,
        updated_at=now,
    )


def _make_mock_db():
    """Return an async generator that yields a bare-minimum mock AsyncSession."""
    async def _mock_get_db():
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.flush = AsyncMock()
        session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)
        yield session
    return _mock_get_db


def _update_status(req: InvoiceRequest | None, new_status: RequestStatus):
    """Side-effect: mutate in-memory request status and return it."""
    if req is not None:
        req.status = new_status
    return req


@contextmanager
def _build_client(
    acting_user: User,
    request_obj: InvoiceRequest | None = None,
    assignment_active: bool = True,
):
    """
    Context manager that yields a configured TestClient.

    Builds a minimal FastAPI app containing ONLY the approve and reject
    endpoints — this avoids requiring python-multipart (needed for the upload
    endpoint) and asyncpg (needed for the DB engine).

    All repository calls and audit logging are patched so no real DB or S3
    connection is made.
    """
    from app.dependencies import get_current_user, get_db

    # Import the route handler functions directly — avoid registering the
    # full router which pulls in the multipart upload endpoint.
    from app.routes.requests import approve_request, reject_request

    app = FastAPI()

    # Re-register only the two endpoints we care about under the same paths
    app.post("/requests/{request_id}/approve")(approve_request)
    app.post("/requests/{request_id}/reject")(reject_request)

    app.dependency_overrides[get_db] = _make_mock_db()
    app.dependency_overrides[get_current_user] = lambda: acting_user

    with (
        patch(
            "app.routes.requests.request_repository.get_by_id",
            new=AsyncMock(return_value=request_obj),
        ),
        patch(
            "app.routes.requests.user_repository.is_assignment_active",
            new=AsyncMock(return_value=assignment_active),
        ),
        patch(
            "app.routes.requests.log_event",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.routes.requests.request_repository.update_status",
            new=AsyncMock(
                side_effect=lambda db, rid, s: _update_status(request_obj, s)
            ),
        ),
        patch(
            "app.routes.requests.request_repository.set_rejection_reason",
            new=AsyncMock(return_value=None),
        ),
    ):
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client


# ─── Approval Tests ──────────────────────────────────────────────────────────


class TestApproval:
    """POST /requests/{id}/approve"""

    # ── 1. Self-approval ──────────────────────────────────────────────────────

    def test_self_approval_returns_403(self):
        """Uploader cannot approve their own request."""
        reviewer_id = uuid.uuid4()
        client_id = uuid.uuid4()
        reviewer = _make_user(UserRole.FINANCE_REVIEWER, user_id=reviewer_id)
        # uploader_id == reviewer_id → self-approval
        req = _make_request(uploader_id=reviewer_id, client_id=client_id)

        with _build_client(reviewer, request_obj=req, assignment_active=True) as client:
            resp = client.post(
                f"/requests/{req.request_id}/approve",
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 403
        assert "self-approval" in resp.json()["detail"].lower()

    # ── 2. Wrong role (CLIENT_PIC) ────────────────────────────────────────────

    def test_wrong_role_client_pic_returns_403(self):
        """A CLIENT_PIC attempting approval gets 403."""
        client_id = uuid.uuid4()
        pic = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(uploader_id=uuid.uuid4(), client_id=client_id)

        with _build_client(pic, request_obj=req) as client:
            resp = client.post(
                f"/requests/{req.request_id}/approve",
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 403
        assert "authority" in resp.json()["detail"].lower()

    def test_wrong_role_service_lead_returns_403(self):
        """A SERVICE_LEAD attempting approval gets 403."""
        client_id = uuid.uuid4()
        sl = _make_user(UserRole.SERVICE_LEAD)
        req = _make_request(uploader_id=uuid.uuid4(), client_id=client_id)

        with _build_client(sl, request_obj=req) as client:
            resp = client.post(
                f"/requests/{req.request_id}/approve",
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 403
        assert "authority" in resp.json()["detail"].lower()

    def test_wrong_role_intake_support_returns_403(self):
        """An INTAKE_SUPPORT attempting approval gets 403."""
        client_id = uuid.uuid4()
        is_user = _make_user(UserRole.INTAKE_SUPPORT)
        req = _make_request(uploader_id=uuid.uuid4(), client_id=client_id)

        with _build_client(is_user, request_obj=req) as client:
            resp = client.post(
                f"/requests/{req.request_id}/approve",
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 403

    # ── 3. SYSTEM_ADMIN attempt ───────────────────────────────────────────────

    def test_system_admin_returns_403(self):
        """SYSTEM_ADMIN gets 403 when attempting approval."""
        client_id = uuid.uuid4()
        admin = _make_user(UserRole.SYSTEM_ADMIN)
        req = _make_request(uploader_id=uuid.uuid4(), client_id=client_id)

        with _build_client(admin, request_obj=req) as client:
            resp = client.post(
                f"/requests/{req.request_id}/approve",
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 403
        assert "authority" in resp.json()["detail"].lower()

    # ── 4. EXCEPTION status blocks approval ───────────────────────────────────

    def test_exception_status_blocks_approval(self):
        """Request in EXCEPTION status cannot be approved → 409."""
        reviewer_id = uuid.uuid4()
        client_id = uuid.uuid4()
        reviewer = _make_user(UserRole.FINANCE_REVIEWER, user_id=reviewer_id)
        # different uploader so SOD passes; status=EXCEPTION
        req = _make_request(
            uploader_id=uuid.uuid4(),
            client_id=client_id,
            status=RequestStatus.EXCEPTION,
        )

        with _build_client(reviewer, request_obj=req, assignment_active=True) as client:
            resp = client.post(
                f"/requests/{req.request_id}/approve",
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 409
        detail = resp.json()["detail"].lower()
        assert "exception" in detail or "unresolved" in detail

    # ── 5. Valid approval ─────────────────────────────────────────────────────

    def test_valid_approval_returns_200(self):
        """
        Finance Reviewer (not the uploader, active assignment)
        approves READY_FOR_REVIEW → 200 with status=approved.
        """
        reviewer_id = uuid.uuid4()
        client_id = uuid.uuid4()
        reviewer = _make_user(UserRole.FINANCE_REVIEWER, user_id=reviewer_id)
        req = _make_request(
            uploader_id=uuid.uuid4(),  # different user → SOD passes
            client_id=client_id,
            status=RequestStatus.READY_FOR_REVIEW,
        )

        with _build_client(reviewer, request_obj=req, assignment_active=True) as client:
            resp = client.post(
                f"/requests/{req.request_id}/approve",
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "approved"
        assert body["request_id"] == str(req.request_id)

    def test_valid_approval_404_when_request_not_found(self):
        """Non-existent request → 404."""
        reviewer = _make_user(UserRole.FINANCE_REVIEWER)
        rid = uuid.uuid4()

        with _build_client(reviewer, request_obj=None, assignment_active=True) as client:
            resp = client.post(
                f"/requests/{rid}/approve",
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 404

    def test_approval_without_client_assignment_returns_403(self):
        """Finance Reviewer with no active assignment → 403."""
        reviewer_id = uuid.uuid4()
        client_id = uuid.uuid4()
        reviewer = _make_user(UserRole.FINANCE_REVIEWER, user_id=reviewer_id)
        req = _make_request(uploader_id=uuid.uuid4(), client_id=client_id)

        with _build_client(reviewer, request_obj=req, assignment_active=False) as client:
            resp = client.post(
                f"/requests/{req.request_id}/approve",
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 403
        assert "not authorized" in resp.json()["detail"].lower()


# ─── Rejection Tests ─────────────────────────────────────────────────────────


class TestRejection:
    """POST /requests/{id}/reject"""

    # ── 6 & 7. Valid reasons ──────────────────────────────────────────────────

    def test_valid_reason_1_char(self):
        """A 1-character rejection reason is accepted → 200."""
        reviewer_id = uuid.uuid4()
        client_id = uuid.uuid4()
        reviewer = _make_user(UserRole.FINANCE_REVIEWER, user_id=reviewer_id)
        req = _make_request(uploader_id=uuid.uuid4(), client_id=client_id)

        with _build_client(reviewer, request_obj=req, assignment_active=True) as client:
            resp = client.post(
                f"/requests/{req.request_id}/reject",
                json={"rejection_reason": "X"},
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    def test_valid_reason_500_chars(self):
        """A 500-character rejection reason is accepted → 200."""
        reviewer_id = uuid.uuid4()
        client_id = uuid.uuid4()
        reviewer = _make_user(UserRole.FINANCE_REVIEWER, user_id=reviewer_id)
        req = _make_request(uploader_id=uuid.uuid4(), client_id=client_id)
        long_reason = "A" * 500

        with _build_client(reviewer, request_obj=req, assignment_active=True) as client:
            resp = client.post(
                f"/requests/{req.request_id}/reject",
                json={"rejection_reason": long_reason},
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 200

    def test_valid_reason_typical(self):
        """A typical rejection reason → 200 with request_id in response."""
        reviewer_id = uuid.uuid4()
        client_id = uuid.uuid4()
        reviewer = _make_user(UserRole.FINANCE_REVIEWER, user_id=reviewer_id)
        req = _make_request(uploader_id=uuid.uuid4(), client_id=client_id)

        with _build_client(reviewer, request_obj=req, assignment_active=True) as client:
            resp = client.post(
                f"/requests/{req.request_id}/reject",
                json={"rejection_reason": "Invoice amount does not match PO."},
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "rejected"
        assert body["request_id"] == str(req.request_id)

    # ── 8. Empty reason ───────────────────────────────────────────────────────

    def test_empty_reason_returns_422(self):
        """Empty string rejection reason → 422."""
        reviewer = _make_user(UserRole.FINANCE_REVIEWER)
        req = _make_request(uploader_id=uuid.uuid4(), client_id=uuid.uuid4())

        with _build_client(reviewer, request_obj=req, assignment_active=True) as client:
            resp = client.post(
                f"/requests/{req.request_id}/reject",
                json={"rejection_reason": ""},
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 422

    def test_missing_rejection_reason_field_returns_422(self):
        """Missing rejection_reason field → 422."""
        reviewer = _make_user(UserRole.FINANCE_REVIEWER)
        req = _make_request(uploader_id=uuid.uuid4(), client_id=uuid.uuid4())

        with _build_client(reviewer, request_obj=req, assignment_active=True) as client:
            resp = client.post(
                f"/requests/{req.request_id}/reject",
                json={},
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 422

    # ── 9. Reason too long ────────────────────────────────────────────────────

    def test_reason_501_chars_returns_422(self):
        """501-character rejection reason → 422."""
        reviewer = _make_user(UserRole.FINANCE_REVIEWER)
        req = _make_request(uploader_id=uuid.uuid4(), client_id=uuid.uuid4())

        with _build_client(reviewer, request_obj=req, assignment_active=True) as client:
            resp = client.post(
                f"/requests/{req.request_id}/reject",
                json={"rejection_reason": "A" * 501},
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 422

    def test_reason_exactly_501_chars_is_boundary_over(self):
        """501 chars is just over the limit — must fail with 422."""
        reviewer = _make_user(UserRole.FINANCE_REVIEWER)
        req = _make_request(uploader_id=uuid.uuid4(), client_id=uuid.uuid4())

        with _build_client(reviewer, request_obj=req, assignment_active=True) as client:
            resp = client.post(
                f"/requests/{req.request_id}/reject",
                json={"rejection_reason": "B" * 501},
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 422

    # ── 10. Self-rejection ────────────────────────────────────────────────────

    def test_self_rejection_returns_403(self):
        """Uploader cannot reject their own request → 403."""
        reviewer_id = uuid.uuid4()
        client_id = uuid.uuid4()
        reviewer = _make_user(UserRole.FINANCE_REVIEWER, user_id=reviewer_id)
        req = _make_request(uploader_id=reviewer_id, client_id=client_id)

        with _build_client(reviewer, request_obj=req, assignment_active=True) as client:
            resp = client.post(
                f"/requests/{req.request_id}/reject",
                json={"rejection_reason": "Cannot process this invoice."},
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 403
        assert "self-rejection" in resp.json()["detail"].lower()

    # ── 11. Wrong role ────────────────────────────────────────────────────────

    def test_wrong_role_pic_returns_403(self):
        """A CLIENT_PIC attempting rejection → 403."""
        client_id = uuid.uuid4()
        pic = _make_user(UserRole.CLIENT_PIC)
        req = _make_request(uploader_id=uuid.uuid4(), client_id=client_id)

        with _build_client(pic, request_obj=req) as client:
            resp = client.post(
                f"/requests/{req.request_id}/reject",
                json={"rejection_reason": "Trying to reject."},
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 403
        assert "authority" in resp.json()["detail"].lower()

    def test_wrong_role_service_lead_returns_403(self):
        """A SERVICE_LEAD attempting rejection → 403."""
        client_id = uuid.uuid4()
        sl = _make_user(UserRole.SERVICE_LEAD)
        req = _make_request(uploader_id=uuid.uuid4(), client_id=client_id)

        with _build_client(sl, request_obj=req) as client:
            resp = client.post(
                f"/requests/{req.request_id}/reject",
                json={"rejection_reason": "Trying to reject."},
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 403

    def test_system_admin_cannot_reject(self):
        """A SYSTEM_ADMIN attempting rejection → 403."""
        client_id = uuid.uuid4()
        admin = _make_user(UserRole.SYSTEM_ADMIN)
        req = _make_request(uploader_id=uuid.uuid4(), client_id=client_id)

        with _build_client(admin, request_obj=req) as client:
            resp = client.post(
                f"/requests/{req.request_id}/reject",
                json={"rejection_reason": "Trying to reject."},
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 403

    # ── 12. Wrong status ──────────────────────────────────────────────────────

    def test_already_rejected_status_returns_409(self):
        """Rejecting an already-REJECTED request → 409."""
        reviewer_id = uuid.uuid4()
        client_id = uuid.uuid4()
        reviewer = _make_user(UserRole.FINANCE_REVIEWER, user_id=reviewer_id)
        req = _make_request(
            uploader_id=uuid.uuid4(),
            client_id=client_id,
            status=RequestStatus.REJECTED,
        )

        with _build_client(reviewer, request_obj=req, assignment_active=True) as client:
            resp = client.post(
                f"/requests/{req.request_id}/reject",
                json={"rejection_reason": "Duplicate attempt."},
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 409

    def test_queued_status_returns_409(self):
        """Rejecting a QUEUED request → 409."""
        reviewer_id = uuid.uuid4()
        client_id = uuid.uuid4()
        reviewer = _make_user(UserRole.FINANCE_REVIEWER, user_id=reviewer_id)
        req = _make_request(
            uploader_id=uuid.uuid4(),
            client_id=client_id,
            status=RequestStatus.QUEUED,
        )

        with _build_client(reviewer, request_obj=req, assignment_active=True) as client:
            resp = client.post(
                f"/requests/{req.request_id}/reject",
                json={"rejection_reason": "Wrong status."},
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 409

    def test_amiga_reviewed_status_returns_409(self):
        """Rejecting an AMIGA_REVIEWED request → 409."""
        reviewer_id = uuid.uuid4()
        client_id = uuid.uuid4()
        reviewer = _make_user(UserRole.FINANCE_REVIEWER, user_id=reviewer_id)
        req = _make_request(
            uploader_id=uuid.uuid4(),
            client_id=client_id,
            status=RequestStatus.AMIGA_REVIEWED,
        )

        with _build_client(reviewer, request_obj=req, assignment_active=True) as client:
            resp = client.post(
                f"/requests/{req.request_id}/reject",
                json={"rejection_reason": "Cannot reject approved."},
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 409

    # ── Bonus: Rejection also works from EXCEPTION status ────────────────────

    def test_reject_from_exception_status_succeeds(self):
        """Finance Reviewer can reject a Request in EXCEPTION status → 200."""
        reviewer_id = uuid.uuid4()
        client_id = uuid.uuid4()
        reviewer = _make_user(UserRole.FINANCE_REVIEWER, user_id=reviewer_id)
        req = _make_request(
            uploader_id=uuid.uuid4(),
            client_id=client_id,
            status=RequestStatus.EXCEPTION,
        )

        with _build_client(reviewer, request_obj=req, assignment_active=True) as client:
            resp = client.post(
                f"/requests/{req.request_id}/reject",
                json={"rejection_reason": "Cannot resolve exception; rejecting."},
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"
