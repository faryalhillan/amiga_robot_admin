import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import VoucherPreview from './VoucherPreview';

/**
 * Unit tests for VoucherPreview component.
 *
 * Tests that:
 * - Disclaimer is rendered
 * - All approved fields are displayed
 * - Error message and retry button show on API failure
 *
 * Requirements: 14.2, 14.4
 */

describe('VoucherPreview', () => {
  const mockPreviewData = {
    request_id: '550e8400-e29b-41d4-a716-446655440000',
    vendor_name: 'Vendor ABC',
    invoice_number: 'INV-2024-001',
    invoice_date: '2024-01-15',
    currency: 'USD',
    subtotal: '1000.00',
    total_amount: '1100.00',
    tax_amount: '100.00',
    fee_amount: null,
    rounding_adj: null,
    line_items: [
      {
        line_item_id: '550e8400-e29b-41d4-a716-446655440001',
        sequence_number: 1,
        description: 'Item 1',
        quantity: '5',
        unit: 'pcs',
        unit_price: '100.00',
        line_total: '500.00',
      },
      {
        line_item_id: '550e8400-e29b-41d4-a716-446655440002',
        sequence_number: 2,
        description: 'Item 2',
        quantity: '10',
        unit: 'pcs',
        unit_price: '50.00',
        line_total: '500.00',
      },
    ],
    bank_account_number: '1234567890',
    bank_name: 'Test Bank',
    payment_reference: 'PAY-REF-001',
    authorization_disclaimer:
      'This voucher is prepared for client review purposes only. Payment authorization remains with the client.',
    generated_at: '2024-01-20T10:30:00Z',
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders disclaimer prominently', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockPreviewData),
      })
    ) as any;

    render(<VoucherPreview requestId="550e8400-e29b-41d4-a716-446655440000" />);

    await waitFor(() => {
      const disclaimer = screen.getByTestId('authorization-disclaimer');
      expect(disclaimer).toBeInTheDocument();
      expect(disclaimer.textContent).toContain('Authorization Disclaimer');
      expect(disclaimer.textContent).toContain('Payment authorization remains with the client');
    });
  });

  it('displays all approved header fields', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockPreviewData),
      })
    ) as any;

    render(<VoucherPreview requestId="550e8400-e29b-41d4-a716-446655440000" />);

    await waitFor(() => {
      expect(screen.getByTestId('vendor-name')).toHaveTextContent('Vendor ABC');
      expect(screen.getByTestId('invoice-number')).toHaveTextContent('INV-2024-001');
      expect(screen.getByTestId('invoice-date')).toHaveTextContent('2024-01-15');
      expect(screen.getByTestId('subtotal')).toHaveTextContent('1000.00');
      expect(screen.getByTestId('total-amount')).toHaveTextContent('1100.00');
    });
  });

  it('displays all line items in a table', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockPreviewData),
      })
    ) as any;

    render(<VoucherPreview requestId="550e8400-e29b-41d4-a716-446655440000" />);

    await waitFor(() => {
      const table = screen.getByTestId('line-items-table');
      expect(table).toBeInTheDocument();

      // Verify line items are in the table
      expect(screen.getByText('Item 1')).toBeInTheDocument();
      expect(screen.getByText('Item 2')).toBeInTheDocument();
      expect(screen.getByText('500.00')).toBeInTheDocument(); // Line total
    });
  });

  it('displays payment details', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockPreviewData),
      })
    ) as any;

    render(<VoucherPreview requestId="550e8400-e29b-41d4-a716-446655440000" />);

    await waitFor(() => {
      expect(screen.getByText('1234567890')).toBeInTheDocument();
      expect(screen.getByText('Test Bank')).toBeInTheDocument();
      expect(screen.getByText('PAY-REF-001')).toBeInTheDocument();
    });
  });

  it('shows error message when API returns an error', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
      })
    ) as any;

    render(<VoucherPreview requestId="550e8400-e29b-41d4-a716-446655440000" />);

    await waitFor(() => {
      expect(screen.getByTestId('error-message')).toBeInTheDocument();
      expect(screen.getByText(/Failed to load preview/)).toBeInTheDocument();
    });
  });

  it('shows retry button on API failure', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
      })
    ) as any;

    render(<VoucherPreview requestId="550e8400-e29b-41d4-a716-446655440000" />);

    await waitFor(() => {
      expect(screen.getByTestId('retry-button')).toBeInTheDocument();
    });
  });

  it('retries the API call when retry button is clicked', async () => {
    let callCount = 0;

    global.fetch = vi.fn(() => {
      callCount += 1;
      if (callCount === 1) {
        // First call: return error
        return Promise.resolve({
          ok: false,
          status: 500,
          statusText: 'Internal Server Error',
        });
      } else {
        // Second call: return success
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockPreviewData),
        });
      }
    }) as any;

    render(<VoucherPreview requestId="550e8400-e29b-41d4-a716-446655440000" />);

    // First wait for error to appear
    await waitFor(() => {
      expect(screen.getByTestId('retry-button')).toBeInTheDocument();
    });

    // Click retry
    const retryButton = screen.getByTestId('retry-button');
    await userEvent.click(retryButton);

    // Wait for successful load
    await waitFor(() => {
      expect(screen.getByTestId('vendor-name')).toHaveTextContent('Vendor ABC');
    });
  });

  it('handles 404 error specifically', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 404,
        statusText: 'Not Found',
      })
    ) as any;

    render(<VoucherPreview requestId="550e8400-e29b-41d4-a716-446655440000" />);

    await waitFor(() => {
      expect(screen.getByText('Request not found.')).toBeInTheDocument();
    });
  });

  it('handles 403 authorization error specifically', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 403,
        statusText: 'Forbidden',
      })
    ) as any;

    render(<VoucherPreview requestId="550e8400-e29b-41d4-a716-446655440000" />);

    await waitFor(() => {
      expect(screen.getByText('You are not authorized to view this voucher preview.')).toBeInTheDocument();
    });
  });

  it('handles 400 status error (request not approved)', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
      })
    ) as any;

    render(<VoucherPreview requestId="550e8400-e29b-41d4-a716-446655440000" />);

    await waitFor(() => {
      expect(screen.getByText(/Failed to load preview/)).toBeInTheDocument();
    });
  });

  it('handles network errors', async () => {
    global.fetch = vi.fn(() =>
      Promise.reject(new Error('Network error'))
    ) as any;

    render(<VoucherPreview requestId="550e8400-e29b-41d4-a716-446655440000" />);

    await waitFor(() => {
      expect(screen.getByText(/Network error/)).toBeInTheDocument();
    });
  });

  it('renders read-only layout without edit controls', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockPreviewData),
      })
    ) as any;

    const { container } = render(
      <VoucherPreview requestId="550e8400-e29b-41d4-a716-446655440000" />
    );

    await waitFor(() => {
      // Verify no input elements are present
      const inputs = container.querySelectorAll('input');
      expect(inputs.length).toBe(0);

      // Verify no edit buttons are present
      const buttons = container.querySelectorAll('button');
      // Only retry button if there's an error, otherwise no buttons
      expect(buttons.length).toBeLessThanOrEqual(0);
    });
  });

  it('displays loading state initially', () => {
    global.fetch = vi.fn(() =>
      new Promise(() => {
        /* Never resolves to keep loading state */
      })
    ) as any;

    render(<VoucherPreview requestId="550e8400-e29b-41d4-a716-446655440000" />);

    expect(screen.getByText('Loading voucher preview...')).toBeInTheDocument();
  });

  it('displays formatted generated timestamp', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockPreviewData),
      })
    ) as any;

    render(<VoucherPreview requestId="550e8400-e29b-41d4-a716-446655440000" />);

    await waitFor(() => {
      expect(screen.getByText(/Generated at:/)).toBeInTheDocument();
    });
  });
});
