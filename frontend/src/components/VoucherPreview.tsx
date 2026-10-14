import { useEffect, useState } from 'react';

interface LineItem {
  line_item_id: string;
  sequence_number: number;
  description: string | null;
  quantity: string | null;
  unit: string | null;
  unit_price: string | null;
  line_total: string | null;
}

interface VoucherPreviewData {
  request_id: string;
  vendor_name: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  currency: string | null;
  subtotal: string | null;
  total_amount: string | null;
  tax_amount: string | null;
  fee_amount: string | null;
  rounding_adj: string | null;
  line_items: LineItem[];
  bank_account_number: string | null;
  bank_name: string | null;
  payment_reference: string | null;
  authorization_disclaimer: string;
  generated_at: string;
}

/**
 * VoucherPreview component renders a read-only voucher preview for an
 * AMIGA_REVIEWED request. Displays all approved fields and the authorization
 * disclaimer. Shows error message and retry button if the preview endpoint
 * returns an error.
 *
 * Requirements: 14.2, 14.4
 */
const VoucherPreview = ({ requestId }: { requestId: string }) => {
  const [preview, setPreview] = useState<VoucherPreviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchPreview = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/requests/${requestId}/voucher-preview`);
      if (!response.ok) {
        if (response.status === 404) {
          setError('Request not found.');
        } else if (response.status === 403) {
          setError('You are not authorized to view this voucher preview.');
        } else if (response.status === 400) {
          setError('The request has not been approved yet.');
        } else {
          setError(`Failed to load preview: ${response.statusText}`);
        }
        setPreview(null);
        return;
      }

      const data: VoucherPreviewData = await response.json();
      setPreview(data);
      setError(null);
    } catch (err) {
      setError(`Failed to load preview: ${err instanceof Error ? err.message : String(err)}`);
      setPreview(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPreview();
  }, [requestId]);

  const handleRetry = () => {
    fetchPreview();
  };

  if (loading) {
    return (
      <div className="voucher-preview loading" data-testid="voucher-preview">
        <p>Loading voucher preview...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="voucher-preview error" data-testid="voucher-preview">
        <div className="error-message" data-testid="error-message">
          <p>{error}</p>
        </div>
        <button onClick={handleRetry} className="retry-button" data-testid="retry-button">
          Retry
        </button>
      </div>
    );
  }

  if (!preview) {
    return (
      <div className="voucher-preview empty" data-testid="voucher-preview">
        <p>No preview available.</p>
      </div>
    );
  }

  return (
    <div className="voucher-preview" data-testid="voucher-preview">
      <div className="voucher-content" data-testid="voucher-content">
        {/* Header Information */}
        <div className="voucher-section header-section">
          <h2>Voucher Preview</h2>
          <div className="header-info">
            <div className="info-row">
              <span className="label">Vendor:</span>
              <span className="value" data-testid="vendor-name">
                {preview.vendor_name || 'N/A'}
              </span>
            </div>
            <div className="info-row">
              <span className="label">Invoice #:</span>
              <span className="value" data-testid="invoice-number">
                {preview.invoice_number || 'N/A'}
              </span>
            </div>
            <div className="info-row">
              <span className="label">Invoice Date:</span>
              <span className="value" data-testid="invoice-date">
                {preview.invoice_date || 'N/A'}
              </span>
            </div>
            <div className="info-row">
              <span className="label">Currency:</span>
              <span className="value">{preview.currency || 'N/A'}</span>
            </div>
          </div>
        </div>

        {/* Line Items Table */}
        {preview.line_items && preview.line_items.length > 0 && (
          <div className="voucher-section line-items-section">
            <h3>Line Items</h3>
            <table className="line-items-table" data-testid="line-items-table">
              <thead>
                <tr>
                  <th>Description</th>
                  <th>Quantity</th>
                  <th>Unit</th>
                  <th>Unit Price</th>
                  <th>Line Total</th>
                </tr>
              </thead>
              <tbody>
                {preview.line_items.map((item) => (
                  <tr key={item.line_item_id}>
                    <td>{item.description || ''}</td>
                    <td className="text-right">{item.quantity || ''}</td>
                    <td>{item.unit || ''}</td>
                    <td className="text-right">{item.unit_price || ''}</td>
                    <td className="text-right">{item.line_total || ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Totals Section */}
        <div className="voucher-section totals-section">
          <div className="total-row">
            <span className="label">Subtotal:</span>
            <span className="value" data-testid="subtotal">
              {preview.subtotal || '0.00'}
            </span>
          </div>
          {preview.tax_amount && preview.tax_amount !== '0.00' && (
            <div className="total-row">
              <span className="label">Tax Amount:</span>
              <span className="value">{preview.tax_amount}</span>
            </div>
          )}
          {preview.fee_amount && preview.fee_amount !== '0.00' && (
            <div className="total-row">
              <span className="label">Fee Amount:</span>
              <span className="value">{preview.fee_amount}</span>
            </div>
          )}
          {preview.rounding_adj && preview.rounding_adj !== '0.00' && (
            <div className="total-row">
              <span className="label">Rounding Adjustment:</span>
              <span className="value">{preview.rounding_adj}</span>
            </div>
          )}
          <div className="total-row total-amount">
            <span className="label">Total:</span>
            <span className="value" data-testid="total-amount">
              {preview.total_amount || '0.00'}
            </span>
          </div>
        </div>

        {/* Payment Details Section */}
        {(preview.bank_account_number || preview.bank_name || preview.payment_reference) && (
          <div className="voucher-section payment-section">
            <h3>Payment Details</h3>
            <div className="payment-info">
              {preview.bank_account_number && (
                <div className="info-row">
                  <span className="label">Bank Account:</span>
                  <span className="value">{preview.bank_account_number}</span>
                </div>
              )}
              {preview.bank_name && (
                <div className="info-row">
                  <span className="label">Bank Name:</span>
                  <span className="value">{preview.bank_name}</span>
                </div>
              )}
              {preview.payment_reference && (
                <div className="info-row">
                  <span className="label">Payment Reference:</span>
                  <span className="value">{preview.payment_reference}</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Authorization Disclaimer */}
        <div className="voucher-section disclaimer-section">
          <div className="disclaimer" data-testid="authorization-disclaimer">
            <strong>Authorization Disclaimer:</strong>
            <p>{preview.authorization_disclaimer}</p>
          </div>
        </div>

        {/* Generated At */}
        <div className="voucher-footer">
          <p className="generated-at">
            Generated at: {new Date(preview.generated_at).toLocaleString()}
          </p>
        </div>
      </div>
    </div>
  );
};

export default VoucherPreview;
