/**
 * ReviewWorkspace Component
 *
 * Main review workspace that displays:
 * - Invoice PDF viewer (left panel)
 * - Extracted fields and line items with tax assignment (right panel)
 * - Tax summary below the line items
 *
 * Integrates TaxAssignmentPanel and TaxSummarySection components.
 *
 * Satisfies Requirements: 10.1, 10.2, 21.1, 21.3, 21.4, 21.6, 21.7
 */

import React, { useState, useCallback } from "react";
import { LineItem } from "../types/tax";
import TaxAssignmentPanel from "./TaxAssignmentPanel";
import TaxSummarySection from "./TaxSummarySection";
import styles from "./ReviewWorkspace.module.css";

export interface ReviewWorkspaceProps {
  requestId: string;
  lineItems: LineItem[];
  isLocked: boolean;
  pdfUrl?: string;
  onFieldUpdate?: (fieldPath: string, value: unknown) => void;
}

export const ReviewWorkspace: React.FC<ReviewWorkspaceProps> = ({
  requestId,
  lineItems,
  isLocked,
  pdfUrl,
  onFieldUpdate,
}) => {
  const [taxSummaryRefresh, setTaxSummaryRefresh] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const handleTaxAssigned = useCallback(
    (lineItemId: string, taxType: string, _taxAmount: string) => {
      // Trigger tax summary refresh
      setTaxSummaryRefresh((prev) => prev + 1);

      // Notify parent of the update
      if (onFieldUpdate) {
        onFieldUpdate(
          `line_items[${lineItemId}].tax_type`,
          taxType
        );
      }
    },
    [onFieldUpdate]
  );

  const handleError = useCallback((errorMsg: string) => {
    setError(errorMsg);
    // Clear error after 5 seconds
    setTimeout(() => setError(null), 5000);
  }, []);

  return (
    <div className={styles.workspace}>
      <div className={styles.header}>
        <h1>Review Workspace</h1>
        {isLocked && (
          <div className={styles.lockedBadge}>🔒 LOCKED</div>
        )}
      </div>

      {error && (
        <div className={styles.globalError}>
          <button
            className={styles.closeError}
            onClick={() => setError(null)}
          >
            ✕
          </button>
          <strong>Error:</strong> {error}
        </div>
      )}

      <div className={styles.layout}>
        {/* Left Panel: PDF Viewer */}
        <div className={styles.leftPanel}>
          <div className={styles.pdfViewer}>
            {pdfUrl ? (
              <iframe
                src={pdfUrl}
                title="Invoice PDF"
                className={styles.pdfFrame}
              />
            ) : (
              <div className={styles.pdfPlaceholder}>
                <p>PDF viewer not available</p>
                <p className={styles.pdfPlaceholderSmall}>
                  Invoice PDF will be displayed here
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Right Panel: Editable Fields */}
        <div className={styles.rightPanel}>
          <div className={styles.fieldsContainer}>
            <h2>Extracted Fields</h2>

            {/* Tax Assignment Panel */}
            <TaxAssignmentPanel
              requestId={requestId}
              lineItems={lineItems}
              isLocked={isLocked}
              onTaxAssigned={handleTaxAssigned}
              onError={handleError}
            />

            {/* Tax Summary Section */}
            <TaxSummarySection
              requestId={requestId}
              refreshTrigger={taxSummaryRefresh}
              onError={handleError}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default ReviewWorkspace;
