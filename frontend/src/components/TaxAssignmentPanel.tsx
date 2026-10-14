/**
 * TaxAssignmentPanel Component
 *
 * Renders a table of line items with tax type selectors and computed tax amounts.
 * Allows Finance Reviewers to assign Indonesian tax types to each line item.
 *
 * Satisfies Requirements: 21.1, 21.3, 21.7
 */

import React, { useState, useCallback, useEffect } from "react";
import {
  IndonesianTaxType,
  TAX_TYPE_DISPLAY_NAMES,
  LineItem,
} from "../types/tax";
import { useTaxAssignment } from "../hooks/useTaxAssignment";
import { formatCurrency } from "../utils/formatting";
import styles from "./TaxAssignmentPanel.module.css";

export interface TaxAssignmentPanelProps {
  requestId: string;
  lineItems: LineItem[];
  isLocked: boolean;
  onTaxAssigned?: (lineItemId: string, taxType: string, taxAmount: string) => void;
  onError?: (error: string) => void;
}

export const TaxAssignmentPanel: React.FC<TaxAssignmentPanelProps> = ({
  requestId,
  lineItems,
  isLocked,
  onTaxAssigned,
  onError,
}) => {
  const { assignTax, error } = useTaxAssignment();
  const [localLineItems, setLocalLineItems] = useState<LineItem[]>(lineItems);
  const [assigningLineItemId, setAssigningLineItemId] = useState<string | null>(
    null
  );

  // Sync local state when props change
  useEffect(() => {
    setLocalLineItems(lineItems);
  }, [lineItems]);

  // Report errors to parent
  useEffect(() => {
    if (error && onError) {
      onError(error);
    }
  }, [error, onError]);

  const handleTaxTypeChange = useCallback(
    async (lineItemId: string, taxType: string) => {
      setAssigningLineItemId(lineItemId);

      try {
        const response = await assignTax(requestId, lineItemId, taxType);

        // Update local state with response
        setLocalLineItems((items) =>
          items.map((item) =>
            item.line_item_id === lineItemId
              ? {
                  ...item,
                  tax_type: taxType as IndonesianTaxType,
                  tax_rate: parseFloat(response.tax_rate),
                  tax_amount: parseFloat(response.tax_amount),
                }
              : item
          )
        );

        // Notify parent
        if (onTaxAssigned) {
          onTaxAssigned(lineItemId, taxType, response.tax_amount);
        }
      } catch (err) {
        // Error is already handled by the hook
        console.error("Failed to assign tax:", err);
      } finally {
        setAssigningLineItemId(null);
      }
    },
    [requestId, assignTax, onTaxAssigned]
  );

  return (
    <div className={styles.container}>
      <h2>Tax Assignment</h2>

      {error && (
        <div className={styles.errorMessage}>
          <strong>Error:</strong> {error}
        </div>
      )}

      <table className={styles.table}>
        <thead>
          <tr>
            <th>Sequence</th>
            <th>Description</th>
            <th>Unit Price</th>
            <th>Quantity</th>
            <th>Line Total</th>
            <th>Tax Type</th>
            <th>Tax Amount</th>
          </tr>
        </thead>
        <tbody>
          {localLineItems.map((item, index) => (
            <tr key={item.line_item_id} className={styles.row}>
              <td className={styles.sequence}>{index + 1}</td>
              <td className={styles.description}>{item.description || "—"}</td>
              <td className={styles.numeric}>
                {item.unit_price !== undefined
                  ? formatCurrency(item.unit_price)
                  : "—"}
              </td>
              <td className={styles.numeric}>
                {item.quantity !== undefined
                  ? `${item.quantity} ${item.unit || ""}`
                  : "—"}
              </td>
              <td className={styles.numeric}>
                {item.line_total !== undefined
                  ? formatCurrency(item.line_total)
                  : "—"}
              </td>
              <td className={styles.selector}>
                <select
                  value={item.tax_type || ""}
                  onChange={(e) =>
                    handleTaxTypeChange(item.line_item_id, e.target.value)
                  }
                  disabled={isLocked || assigningLineItemId === item.line_item_id}
                  className={
                    isLocked
                      ? styles.disabledSelect
                      : styles.enabledSelect
                  }
                  title={
                    isLocked
                      ? "Request is locked. Tax assignments cannot be modified."
                      : "Select a tax type"
                  }
                >
                  <option value="">— Select Tax Type —</option>
                  {Object.values(IndonesianTaxType).map((taxType) => (
                    <option key={taxType} value={taxType}>
                      {TAX_TYPE_DISPLAY_NAMES[taxType]}
                    </option>
                  ))}
                </select>
                {assigningLineItemId === item.line_item_id && (
                  <span className={styles.loadingSpinner}>⟳</span>
                )}
              </td>
              <td className={styles.taxAmount}>
                {item.tax_amount !== undefined
                  ? formatCurrency(item.tax_amount)
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {localLineItems.length === 0 && (
        <p className={styles.emptyMessage}>No line items to display.</p>
      )}

      {isLocked && (
        <div className={styles.lockedNotice}>
          <strong>ℹ</strong> This request is locked. Tax assignments cannot be
          modified.
        </div>
      )}
    </div>
  );
};

export default TaxAssignmentPanel;
