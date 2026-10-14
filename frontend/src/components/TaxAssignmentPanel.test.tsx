/**
 * Unit tests for TaxAssignmentPanel component.
 * Tests rendering, user interactions, and tax assignment functionality.
 *
 * Validates Requirements 21.1, 21.3, 21.7
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TaxAssignmentPanel } from "./TaxAssignmentPanel";
import { IndonesianTaxType, LineItem } from "../types/tax";
import * as useTaxAssignmentModule from "../hooks/useTaxAssignment";

// Mock the useTaxAssignment hook
vi.mock("../hooks/useTaxAssignment");

const mockLineItems: LineItem[] = [
  {
    line_item_id: "line-1",
    description: "Software License",
    quantity: 1,
    unit: "lot",
    unit_price: 1000000,
    line_total: 1000000,
  },
  {
    line_item_id: "line-2",
    description: "Support Services",
    quantity: 12,
    unit: "month",
    unit_price: 50000,
    line_total: 600000,
  },
];

describe("TaxAssignmentPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Requirement 21.1: Tax Type Selector Display", () => {
    it("should render a dropdown selector for each line item", () => {
      const mockAssignTax = vi.fn();
      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: null,
        assignTax: mockAssignTax,
        getTaxSummary: vi.fn(),
      });

      render(
        <TaxAssignmentPanel
          requestId="req-1"
          lineItems={mockLineItems}
          isLocked={false}
        />
      );

      // Find both selectors
      const selectors = screen.getAllByRole("combobox");
      expect(selectors).toHaveLength(2);
    });

    it("should show all tax type options in the dropdown", () => {
      const mockAssignTax = vi.fn();
      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: null,
        assignTax: mockAssignTax,
        getTaxSummary: vi.fn(),
      });

      render(
        <TaxAssignmentPanel
          requestId="req-1"
          lineItems={[mockLineItems[0]]}
          isLocked={false}
        />
      );

      const selector = screen.getByRole("combobox");
      fireEvent.click(selector);

      // Check for all tax type options
      expect(screen.getByText("PPh 21 (5%)")).toBeTruthy();
      expect(screen.getByText("PPh 22 (1.5%)")).toBeTruthy();
      expect(screen.getByText("PPh 23 (2%)")).toBeTruthy();
      expect(screen.getByText("PPh 25 (2%)")).toBeTruthy();
      expect(screen.getByText("PPN (11%)")).toBeTruthy();
      expect(screen.getByText("No Tax")).toBeTruthy();
    });

    it("should display line item information in the table", () => {
      const mockAssignTax = vi.fn();
      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: null,
        assignTax: mockAssignTax,
        getTaxSummary: vi.fn(),
      });

      render(
        <TaxAssignmentPanel
          requestId="req-1"
          lineItems={mockLineItems}
          isLocked={false}
        />
      );

      // Check for line item descriptions
      expect(screen.getByText("Software License")).toBeTruthy();
      expect(screen.getByText("Support Services")).toBeTruthy();
    });
  });

  describe("Requirement 21.3: Computed Tax Amount Display", () => {
    it("should display computed tax amount after tax type selection", async () => {
      const mockAssignTax = vi.fn().mockResolvedValue({
        line_item_id: "line-1",
        tax_type: IndonesianTaxType.PPH21,
        tax_rate: "0.0500",
        tax_amount: "50000",
      });

      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: null,
        assignTax: mockAssignTax,
        getTaxSummary: vi.fn(),
      });

      render(
        <TaxAssignmentPanel
          requestId="req-1"
          lineItems={mockLineItems}
          isLocked={false}
        />
      );

      const selectors = screen.getAllByRole("combobox");
      await userEvent.selectOptions(selectors[0], IndonesianTaxType.PPH21);

      await waitFor(() => {
        expect(mockAssignTax).toHaveBeenCalledWith(
          "req-1",
          "line-1",
          IndonesianTaxType.PPH21
        );
      });
    });

    it("should call onTaxAssigned callback with computed tax amount", async () => {
      const mockOnTaxAssigned = vi.fn();
      const mockAssignTax = vi.fn().mockResolvedValue({
        line_item_id: "line-1",
        tax_type: IndonesianTaxType.PPH22,
        tax_rate: "0.0150",
        tax_amount: "15000",
      });

      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: null,
        assignTax: mockAssignTax,
        getTaxSummary: vi.fn(),
      });

      render(
        <TaxAssignmentPanel
          requestId="req-1"
          lineItems={mockLineItems}
          isLocked={false}
          onTaxAssigned={mockOnTaxAssigned}
        />
      );

      const selectors = screen.getAllByRole("combobox");
      await userEvent.selectOptions(selectors[0], IndonesianTaxType.PPH22);

      await waitFor(() => {
        expect(mockOnTaxAssigned).toHaveBeenCalledWith(
          "line-1",
          IndonesianTaxType.PPH22,
          "15000"
        );
      });
    });
  });

  describe("Requirement 21.7: Request Locked Status", () => {
    it("should disable selectors when request is locked", () => {
      const mockAssignTax = vi.fn();
      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: null,
        assignTax: mockAssignTax,
        getTaxSummary: vi.fn(),
      });

      render(
        <TaxAssignmentPanel
          requestId="req-1"
          lineItems={mockLineItems}
          isLocked={true}
        />
      );

      const selectors = screen.getAllByRole("combobox");
      selectors.forEach((selector) => {
        expect((selector as HTMLSelectElement).disabled).toBe(true);
      });
    });

    it("should display locked notice when request is locked", () => {
      const mockAssignTax = vi.fn();
      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: null,
        assignTax: mockAssignTax,
        getTaxSummary: vi.fn(),
      });

      render(
        <TaxAssignmentPanel
          requestId="req-1"
          lineItems={mockLineItems}
          isLocked={true}
        />
      );

      expect(
        screen.getByText(/request is locked/i)
      ).toBeTruthy();
    });

    it("should enable selectors when request is not locked", () => {
      const mockAssignTax = vi.fn();
      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: null,
        assignTax: mockAssignTax,
        getTaxSummary: vi.fn(),
      });

      render(
        <TaxAssignmentPanel
          requestId="req-1"
          lineItems={mockLineItems}
          isLocked={false}
        />
      );

      const selectors = screen.getAllByRole("combobox");
      selectors.forEach((selector) => {
        expect((selector as HTMLSelectElement).disabled).toBe(false);
      });
    });
  });

  describe("Error Handling", () => {
    it("should display error message when tax assignment fails", async () => {
      const mockOnError = vi.fn();
      const mockAssignTax = vi
        .fn()
        .mockRejectedValue(
          new Error("Failed to assign tax")
        );

      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: "Failed to assign tax",
        assignTax: mockAssignTax,
        getTaxSummary: vi.fn(),
      });

      render(
        <TaxAssignmentPanel
          requestId="req-1"
          lineItems={mockLineItems}
          isLocked={false}
          onError={mockOnError}
        />
      );

      // Error message should be displayed
      await waitFor(() => {
        expect(
          screen.getByText(/Failed to assign tax/i)
        ).toBeTruthy();
      });
    });

    it("should handle empty line items gracefully", () => {
      const mockAssignTax = vi.fn();
      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: null,
        assignTax: mockAssignTax,
        getTaxSummary: vi.fn(),
      });

      render(
        <TaxAssignmentPanel
          requestId="req-1"
          lineItems={[]}
          isLocked={false}
        />
      );

      expect(
        screen.getByText(/No line items to display/i)
      ).toBeTruthy();
    });
  });

  describe("Tax Type Selection", () => {
    it("should correctly send PPH21 tax type to API", async () => {
      const mockAssignTax = vi.fn().mockResolvedValue({
        line_item_id: "line-1",
        tax_type: IndonesianTaxType.PPH21,
        tax_rate: "0.0500",
        tax_amount: "50000",
      });

      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: null,
        assignTax: mockAssignTax,
        getTaxSummary: vi.fn(),
      });

      render(
        <TaxAssignmentPanel
          requestId="req-1"
          lineItems={[mockLineItems[0]]}
          isLocked={false}
        />
      );

      const selector = screen.getByRole("combobox");
      await userEvent.selectOptions(selector, IndonesianTaxType.PPH21);

      await waitFor(() => {
        expect(mockAssignTax).toHaveBeenCalledWith(
          "req-1",
          "line-1",
          IndonesianTaxType.PPH21
        );
      });
    });

    it("should correctly send NO_TAX tax type to API", async () => {
      const mockAssignTax = vi.fn().mockResolvedValue({
        line_item_id: "line-1",
        tax_type: IndonesianTaxType.NO_TAX,
        tax_rate: "0.0000",
        tax_amount: "0",
      });

      vi.mocked(useTaxAssignmentModule.useTaxAssignment).mockReturnValue({
        loading: false,
        error: null,
        assignTax: mockAssignTax,
        getTaxSummary: vi.fn(),
      });

      render(
        <TaxAssignmentPanel
          requestId="req-1"
          lineItems={[mockLineItems[0]]}
          isLocked={false}
        />
      );

      const selector = screen.getByRole("combobox");
      await userEvent.selectOptions(selector, IndonesianTaxType.NO_TAX);

      await waitFor(() => {
        expect(mockAssignTax).toHaveBeenCalledWith(
          "req-1",
          "line-1",
          IndonesianTaxType.NO_TAX
        );
      });
    });
  });
});
