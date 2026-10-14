# backend/app/services/tax_service.py

from decimal import Decimal

from app.models.invoice_fields import LineItem
from app.models.tax_assignment import IndonesianTaxType, TAX_RATES, TaxAssignment


def compute_tax_amount(line_total: Decimal, tax_type: IndonesianTaxType) -> Decimal:
    """
    Compute the tax amount for a line item.
    Uses only Decimal arithmetic, never float.

    Args:
        line_total: The total amount for the line item (as Decimal).
        tax_type: The IndonesianTaxType to apply.

    Returns:
        The computed tax amount (as Decimal).
    """
    # Ensure line_total is Decimal
    if not isinstance(line_total, Decimal):
        line_total = Decimal(str(line_total))

    # Get the tax rate (always a Decimal)
    tax_rate = TAX_RATES[tax_type]

    # Compute using Decimal multiplication only
    tax_amount = line_total * tax_rate

    return tax_amount


def compute_tax_summary(
    tax_assignments: list[TaxAssignment], line_items: list[LineItem]
) -> dict:
    """
    Compute the tax summary for a set of line items.

    Args:
        tax_assignments: List of TaxAssignment objects.
        line_items: List of LineItem objects.

    Returns:
        A dictionary with:
        - "per_type": {tax_type_name: subtotal_for_type, ...}
        - "total_tax": total tax amount (Decimal)
        - "grand_total": sum of all line totals + total tax (Decimal)
    """
    # Build a mapping of line_item_id -> TaxAssignment for efficient lookup
    assignment_map = {ta.line_item_id: ta for ta in tax_assignments}

    # Initialize per-type subtotals
    per_type_subtotals: dict[str, Decimal] = {}
    total_tax = Decimal("0.00")
    line_total_sum = Decimal("0.00")

    # Process each line item
    for line_item in line_items:
        # Convert line_total to Decimal
        line_total = Decimal(str(line_item.line_total)) if line_item.line_total else Decimal("0.00")
        line_total_sum += line_total

        # Check if this line item has a tax assignment
        if line_item.line_item_id in assignment_map:
            assignment = assignment_map[line_item.line_item_id]
            tax_type_name = assignment.tax_type.value

            # Add to per-type subtotal (line total for this type)
            if tax_type_name not in per_type_subtotals:
                per_type_subtotals[tax_type_name] = Decimal("0.00")
            per_type_subtotals[tax_type_name] += line_total

            # Add to total tax
            tax_amount = Decimal(str(assignment.tax_amount))
            total_tax += tax_amount

    # Compute grand total: sum of line totals + total tax
    grand_total = line_total_sum + total_tax

    return {
        "per_type": per_type_subtotals,
        "total_tax": total_tax,
        "grand_total": grand_total,
    }
