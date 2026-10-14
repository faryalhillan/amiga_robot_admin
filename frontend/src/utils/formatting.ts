/**
 * Formatting utilities for currency and numeric values.
 */

/**
 * Format a number as currency (IDR with proper formatting).
 * Handles string inputs that may come from Decimal fields in the API.
 */
export function formatCurrency(
  value: number | string | undefined | null
): string {
  if (value === undefined || value === null) {
    return "IDR 0.00";
  }

  const numValue = typeof value === "string" ? parseFloat(value) : value;

  if (isNaN(numValue)) {
    return "IDR 0.00";
  }

  return new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency: "IDR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(numValue);
}

/**
 * Format a number as percentage.
 */
export function formatPercentage(value: number): string {
  return `${value.toFixed(2)}%`;
}

/**
 * Parse a currency string value from the API to a number.
 */
export function parseCurrency(value: string | number | undefined): number {
  if (value === undefined || value === null) {
    return 0;
  }

  const numValue = typeof value === "string" ? parseFloat(value) : value;
  return isNaN(numValue) ? 0 : numValue;
}
