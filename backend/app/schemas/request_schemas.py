# backend/app/schemas/request_schemas.py

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.request import RequestStatus


class CreateRequestResponse(BaseModel):
    request_id: uuid.UUID
    status: RequestStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class RequestSummary(BaseModel):
    request_id: uuid.UUID
    client_id: uuid.UUID
    request_type: str
    channel: str
    request_date: date
    status: RequestStatus
    flags: list[str]
    invoice_page_count: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RequestDetail(BaseModel):
    """Full request detail — includes rejection_reason visible to authorized roles."""

    request_id: uuid.UUID
    client_id: uuid.UUID
    uploader_id: uuid.UUID
    assigned_reviewer: Optional[uuid.UUID]
    request_type: str
    channel: str
    request_date: date
    status: RequestStatus
    flags: list[str]
    invoice_page_count: Optional[int]
    rejection_reason: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RejectionRequest(BaseModel):
    """Request body for POST /requests/{id}/reject."""

    rejection_reason: str = Field(min_length=1, max_length=500)
