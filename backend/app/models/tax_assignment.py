import enum
import uuid
from datetime import datetime

from decimal import Decimal
from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class IndonesianTaxType(str, enum.Enum):
    """Indonesian tax types with their statutory rates."""
    PPH21 = "PPH21"
    PPH22 = "PPH22"
    PPH23 = "PPH23"
    PPH25 = "PPH25"
    PPN = "PPN"
    NO_TAX = "NO_TAX"


# Hardcoded Indonesian tax rates mapping
TAX_RATES: dict[IndonesianTaxType, Decimal] = {
    IndonesianTaxType.PPH21: Decimal("0.0500"),
    IndonesianTaxType.PPH22: Decimal("0.0150"),
    IndonesianTaxType.PPH23: Decimal("0.0200"),
    IndonesianTaxType.PPH25: Decimal("0.0200"),
    IndonesianTaxType.PPN: Decimal("0.1100"),
    IndonesianTaxType.NO_TAX: Decimal("0.0000"),
}


class TaxAssignment(Base):
    __tablename__ = "tax_assignments"

    tax_assignment_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    line_item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("line_items.line_item_id"), nullable=False
    )
    tax_type: Mapped[IndonesianTaxType] = mapped_column(
        SAEnum(IndonesianTaxType, name="indonesiantaxtype"), nullable=False
    )
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    assigned_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("line_item_id", name="uq_tax_assignment_per_line_item"),
    )
