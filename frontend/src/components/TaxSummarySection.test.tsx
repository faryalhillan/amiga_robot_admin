/**
 * Unit tests for TaxSummarySection component.
 * Tests rendering of tax summary, per-type subtotals, and locked status.
 *
 * Validates Requirements 21.4, 21.6, 21.7
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { TaxSummarySection } from "./TaxSummarySection";
import { TaxSummaryResponse } from "../types/tax";
import * as useTaxAssignmentModule from "../hooks/useTaxAssignment";


// Mock the useTaxAssignment hook
vi.mock("../hooks/useTaxAssignment");

const mockTaxSummary: TaxSummaryResponse = {
  line_items: [
    {
      line_item_id: "line-1",
      description: "Software License",
      quantity: 1,
      unit: "lot",
      unit_price: 1000000,
      line_total: 1000000,
      tax_type: "PPH21",
      tax_rate: 0.05,
      tax_amount: 50000,
    },
    {
      line_item_id: "line-2",
      description: "Support Services",
      quantity: 12,
      unit: "month",
      unit_price: 50000,
      line_total: 600000,
      tax_type: "PPN",
      tax_rate: 0.11,
      tax_amount: 66000,
    },
  ],
  per_type_subtotals: {
    PPH21: "50000",
    PPN: "66000",
  },
  total_tax: "116000",
  grand_total: "1716000",
  locked: false,
};

describe("TaxSummarySection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Requirement 21.4: Tax Summary Display", () => {
    it("should display per-type subtotals", async () => {
      const mockGetTaxSummary = vi
        .fn()
        .mockResolvedValue(mockTaxSummary);

      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: null,
        assignTax: vi.fn(),
        getTaxSummary: mockGetTaxSummary,
      });

      render(
        <TaxSummarySection requestId="req-1" />
      );

      await waitFor(() => {
        expect(screen.getByText("PPH21")).toBeTruthy();
        expect(screen.getByText("PPN")).toBeTruthy();
      });
    });

    it("should display grand total", async () => {
      const mockGetTaxSummary = vi
        .fn()
        .mockResolvedValue(mockTaxSummary);

      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: null,
        assignTax: vi.fn(),
        getTaxSummary: mockGetTaxSummary,
      });

      render(
        <TaxSummarySection requestId="req-1" />
      );

      await waitFor(() => {
        expect(screen.getByText(/Grand Total:/)).toBeTruthy();
      });
    });

    it("should display total tax amount", async () => {
      const mockGetTaxSummary = vi
        .fn()
        .mockResolvedValue(mockTaxSummary);

      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: null,
        assignTax: vi.fn(),
        getTaxSummary: mockGetTaxSummary,
      });

      render(
        <TaxSummarySection requestId="req-1" />
      );

      await waitFor(() => {
        expect(screen.getByText(/Total Tax:/)).toBeTruthy();
      });
    });
  });

  describe("Requirement 21.6: Tax Summary on Request Detail", () => {
    it("should fetch tax summary for the given request ID", async () => {
      const mockGetTaxSummary = vi
        .fn()
        .mockResolvedValue(mockTaxSummary);

      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: null,
        assignTax: vi.fn(),
        getTaxSummary: mockGetTaxSummary,
      });

      render(
        <TaxSummarySection requestId="req-123" />
      );

      await waitFor(() => {
        expect(mockGetTaxSummary).toHaveBeenCalledWith("req-123");
      });
    });

    it("should refetch when refresh trigger changes", async () => {
      const mockGetTaxSummary = vi
        .fn()
        .mockResolvedValue(mockTaxSummary);

      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: null,
        assignTax: vi.fn(),
        getTaxSummary: mockGetTaxSummary,
      });

      const { rerender } = render(
        <TaxSummarySection requestId="req-1" refreshTrigger={0} />
      );

      await waitFor(() => {
        expect(mockGetTaxSummary).toHaveBeenCalledWith("req-1");
      });

      rerender(
        <TaxSummarySection requestId="req-1" refreshTrigger={1} />
      );

      await waitFor(() => {
        expect(mockGetTaxSummary).toHaveBeenCalledTimes(2);
      });
    });
  });

  describe("Requirement 21.7: Locked Request Status", () => {
    it("should display locked indicator when locked is true", async () => {
      const mockGetTaxSummary = vi.fn().mockResolvedValue({
        ...mockTaxSummary,
        locked: true,
      });

      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: null,
        assignTax: vi.fn(),
        getTaxSummary: mockGetTaxSummary,
      });

      render(
        <TaxSummarySection requestId="req-1" />
      );

      await waitFor(() => {
        expect(screen.getByText(/Locked/)).toBeTruthy();
      });
    });

    it("should display locked notice when request is locked", async () => {
      const mockGetTaxSummary = vi.fn().mockResolvedValue({
        ...mockTaxSummary,
        locked: true,
      });

      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: null,
        assignTax: vi.fn(),
        getTaxSummary: mockGetTaxSummary,
      });

      render(
        <TaxSummarySection requestId="req-1" />
      );

      await waitFor(() => {
        expect(
          screen.getByText(/request is locked/i)
        ).toBeTruthy();
      });
    });

    it("should not show locked notice when request is not locked", async () => {
      const mockGetTaxSummary = vi.fn().mockResolvedValue({
        ...mockTaxSummary,
        locked: false,
      });

      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: null,
        assignTax: vi.fn(),
        getTaxSummary: mockGetTaxSummary,
      });

      render(
        <TaxSummarySection requestId="req-1" />
      );

      await waitFor(() => {
        expect(
          screen.queryByText(/request is locked/i)
        ).not.toBeTruthy();
      });
    });
  });

  describe("Error Handling", () => {
    it("should display error message when fetch fails", async () => {
      const mockGetTaxSummary = vi
        .fn()
        .mockRejectedValue(new Error("Network error"));

      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: "Failed to fetch tax summary",
        assignTax: vi.fn(),
        getTaxSummary: mockGetTaxSummary,
      });

      render(
        <TaxSummarySection requestId="req-1" />
      );

      await waitFor(() => {
        expect(
          screen.getByText(/Failed to fetch tax summary/i)
        ).toBeTruthy();
      });
    });

    it("should call onError callback when error occurs", async () => {
      const mockOnError = vi.fn();
      const mockGetTaxSummary = vi
        .fn()
        .mockRejectedValue(new Error("Network error"));

      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: "Failed to fetch tax summary",
        assignTax: vi.fn(),
        getTaxSummary: mockGetTaxSummary,
      });

      render(
        <TaxSummarySection
          requestId="req-1"
          onError={mockOnError}
        />
      );

      await waitFor(() => {
        expect(mockOnError).toHaveBeenCalledWith(
          "Failed to fetch tax summary"
        );
      });
    });

    it("should display loading message initially", () => {
      const mockGetTaxSummary = vi
        .fn()
        .mockResolvedValue(mockTaxSummary);

      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: true,
        error: null,
        assignTax: vi.fn(),
        getTaxSummary: mockGetTaxSummary,
      });

      render(
        <TaxSummarySection requestId="req-1" />
      );

      expect(
        screen.getByText(/Loading tax summary/i)
      ).toBeTruthy();
    });
  });

  describe("Empty State", () => {
    it("should handle empty tax summary gracefully", async () => {
      const mockGetTaxSummary = vi.fn().mockResolvedValue({
        line_items: [],
        per_type_subtotals: {},
        total_tax: "0",
        grand_total: "0",
        locked: false,
      });

      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: null,
        assignTax: vi.fn(),
        getTaxSummary: mockGetTaxSummary,
      });

      render(
        <TaxSummarySection requestId="req-1" />
      );

      await waitFor(() => {
        expect(
          screen.getByText(/No tax assignments yet/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Multiple Tax Types", () => {
    it("should display all assigned tax types in summary", async () => {
      const mockGetTaxSummary = vi.fn().mockResolvedValue({
        ...mockTaxSummary,
        per_type_subtotals: {
          PPH21: "50000",
          PPH22: "15000",
          PPH23: "20000",
          PPH25: "20000",
          PPN: "66000",
        },
      });

      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: null,
        assignTax: vi.fn(),
        getTaxSummary: mockGetTaxSummary,
      });

      render(
        <TaxSummarySection requestId="req-1" />
      );

      await waitFor(() => {
        expect(screen.getByText("PPH21")).toBeTruthy();
        expect(screen.getByText("PPH22")).toBeTruthy();
        expect(screen.getByText("PPH23")).toBeTruthy();
        expect(screen.getByText("PPH25")).toBeTruthy();
        expect(screen.getByText("PPN")).toBeTruthy();
      });
    });
  });
});
