# backend/app/models/tax_assignment.py
from __future__ import annotations

import enum
import uuid
from decimal import Decimal

from sqlalchemy import Enum as SAEnum, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base

# Hard-coded tax rates per Indonesian statute.
TAX_RATES: dict[str, Decimal] = {
    "PPH21": Decimal("0.0500"),
    "PPH22": Decimal("0.0150"),
    "PPH23": Decimal("0.0200"),
    "PPH25": Decimal("0.0200"),
    "PPN":   Decimal("0.1100"),
    "NO_TAX": Decimal("0.0000"),
}


class IndonesianTaxType(str, enum.Enum):
    PPH21 = "PPH21"
    PPH22 = "PPH22"
    PPH23 = "PPH23"
    PPH25 = "PPH25"
    PPN = "PPN"
    NO_TAX = "NO_TAX"


class TaxAssignment(Base):
    __tablename__ = "tax_assignments"

    assignment_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    line_item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("line_items.line_item_id"),
        unique=True,
        nullable=False,
    )
    tax_type: Mapped[str] = mapped_column(
        SAEnum(IndonesianTaxType, name="indonesiantaxtype"),
        nullable=False,
    )
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
