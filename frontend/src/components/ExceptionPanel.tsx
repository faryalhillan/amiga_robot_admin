import React from 'react';
import { FlagDetail, FlagType } from '../types';
import './ExceptionPanel.css';

export interface ExceptionPanelProps {
  flags: FlagType[];
  flagDetails: FlagDetail[];
  requestStatus: 'EXCEPTION' | 'READY_FOR_REVIEW';
  onDismissFlag?: (flagType: FlagType) => void;
}

/**
 * ExceptionPanel Component
 * 
 * Displays all active exception flags with visual distinction and per-flag instructions.
 * Validates Requirements: 9.1, 9.2, 9.3, 9.4
 */
export const ExceptionPanel: React.FC<ExceptionPanelProps> = ({
  flags,
  flagDetails,
  requestStatus,
  onDismissFlag,
}) => {
  if (!flags || flags.length === 0) {
    return null;
  }

  const getFlagDetail = (flagType: FlagType): FlagDetail | undefined => {
    return flagDetails.find((fd) => fd.flag_type === flagType);
  };

  const getFlagColor = (flagType: FlagType): string => {
    switch (flagType) {
      case 'MISSING_EVIDENCE':
        return '#dc3545'; // red
      case 'POSSIBLE_DUPLICATE':
        return '#ff8c00'; // orange
      case 'CALC_DISCREPANCY':
        return '#ffc107'; // yellow
      default:
        return '#6c757d'; // gray
    }
  };

  const getFlagIcon = (flagType: FlagType): string => {
    switch (flagType) {
      case 'MISSING_EVIDENCE':
        return '⚠️'; // Alert Circle equivalent
      case 'POSSIBLE_DUPLICATE':
        return '📋'; // Copy/duplicate icon
      case 'CALC_DISCREPANCY':
        return '⚡'; // Alert Triangle equivalent
      default:
        return 'ℹ️';
    }
  };

  const renderMissingEvidenceContent = (detail: FlagDetail): React.ReactNode => {
    const missingFields = detail.missing_fields || [];
    return (
      <div className="exception-panel__content">
        <p className="exception-panel__instruction">
          <strong>Action Required:</strong> Supply the missing field values:
        </p>
        <ul className="exception-panel__list">
          {missingFields.map((field) => (
            <li key={field}>{field}</li>
          ))}
        </ul>
      </div>
    );
  };

  const renderPossibleDuplicateContent = (detail: FlagDetail): React.ReactNode => {
    const matchingRequests = detail.matching_requests || [];
    return (
      <div className="exception-panel__content">
        <p className="exception-panel__instruction">
          <strong>Action Required:</strong> Compare this request with the matching request(s) below:
        </p>
        <div className="exception-panel__matching-requests">
          {matchingRequests.map((match) => (
            <div key={match.request_id} className="exception-panel__matching-item">
              <div className="exception-panel__matching-header">
                <strong>Request ID:</strong>
                <code className="exception-panel__request-id">{match.request_id}</code>
              </div>
              <div className="exception-panel__matching-detail">
                <span><strong>Status:</strong> {match.status}</span>
              </div>
              <div className="exception-panel__matching-detail">
                <span><strong>Invoice Date:</strong> {match.invoice_date}</span>
              </div>
              <div className="exception-panel__matching-detail">
                <span><strong>Total Amount:</strong> {match.total_amount}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  const renderCalculationDiscrepancyContent = (detail: FlagDetail): React.ReactNode => {
    const discrepancies = detail.discrepancies || [];
    return (
      <div className="exception-panel__content">
        <p className="exception-panel__instruction">
          <strong>Action Required:</strong> Correct the identified inconsistent value(s):
        </p>
        <div className="exception-panel__discrepancies">
          {discrepancies.map((disc, idx) => (
            <div key={idx} className="exception-panel__discrepancy-item">
              <div className="exception-panel__discrepancy-field">
                <strong>{disc.field_name}</strong>
              </div>
              <div className="exception-panel__discrepancy-comparison">
                <div className="exception-panel__value-group">
                  <span className="exception-panel__value-label">Computed:</span>
                  <code className="exception-panel__value-code">{disc.computed}</code>
                </div>
                <div className="exception-panel__value-group">
                  <span className="exception-panel__value-label">Extracted:</span>
                  <code className="exception-panel__value-code">{disc.extracted}</code>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  const renderFlagContent = (flagType: FlagType): React.ReactNode => {
    const detail = getFlagDetail(flagType);
    if (!detail) return null;

    switch (flagType) {
      case 'MISSING_EVIDENCE':
        return renderMissingEvidenceContent(detail);
      case 'POSSIBLE_DUPLICATE':
        return renderPossibleDuplicateContent(detail);
      case 'CALC_DISCREPANCY':
        return renderCalculationDiscrepancyContent(detail);
      default:
        return null;
    }
  };

  const getFlagLabel = (flagType: FlagType): string => {
    switch (flagType) {
      case 'MISSING_EVIDENCE':
        return 'Missing Evidence';
      case 'POSSIBLE_DUPLICATE':
        return 'Possible Duplicate';
      case 'CALC_DISCREPANCY':
        return 'Calculation Discrepancy';
      default:
        return flagType;
    }
  };

  return (
    <div className="exception-panel">
      <div className="exception-panel__header">
        <h2 className="exception-panel__title">⚠️ Request in Exception Status</h2>
        <p className="exception-panel__subtitle">
          This request has one or more issues that must be resolved before it can be approved.
        </p>
      </div>

      <div className="exception-panel__flags-container">
        {flags.map((flagType) => (
          <div
            key={flagType}
            className="exception-panel__flag"
            style={{
              borderLeftColor: getFlagColor(flagType),
            }}
          >
            <div className="exception-panel__flag-header">
              <span className="exception-panel__flag-icon">{getFlagIcon(flagType)}</span>
              <span className="exception-panel__flag-badge" style={{ backgroundColor: getFlagColor(flagType) }}>
                {getFlagLabel(flagType)}
              </span>
              {onDismissFlag && flagType === 'POSSIBLE_DUPLICATE' && (
                <button
                  className="exception-panel__dismiss-button"
                  onClick={() => onDismissFlag(flagType)}
                  title="Dismiss this flag if it is a false positive"
                >
                  ✕
                </button>
              )}
            </div>

            {renderFlagContent(flagType)}
          </div>
        ))}
      </div>

      {requestStatus === 'EXCEPTION' && (
        <div className="exception-panel__approval-notice">
          <p className="exception-panel__notice-text">
            🔒 Approval is disabled while exception flags are active. Please resolve all issues above to enable approval.
          </p>
        </div>
      )}
    </div>
  );
};

export default ExceptionPanel;
