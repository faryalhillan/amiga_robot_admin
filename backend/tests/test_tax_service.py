# backend/tests/test_tax_service.py

from decimal import Decimal
import uuid
from datetime import datetime, timezone

import pytest

from app.models.invoice_fields import LineItem
from app.models.tax_assignment import IndonesianTaxType, TAX_RATES, TaxAssignment
from app.services.tax_service import compute_tax_amount, compute_tax_summary


class TestComputeTaxAmount:
    """Test the compute_tax_amount function with various tax types."""

    def test_compute_tax_pph21(self):
        """Test PPH21 (5%) tax computation."""
        line_total = Decimal("100.00")
        tax_amount = compute_tax_amount(line_total, IndonesianTaxType.PPH21)
        assert tax_amount == Decimal("5.00")
        assert isinstance(tax_amount, Decimal)

    def test_compute_tax_pph22(self):
        """Test PPH22 (1.5%) tax computation."""
        line_total = Decimal("1000.00")
        tax_amount = compute_tax_amount(line_total, IndonesianTaxType.PPH22)
        assert tax_amount == Decimal("15.00")
        assert isinstance(tax_amount, Decimal)

    def test_compute_tax_pph23(self):
        """Test PPH23 (2%) tax computation."""
        line_total = Decimal("500.00")
        tax_amount = compute_tax_amount(line_total, IndonesianTaxType.PPH23)
        assert tax_amount == Decimal("10.00")
        assert isinstance(tax_amount, Decimal)

    def test_compute_tax_pph25(self):
        """Test PPH25 (2%) tax computation."""
        line_total = Decimal("250.00")
        tax_amount = compute_tax_amount(line_total, IndonesianTaxType.PPH25)
        assert tax_amount == Decimal("5.00")
        assert isinstance(tax_amount, Decimal)

    def test_compute_tax_ppn(self):
        """Test PPN (11%) tax computation."""
        line_total = Decimal("1000.00")
        tax_amount = compute_tax_amount(line_total, IndonesianTaxType.PPN)
        assert tax_amount == Decimal("110.00")
        assert isinstance(tax_amount, Decimal)

    def test_compute_tax_no_tax(self):
        """Test NO_TAX (0%) computation."""
        line_total = Decimal("500.00")
        tax_amount = compute_tax_amount(line_total, IndonesianTaxType.NO_TAX)
        assert tax_amount == Decimal("0.00")
        assert isinstance(tax_amount, Decimal)

    def test_compute_tax_with_float_input(self):
        """Test that float inputs are converted to Decimal."""
        line_total = 100.50
        tax_amount = compute_tax_amount(line_total, IndonesianTaxType.PPH21)
        expected = Decimal("100.50") * Decimal("0.0500")
        assert tax_amount == expected
        assert isinstance(tax_amount, Decimal)

    def test_compute_tax_preserves_precision(self):
        """Test that Decimal precision is maintained (never uses float)."""
        line_total = Decimal("333.333")
        tax_amount = compute_tax_amount(line_total, IndonesianTaxType.PPH21)
        # Should be 333.333 * 0.05 = 16.66665
        expected = Decimal("333.333") * Decimal("0.0500")
        assert tax_amount == expected


class TestComputeTaxSummary:
    """Test the compute_tax_summary function."""

    def test_empty_line_items(self):
        """Test with no line items."""
        summary = compute_tax_summary([], [])
        assert summary["per_type"] == {}
        assert summary["total_tax"] == Decimal("0.00")
        assert summary["grand_total"] == Decimal("0.00")

    def test_single_line_item_with_tax(self):
        """Test with one line item that has a tax assignment."""
        line_item_id = uuid.uuid4()
        
        # Create mock LineItem
        line_item = LineItem(
            line_item_id=line_item_id,
            draft_id=uuid.uuid4(),
            sequence_number=1,
            description="Test item",
            quantity=Decimal("1"),
            unit="piece",
            unit_price=Decimal("100.00"),
            line_total=Decimal("100.00"),
            extraction_status="COMPLETE",
        )
        
        # Create mock TaxAssignment
        assignment = TaxAssignment(
            tax_assignment_id=uuid.uuid4(),
            line_item_id=line_item_id,
            tax_type=IndonesianTaxType.PPH21,
            tax_rate=Decimal("0.05"),
            tax_amount=Decimal("5.00"),
            assigned_at=datetime.now(timezone.utc),
            assigned_by=uuid.uuid4(),
        )
        
        summary = compute_tax_summary([assignment], [line_item])
        
        assert summary["per_type"]["PPH21"] == Decimal("100.00")
        assert summary["total_tax"] == Decimal("5.00")
        assert summary["grand_total"] == Decimal("105.00")

    def test_multiple_line_items_different_taxes(self):
        """Test with multiple line items with different tax types."""
        line_item_id_1 = uuid.uuid4()
        line_item_id_2 = uuid.uuid4()
        
        line_items = [
            LineItem(
                line_item_id=line_item_id_1,
                draft_id=uuid.uuid4(),
                sequence_number=1,
                description="Item 1",
                quantity=Decimal("1"),
                unit="piece",
                unit_price=Decimal("100.00"),
                line_total=Decimal("100.00"),
                extraction_status="COMPLETE",
            ),
            LineItem(
                line_item_id=line_item_id_2,
                draft_id=uuid.uuid4(),
                sequence_number=2,
                description="Item 2",
                quantity=Decimal("1"),
                unit="piece",
                unit_price=Decimal("1000.00"),
                line_total=Decimal("1000.00"),
                extraction_status="COMPLETE",
            ),
        ]
        
        assignments = [
            TaxAssignment(
                tax_assignment_id=uuid.uuid4(),
                line_item_id=line_item_id_1,
                tax_type=IndonesianTaxType.PPH21,
                tax_rate=Decimal("0.05"),
                tax_amount=Decimal("5.00"),
                assigned_at=datetime.now(timezone.utc),
                assigned_by=uuid.uuid4(),
            ),
            TaxAssignment(
                tax_assignment_id=uuid.uuid4(),
                line_item_id=line_item_id_2,
                tax_type=IndonesianTaxType.PPN,
                tax_rate=Decimal("0.11"),
                tax_amount=Decimal("110.00"),
                assigned_at=datetime.now(timezone.utc),
                assigned_by=uuid.uuid4(),
            ),
        ]
        
        summary = compute_tax_summary(assignments, line_items)
        
        assert summary["per_type"]["PPH21"] == Decimal("100.00")
        assert summary["per_type"]["PPN"] == Decimal("1000.00")
        assert summary["total_tax"] == Decimal("115.00")
        assert summary["grand_total"] == Decimal("1215.00")

    def test_line_item_without_assignment(self):
        """Test with a line item that has no tax assignment (contributes 0 tax)."""
        line_item_id_1 = uuid.uuid4()
        line_item_id_2 = uuid.uuid4()
        
        line_items = [
            LineItem(
                line_item_id=line_item_id_1,
                draft_id=uuid.uuid4(),
                sequence_number=1,
                description="Item with tax",
                quantity=Decimal("1"),
                unit="piece",
                unit_price=Decimal("100.00"),
                line_total=Decimal("100.00"),
                extraction_status="COMPLETE",
            ),
            LineItem(
                line_item_id=line_item_id_2,
                draft_id=uuid.uuid4(),
                sequence_number=2,
                description="Item without tax",
                quantity=Decimal("1"),
                unit="piece",
                unit_price=Decimal("50.00"),
                line_total=Decimal("50.00"),
                extraction_status="COMPLETE",
            ),
        ]
        
        assignments = [
            TaxAssignment(
                tax_assignment_id=uuid.uuid4(),
                line_item_id=line_item_id_1,
                tax_type=IndonesianTaxType.PPH21,
                tax_rate=Decimal("0.05"),
                tax_amount=Decimal("5.00"),
                assigned_at=datetime.now(timezone.utc),
                assigned_by=uuid.uuid4(),
            ),
        ]
        
        summary = compute_tax_summary(assignments, line_items)
        
        # Only line_item_1 contributes to per_type
        assert summary["per_type"]["PPH21"] == Decimal("100.00")
        # But grand_total includes both line items + only tax on item 1
        assert summary["total_tax"] == Decimal("5.00")
        assert summary["grand_total"] == Decimal("155.00")  # 100 + 50 + 5

    def test_grand_total_calculation(self):
        """Test that grand_total = sum of line_totals + total_tax."""
        line_item_id_1 = uuid.uuid4()
        line_item_id_2 = uuid.uuid4()
        
        line_items = [
            LineItem(
                line_item_id=line_item_id_1,
                draft_id=uuid.uuid4(),
                sequence_number=1,
                description="Item 1",
                quantity=Decimal("2"),
                unit="piece",
                unit_price=Decimal("500.00"),
                line_total=Decimal("1000.00"),
                extraction_status="COMPLETE",
            ),
            LineItem(
                line_item_id=line_item_id_2,
                draft_id=uuid.uuid4(),
                sequence_number=2,
                description="Item 2",
                quantity=Decimal("1"),
                unit="piece",
                unit_price=Decimal("250.00"),
                line_total=Decimal("250.00"),
                extraction_status="COMPLETE",
            ),
        ]
        
        assignments = [
            TaxAssignment(
                tax_assignment_id=uuid.uuid4(),
                line_item_id=line_item_id_1,
                tax_type=IndonesianTaxType.PPH21,
                tax_rate=Decimal("0.05"),
                tax_amount=Decimal("50.00"),
                assigned_at=datetime.now(timezone.utc),
                assigned_by=uuid.uuid4(),
            ),
            TaxAssignment(
                tax_assignment_id=uuid.uuid4(),
                line_item_id=line_item_id_2,
                tax_type=IndonesianTaxType.PPN,
                tax_rate=Decimal("0.11"),
                tax_amount=Decimal("27.50"),
                assigned_at=datetime.now(timezone.utc),
                assigned_by=uuid.uuid4(),
            ),
        ]
        
        summary = compute_tax_summary(assignments, line_items)
        
        # grand_total should be: 1000 + 250 + 50 + 27.5 = 1327.5
        expected_grand_total = Decimal("1000") + Decimal("250") + Decimal("50") + Decimal("27.50")
        assert summary["grand_total"] == expected_grand_total


class TestTaxRates:
    """Test that tax rates are properly defined."""

    def test_all_tax_types_have_rates(self):
        """Verify all IndonesianTaxType enum values have rates."""
        for tax_type in IndonesianTaxType:
            assert tax_type in TAX_RATES, f"Missing rate for {tax_type}"

    def test_rates_are_decimal(self):
        """Verify all rates are Decimal type."""
        for tax_type, rate in TAX_RATES.items():
            assert isinstance(rate, Decimal), f"Rate for {tax_type} is not Decimal"

    def test_correct_rate_values(self):
        """Verify the hardcoded rate values match spec."""
        expected_rates = {
            IndonesianTaxType.PPH21: Decimal("0.0500"),
            IndonesianTaxType.PPH22: Decimal("0.0150"),
            IndonesianTaxType.PPH23: Decimal("0.0200"),
            IndonesianTaxType.PPH25: Decimal("0.0200"),
            IndonesianTaxType.PPN: Decimal("0.1100"),
            IndonesianTaxType.NO_TAX: Decimal("0.0000"),
        }
        for tax_type, expected_rate in expected_rates.items():
            assert TAX_RATES[tax_type] == expected_rate, f"Incorrect rate for {tax_type}"
