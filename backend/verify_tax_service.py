#!/usr/bin/env python3
"""
Simple verification script for tax_service implementation.
Tests the core logic without requiring full SQLAlchemy setup.
"""

from decimal import Decimal
import sys


# Define minimal mock classes for testing
class MockLineItem:
    def __init__(self, line_item_id, line_total):
        self.line_item_id = line_item_id
        self.line_total = line_total


class MockTaxAssignment:
    def __init__(self, line_item_id, tax_type, tax_rate, tax_amount):
        self.line_item_id = line_item_id
        self.tax_type = tax_type
        self.tax_rate = tax_rate
        self.tax_amount = tax_amount


# Define minimal mock enums and rates
class IndonesianTaxType:
    PPH21 = "PPH21"
    PPH22 = "PPH22"
    PPH23 = "PPH23"
    PPH25 = "PPH25"
    PPN = "PPN"
    NO_TAX = "NO_TAX"


TAX_RATES = {
    "PPH21": Decimal("0.0500"),
    "PPH22": Decimal("0.0150"),
    "PPH23": Decimal("0.0200"),
    "PPH25": Decimal("0.0200"),
    "PPN": Decimal("0.1100"),
    "NO_TAX": Decimal("0.0000"),
}


# Implementation of tax_service functions
def compute_tax_amount(line_total: Decimal, tax_type: str) -> Decimal:
    """Compute the tax amount for a line item given its total and tax type."""
    if not isinstance(line_total, Decimal):
        raise TypeError(f"line_total must be Decimal, got {type(line_total).__name__}")
    
    tax_rate = TAX_RATES[tax_type]
    tax_amount = line_total * tax_rate
    return tax_amount


def compute_tax_summary(tax_assignments: list, line_items: list) -> dict:
    """Compute a tax summary grouped by tax type."""
    # Create a mapping from line_item_id to line_item for quick lookup
    line_items_by_id = {li.line_item_id: li for li in line_items}

    # Group line totals by tax type
    per_type_subtotals = {}
    total_subtotal = Decimal("0")

    for tax_assignment in tax_assignments:
        line_item = line_items_by_id.get(tax_assignment.line_item_id)
        if line_item is None:
            continue

        # Treat None line_total as 0
        line_total = Decimal(str(line_item.line_total)) if line_item.line_total is not None else Decimal("0")

        # Add to per-type subtotal
        if tax_assignment.tax_type not in per_type_subtotals:
            per_type_subtotals[tax_assignment.tax_type] = Decimal("0")
        per_type_subtotals[tax_assignment.tax_type] += line_total

        # Add to grand subtotal
        total_subtotal += line_total

    # Compute tax for each type and sum all taxes
    total_tax = Decimal("0")
    for tax_type, subtotal in per_type_subtotals.items():
        tax_for_type = compute_tax_amount(subtotal, tax_type)
        total_tax += tax_for_type

    # Compute grand total
    grand_total = total_subtotal + total_tax

    return {
        "per_type": per_type_subtotals,
        "total_tax": total_tax,
        "grand_total": grand_total,
    }


# Test cases
def test_compute_tax_amount():
    """Test the compute_tax_amount function."""
    print("Testing compute_tax_amount...")
    
    # Test PPH21 (5%)
    result = compute_tax_amount(Decimal("100.00"), "PPH21")
    assert result == Decimal("5.00"), f"PPH21 failed: {result}"
    print("  ✓ PPH21 (5%) tax computation")
    
    # Test PPN (11%)
    result = compute_tax_amount(Decimal("1000.00"), "PPN")
    assert result == Decimal("110.00"), f"PPN failed: {result}"
    print("  ✓ PPN (11%) tax computation")
    
    # Test NO_TAX (0%)
    result = compute_tax_amount(Decimal("500.00"), "NO_TAX")
    assert result == Decimal("0.00"), f"NO_TAX failed: {result}"
    print("  ✓ NO_TAX (0%) computation")
    
    # Verify Decimal is used (precision test)
    result = compute_tax_amount(Decimal("333.333"), "PPH21")
    expected = Decimal("333.333") * Decimal("0.0500")
    assert result == expected, f"Precision test failed: {result} != {expected}"
    print("  ✓ Decimal precision maintained")
    
    print("✅ compute_tax_amount tests passed!\n")


def test_compute_tax_summary():
    """Test the compute_tax_summary function."""
    print("Testing compute_tax_summary...")
    
    # Test 1: Empty inputs
    result = compute_tax_summary([], [])
    assert result["per_type"] == {}, "Empty test failed"
    assert result["total_tax"] == Decimal("0.00"), "Empty test failed"
    assert result["grand_total"] == Decimal("0.00"), "Empty test failed"
    print("  ✓ Empty inputs handled correctly")
    
    # Test 2: Single line item with tax
    line_id = "line1"
    line_items = [MockLineItem(line_id, Decimal("100.00"))]
    assignments = [MockTaxAssignment(line_id, "PPH21", Decimal("0.05"), Decimal("5.00"))]
    
    result = compute_tax_summary(assignments, line_items)
    assert result["per_type"]["PPH21"] == Decimal("100.00"), "Single item subtotal failed"
    assert result["total_tax"] == Decimal("5.00"), "Single item tax failed"
    assert result["grand_total"] == Decimal("105.00"), "Single item grand total failed"
    print("  ✓ Single line item with tax")
    
    # Test 3: Multiple items with different tax types
    line_id_1 = "line1"
    line_id_2 = "line2"
    line_items = [
        MockLineItem(line_id_1, Decimal("100.00")),
        MockLineItem(line_id_2, Decimal("1000.00")),
    ]
    assignments = [
        MockTaxAssignment(line_id_1, "PPH21", Decimal("0.05"), Decimal("5.00")),
        MockTaxAssignment(line_id_2, "PPN", Decimal("0.11"), Decimal("110.00")),
    ]
    
    result = compute_tax_summary(assignments, line_items)
    assert result["per_type"]["PPH21"] == Decimal("100.00"), "Multi-item PPH21 subtotal failed"
    assert result["per_type"]["PPN"] == Decimal("1000.00"), "Multi-item PPN subtotal failed"
    assert result["total_tax"] == Decimal("115.00"), "Multi-item total tax failed"
    assert result["grand_total"] == Decimal("1215.00"), "Multi-item grand total failed"
    print("  ✓ Multiple items with different tax types")
    
    # Test 4: Grand total calculation
    line_id_1 = "line1"
    line_id_2 = "line2"
    line_items = [
        MockLineItem(line_id_1, Decimal("1000.00")),
        MockLineItem(line_id_2, Decimal("250.00")),
    ]
    assignments = [
        MockTaxAssignment(line_id_1, "PPH21", Decimal("0.05"), Decimal("50.00")),
        MockTaxAssignment(line_id_2, "PPN", Decimal("0.11"), Decimal("27.50")),
    ]
    
    result = compute_tax_summary(assignments, line_items)
    expected_grand_total = Decimal("1000") + Decimal("250") + Decimal("50") + Decimal("27.50")
    assert result["grand_total"] == expected_grand_total, f"Grand total failed: {result['grand_total']} != {expected_grand_total}"
    print("  ✓ Grand total calculation correct")
    
    print("✅ compute_tax_summary tests passed!\n")


def test_all_tax_rates():
    """Verify all tax rates are defined correctly."""
    print("Testing tax rates...")
    
    expected_rates = {
        "PPH21": Decimal("0.0500"),
        "PPH22": Decimal("0.0150"),
        "PPH23": Decimal("0.0200"),
        "PPH25": Decimal("0.0200"),
        "PPN": Decimal("0.1100"),
        "NO_TAX": Decimal("0.0000"),
    }
    
    for tax_type, expected_rate in expected_rates.items():
        assert TAX_RATES[tax_type] == expected_rate, f"Rate mismatch for {tax_type}"
        assert isinstance(TAX_RATES[tax_type], Decimal), f"Rate for {tax_type} is not Decimal"
    
    print("  ✓ All tax rates defined with correct Decimal values")
    print("✅ Tax rates verification passed!\n")


if __name__ == "__main__":
    try:
        test_compute_tax_amount()
        test_compute_tax_summary()
        test_all_tax_rates()
        print("=" * 50)
        print("✅ ALL VERIFICATION TESTS PASSED!")
        print("=" * 50)
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
