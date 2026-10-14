/**
 * TaxSummarySection Component
 *
 * Displays a live tax summary including per-type subtotals and grand total.
 * Fetches data from GET /requests/{id}/tax-summary endpoint.
 *
 * Satisfies Requirements: 21.4, 21.6, 21.7
 */

import React, { useState, useEffect } from "react";
import { useTaxAssignment } from "../hooks/useTaxAssignment";
import { TaxSummaryResponse } from "../types/tax";
import { formatCurrency } from "../utils/formatting";
import styles from "./TaxSummarySection.module.css";

export interface TaxSummarySectionProps {
  requestId: string;
  refreshTrigger?: number;
  onError?: (error: string) => void;
}

export const TaxSummarySection: React.FC<TaxSummarySectionProps> = ({
  requestId,
  refreshTrigger = 0,
  onError,
}) => {
  const { getTaxSummary, loading, error } = useTaxAssignment();
  const [summary, setSummary] = useState<TaxSummaryResponse | null>(null);

  useEffect(() => {
    const fetchTaxSummary = async () => {
      try {
        const data = await getTaxSummary(requestId);
        setSummary(data);
      } catch (err) {
        console.error("Failed to fetch tax summary:", err);
      }
    };

    fetchTaxSummary();
  }, [requestId, refreshTrigger, getTaxSummary]);

  useEffect(() => {
    if (error && onError) {
      onError(error);
    }
  }, [error, onError]);

  if (loading && !summary) {
    return (
      <div className={styles.container}>
        <h2>Tax Summary</h2>
        <div className={styles.loadingMessage}>Loading tax summary...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.container}>
        <h2>Tax Summary</h2>
        <div className={styles.errorMessage}>
          <strong>Error:</strong> {error}
        </div>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className={styles.container}>
        <h2>Tax Summary</h2>
        <div className={styles.emptyMessage}>No tax data available.</div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <h2>Tax Summary</h2>

      <div className={styles.summaryGrid}>
        {/* Per-Type Subtotals */}
        <div className={styles.subtotalsSection}>
          <h3>Tax by Type</h3>
          {Object.keys(summary.per_type_subtotals).length > 0 ? (
            <table className={styles.subtotalsTable}>
              <thead>
                <tr>
                  <th>Tax Type</th>
                  <th>Subtotal</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(summary.per_type_subtotals).map(([taxType, amount]) => (
                  <tr key={taxType}>
                    <td className={styles.taxTypeLabel}>{taxType}</td>
                    <td className={styles.amount}>
                      {formatCurrency(amount)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className={styles.noDataMessage}>No tax assignments yet.</p>
          )}
        </div>

        {/* Totals Section */}
        <div className={styles.totalsSection}>
          <h3>Totals</h3>
          <div className={styles.totalRow}>
            <span className={styles.totalLabel}>Total Tax:</span>
            <span className={styles.totalValue}>
              {formatCurrency(summary.total_tax)}
            </span>
          </div>
          <div className={styles.totalRow + " " + styles.grandTotalRow}>
            <span className={styles.totalLabel}>Grand Total:</span>
            <span className={styles.grandTotalValue}>
              {formatCurrency(summary.grand_total)}
            </span>
          </div>

          {summary.locked && (
            <div className={styles.lockedBadge}>🔒 Locked</div>
          )}
        </div>
      </div>

      {summary.locked && (
        <div className={styles.lockedNotice}>
          <strong>ℹ</strong> This request is locked. Tax summary is final and
          cannot be modified.
        </div>
      )}
    </div>
  );
};

export default TaxSummarySection;
