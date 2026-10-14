/**
 * Type definitions for tax-related data structures.
 */

export enum IndonesianTaxType {
  PPH21 = "PPH21",
  PPH22 = "PPH22",
  PPH23 = "PPH23",
  PPH25 = "PPH25",
  PPN = "PPN",
  NO_TAX = "NO_TAX",
}

// Display names for tax types
export const TAX_TYPE_DISPLAY_NAMES: Record<IndonesianTaxType, string> = {
  [IndonesianTaxType.PPH21]: "PPh 21 (5%)",
  [IndonesianTaxType.PPH22]: "PPh 22 (1.5%)",
  [IndonesianTaxType.PPH23]: "PPh 23 (2%)",
  [IndonesianTaxType.PPH25]: "PPh 25 (2%)",
  [IndonesianTaxType.PPN]: "PPN (11%)",
  [IndonesianTaxType.NO_TAX]: "No Tax",
};

// Tax rates (as percentages * 100 for display)
export const TAX_RATES: Record<IndonesianTaxType, number> = {
  [IndonesianTaxType.PPH21]: 5,
  [IndonesianTaxType.PPH22]: 1.5,
  [IndonesianTaxType.PPH23]: 2,
  [IndonesianTaxType.PPH25]: 2,
  [IndonesianTaxType.PPN]: 11,
  [IndonesianTaxType.NO_TAX]: 0,
};

export interface LineItem {
  line_item_id: string;
  description?: string;
  quantity?: number;
  unit?: string;
  unit_price?: number;
  line_total?: number;
  tax_type?: IndonesianTaxType | null;
  tax_rate?: number;
  tax_amount?: number;
}

export interface TaxAssignmentRequest {
  tax_type: string;
}

export interface TaxAssignmentResponse {
  line_item_id: string;
  tax_type: string;
  tax_rate: string;
  tax_amount: string;
}

export interface TaxSummaryLineItem {
  line_item_id: string;
  description?: string;
  quantity?: number;
  unit?: string;
  unit_price?: number;
  line_total?: number;
  tax_type?: string;
  tax_rate?: number;
  tax_amount?: number;
}

export interface TaxSummaryResponse {
  line_items: TaxSummaryLineItem[];
  per_type_subtotals: Record<string, string>;
  total_tax: string;
  grand_total: string;
  locked: boolean;
}
