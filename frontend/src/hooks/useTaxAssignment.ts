/**
 * Custom React hook for managing tax assignment operations.
 */

import { useState, useCallback } from "react";
import { apiClient } from "../api/client";
import { TaxAssignmentResponse, TaxSummaryResponse } from "../types/tax";

export interface UseTaxAssignmentState {
  loading: boolean;
  error: string | null;
}

export interface UseTaxAssignmentCallbacks {
  assignTax: (
    requestId: string,
    lineItemId: string,
    taxType: string
  ) => Promise<TaxAssignmentResponse>;
  getTaxSummary: (requestId: string) => Promise<TaxSummaryResponse>;
}

/**
 * Hook for managing tax assignment and summary operations.
 */
export function useTaxAssignment(): UseTaxAssignmentState & UseTaxAssignmentCallbacks {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const assignTax = useCallback(
    async (
      requestId: string,
      lineItemId: string,
      taxType: string
    ): Promise<TaxAssignmentResponse> => {
      setLoading(true);
      setError(null);

      try {
        const response = await apiClient.put<TaxAssignmentResponse>(
          `/requests/${requestId}/line-items/${lineItemId}/tax`,
          { tax_type: taxType }
        );
        return response;
      } catch (err) {
        const errorMessage =
          err && typeof err === "object" && "detail" in err
            ? (err as any).detail || "Failed to assign tax"
            : "Failed to assign tax";
        setError(errorMessage);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const getTaxSummary = useCallback(
    async (requestId: string): Promise<TaxSummaryResponse> => {
      setLoading(true);
      setError(null);

      try {
        const response = await apiClient.get<TaxSummaryResponse>(
          `/requests/${requestId}/tax-summary`
        );
        return response;
      } catch (err) {
        const errorMessage =
          err && typeof err === "object" && "detail" in err
            ? (err as any).detail || "Failed to fetch tax summary"
            : "Failed to fetch tax summary";
        setError(errorMessage);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return {
    loading,
    error,
    assignTax,
    getTaxSummary,
  };
}
