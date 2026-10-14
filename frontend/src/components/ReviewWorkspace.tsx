import React, { useState, useEffect } from 'react';
import { Request } from '../types';
import { ExceptionPanel } from './ExceptionPanel';
import './ReviewWorkspace.css';

export interface ReviewWorkspaceProps {
  request: Request;
  onApprove?: () => void;
  onReject?: () => void;
  onFieldChange?: (fieldPath: string, newValue: any) => void;
}

/**
 * ReviewWorkspace Component
 * 
 * Two-panel layout (PDF viewer on left, editable draft form on right).
 * Integrates ExceptionPanel to display flags and prevents approval when EXCEPTION status is active.
 * 
 * Validates Requirements: 4.2, 10.1, 10.3, 10.4, 9.1, 9.2, 9.3, 9.4
 */
export const ReviewWorkspace: React.FC<ReviewWorkspaceProps> = ({
  request,
  onApprove,
  onReject,
  onFieldChange,
}) => {
  const [unsavedChanges, setUnsavedChanges] = useState(false);

  // Check if there are unsaved changes before navigation
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (unsavedChanges) {
        e.preventDefault();
        e.returnValue = '';
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [unsavedChanges]);

  // Determine if approval button should be disabled
  const isInException = request.status === 'EXCEPTION';
  const isApprovalDisabled = isInException;

  const handleFieldChange = (fieldPath: string, newValue: any) => {
    setUnsavedChanges(true);
    if (onFieldChange) {
      onFieldChange(fieldPath, newValue);
    }
  };

  const handleApprove = () => {
    if (!isApprovalDisabled && onApprove) {
      onApprove();
    }
  };

  const handleReject = () => {
    if (onReject) {
      onReject();
    }
  };

  return (
    <div className="review-workspace">
      {/* Exception Panel at the top - prominently displays flags */}
      {request.flags && request.flags.length > 0 && (
        <ExceptionPanel
          flags={request.flags}
          flagDetails={request.flag_details || []}
          requestStatus={request.status as 'EXCEPTION' | 'READY_FOR_REVIEW'}
          onDismissFlag={(flagType) => {
            console.log('Dismissing flag:', flagType);
            // This would call an API to dismiss the flag
          }}
        />
      )}

      <div className="review-workspace__container">
        {/* Left Panel: PDF Viewer */}
        <div className="review-workspace__pdf-panel">
          <div className="review-workspace__pdf-placeholder">
            <h3>Invoice PDF Viewer</h3>
            <p>PDF viewer would be rendered here using react-pdf</p>
            <p className="review-workspace__placeholder-subtitle">
              {request.vendor_name} - {request.invoice_number}
            </p>
          </div>
        </div>

        {/* Right Panel: Editable Draft Form */}
        <div className="review-workspace__form-panel">
          <div className="review-workspace__ai-label">
            ⚙️ AI-generated draft — not approved
          </div>

          <div className="review-workspace__form-content">
            <h3 className="review-workspace__section-title">Invoice Details</h3>

            <div className="review-workspace__form-group">
              <label className="review-workspace__label">Vendor Name</label>
              <div className="review-workspace__field-wrapper">
                <input
                  type="text"
                  className="review-workspace__input"
                  defaultValue={request.vendor_name}
                  onChange={(e) => handleFieldChange('header.vendor_name', e.target.value)}
                />
                <span className="review-workspace__original-value">
                  Original: {request.vendor_name}
                </span>
              </div>
            </div>

            <div className="review-workspace__form-group">
              <label className="review-workspace__label">Invoice Number</label>
              <div className="review-workspace__field-wrapper">
                <input
                  type="text"
                  className="review-workspace__input"
                  defaultValue={request.invoice_number}
                  onChange={(e) => handleFieldChange('header.invoice_number', e.target.value)}
                />
                <span className="review-workspace__original-value">
                  Original: {request.invoice_number}
                </span>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="review-workspace__actions">
              <button
                className="review-workspace__button review-workspace__button--approve"
                onClick={handleApprove}
                disabled={isApprovalDisabled}
                title={
                  isApprovalDisabled
                    ? 'Cannot approve - resolve all exceptions first'
                    : 'Approve this invoice'
                }
              >
                ✓ Approve
              </button>
              <button
                className="review-workspace__button review-workspace__button--reject"
                onClick={handleReject}
              >
                ✕ Reject
              </button>
            </div>

            {unsavedChanges && (
              <div className="review-workspace__unsaved-notice">
                You have unsaved changes.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ReviewWorkspace;
