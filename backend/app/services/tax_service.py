# backend/app/services/tax_service.py
"""
Tax computation service for Indonesian tax types.

All arithmetic uses Decimal to avoid float rounding errors.
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.invoice_fields import LineItem
    from app.models.tax_assignment import TaxAssignment

from app.models.tax_assignment import TAX_RATES, IndonesianTaxType


def compute_tax_amount(line_total: Decimal, tax_type: IndonesianTaxType) -> Decimal:
    """
    Return the tax amount for a single line item.

    Args:
        line_total: The gross line total (Decimal).
        tax_type:   An IndonesianTaxType enum member.

    Returns:
        Decimal tax amount, rounded to 4 decimal places.
    """
    rate = TAX_RATES.get(tax_type.value, Decimal("0"))
    return (line_total * rate).quantize(Decimal("0.0001"))


def compute_tax_summary(
    tax_assignments: list["TaxAssignment"],
    line_items: list["LineItem"],
) -> dict:
    """
    Compute a tax summary given a list of TaxAssignment and LineItem rows.

    Returns a dict::

        {
            "per_type_subtotals": {tax_type_str: Decimal subtotal, ...},
            "total_tax":  Decimal,
            "grand_total": Decimal,   # subtotal_of_all_line_totals + total_tax
        }

    Line items that have no TaxAssignment contribute 0 tax and are counted
    under "NO_TAX".
    """
    # Build a lookup: line_item_id → TaxAssignment
    assignment_by_item: dict = {ta.line_item_id: ta for ta in tax_assignments}

    per_type: dict[str, Decimal] = {}
    total_line_sum = Decimal("0")

    for li in line_items:
        line_total = Decimal(str(li.line_total)) if li.line_total is not None else Decimal("0")
        total_line_sum += line_total

        ta = assignment_by_item.get(li.line_item_id)
        if ta is None:
            tax_amt = Decimal("0")
            tax_key = IndonesianTaxType.NO_TAX.value
        else:
            tax_amt = Decimal(str(ta.tax_amount))
            tax_key = ta.tax_type

        per_type[tax_key] = per_type.get(tax_key, Decimal("0")) + tax_amt

    total_tax = sum(per_type.values(), Decimal("0"))
    grand_total = total_line_sum + total_tax

    return {
        "per_type_subtotals": per_type,
        "total_tax": total_tax,
        "grand_total": grand_total,
    }
