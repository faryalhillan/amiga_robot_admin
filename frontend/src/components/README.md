# Frontend Components

## ExceptionPanel Component

The `ExceptionPanel` component displays all active exception flags with visual distinction, per-flag instructions, and actionable next steps for Finance Reviewers.

### Features

- **Visual Distinction**: Color-coded badges and icons for each flag type
  - Red (#dc3545) for MISSING_EVIDENCE
  - Orange (#ff8c00) for POSSIBLE_DUPLICATE
  - Yellow (#ffc107) for CALC_DISCREPANCY

- **Per-Flag Instructions**:
  - MISSING_EVIDENCE: "Supply the missing field values: [list of field names]"
  - POSSIBLE_DUPLICATE: "Compare this request with the matching request(s): [request_id, status, invoice_date, total_amount]"
  - CALC_DISCREPANCY: "Correct the inconsistent value(s). Computed vs Extracted: [show discrepancies side-by-side]"

- **Approval Prevention**: Displays a notice when Request is in EXCEPTION status preventing approval
- **Dismiss Capability**: POSSIBLE_DUPLICATE flags can be dismissed if identified as false positives
- **Responsive Design**: Adapts layout for mobile, tablet, and desktop screens

### Props

```typescript
interface ExceptionPanelProps {
  flags: FlagType[];                    // List of active flag types
  flagDetails: FlagDetail[];            // Details for each flag
  requestStatus: 'EXCEPTION' | 'READY_FOR_REVIEW';  // Current request status
  onDismissFlag?: (flagType: FlagType) => void;     // Callback to dismiss a flag
}
```

### Usage Example

```tsx
import { ExceptionPanel } from './components/ExceptionPanel';
import { FlagType, FlagDetail } from './types';

function RequestDetail() {
  const [flags, setFlags] = useState<FlagType[]>(['MISSING_EVIDENCE']);
  const [flagDetails, setFlagDetails] = useState<FlagDetail[]>([
    {
      flag_type: 'MISSING_EVIDENCE',
      missing_fields: ['bank_account_number', 'bank_name'],
    },
  ]);

  const handleDismissFlag = async (flagType: FlagType) => {
    if (flagType === 'POSSIBLE_DUPLICATE') {
      // Call API to dismiss the flag
      await api.post(`/requests/${requestId}/dismiss-duplicate`);
      // Update local state
      setFlags(flags.filter(f => f !== flagType));
    }
  };

  return (
    <ExceptionPanel
      flags={flags}
      flagDetails={flagDetails}
      requestStatus="EXCEPTION"
      onDismissFlag={handleDismissFlag}
    />
  );
}
```

### Data Structures

#### FlagDetail Structure

```typescript
interface FlagDetail {
  flag_type: FlagType;
  missing_fields?: string[];              // For MISSING_EVIDENCE
  matching_requests?: MatchingRequestRef[]; // For POSSIBLE_DUPLICATE
  discrepancies?: CalculationDiscrepancy[];  // For CALC_DISCREPANCY
  details?: Record<string, any>;            // For any additional info
}

interface MatchingRequestRef {
  request_id: string;
  status: RequestStatus;
  invoice_date: string;
  total_amount: number | string;
}

interface CalculationDiscrepancy {
  field_name: string;
  computed: number | string;
  extracted: number | string;
}
```

## ReviewWorkspace Component

The `ReviewWorkspace` component provides a two-panel layout for reviewing invoices with the ExceptionPanel prominently displayed for any active flags.

### Features

- **Two-Panel Layout**: PDF viewer (left) and editable form (right)
- **Persistent AI Label**: "AI-generated draft — not approved" label always visible
- **Original Value Display**: Shows original extracted values inline with editable fields
- **Unsaved Changes Warning**: Prompts user before navigating away with unsaved changes
- **Approval Prevention**: Disables/hides approve button when Request is in EXCEPTION status
- **Exception Panel Integration**: Displays ExceptionPanel prominently at the top

### Props

```typescript
interface ReviewWorkspaceProps {
  request: Request;
  onApprove?: () => void;
  onReject?: () => void;
  onFieldChange?: (fieldPath: string, newValue: any) => void;
}
```

### Usage Example

```tsx
import { ReviewWorkspace } from './components/ReviewWorkspace';
import { Request } from './types';

function ReviewPage() {
  const [request, setRequest] = useState<Request | null>(null);

  const handleApprove = async () => {
    if (request?.status === 'EXCEPTION') {
      alert('Cannot approve - resolve all exceptions first');
      return;
    }
    // Call API to approve
    await api.post(`/requests/${request?.request_id}/approve`);
  };

  if (!request) return <div>Loading...</div>;

  return (
    <ReviewWorkspace
      request={request}
      onApprove={handleApprove}
      onReject={() => console.log('Reject clicked')}
      onFieldChange={(fieldPath, value) => console.log(fieldPath, value)}
    />
  );
}
```

## Integration with Backend API

The ExceptionPanel expects flag details from the backend API's response to `GET /requests/{id}`:

```typescript
// Expected API Response
{
  request_id: "uuid",
  status: "EXCEPTION",
  flags: ["MISSING_EVIDENCE", "POSSIBLE_DUPLICATE"],
  flag_details: [
    {
      flag_type: "MISSING_EVIDENCE",
      missing_fields: ["bank_account_number", "payment_reference"]
    },
    {
      flag_type: "POSSIBLE_DUPLICATE",
      matching_requests: [
        {
          request_id: "req-001",
          status: "AMIGA_REVIEWED",
          invoice_date: "2025-01-15",
          total_amount: 5000.00
        }
      ]
    }
  ]
}
```

## Testing

Unit tests are provided in `ExceptionPanel.test.tsx` covering:

- Rendering of all flag types
- Correct per-flag instructions displayed
- Color-coded visual styling applied
- Dismiss button functionality for POSSIBLE_DUPLICATE
- Approval notice visibility when in EXCEPTION status
- Multiple flags rendering correctly
- Edge cases (empty details, undefined fields)

### Running Tests

```bash
npm test -- ExceptionPanel.test.tsx
```

## Accessibility

The components follow WCAG accessibility guidelines:

- Semantic HTML elements (`<button>`, `<label>`)
- Proper heading hierarchy (`<h2>`, `<h3>`)
- Descriptive button titles for icon-only buttons
- Color + icons used together for distinction (not color alone)
- Responsive design works with assistive technologies
- Focus states clearly visible on interactive elements

## Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Requirements Validation

The ExceptionPanel component validates the following requirements:

- **Requirement 9.1**: Displays all active flags (MISSING_EVIDENCE, POSSIBLE_DUPLICATE, CALC_DISCREPANCY)
- **Requirement 9.2**: Visually distinguishes flagged fields with color/icon and labels them with flag identifier
- **Requirement 9.3**: Shows per-flag next-action instructions:
  - MISSING_EVIDENCE: instructs to supply missing field values
  - POSSIBLE_DUPLICATE: instructs to compare with matching request
  - CALC_DISCREPANCY: instructs to correct inconsistent values
- **Requirement 9.4**: Prevents voucher generation (approval button disabled/hidden) while EXCEPTION flags are active

The ReviewWorkspace component validates:

- **Requirement 10.1**: Two-panel layout with both panels simultaneously visible
- **Requirement 10.2**: Review workspace loads and renders within 2 seconds
- **Requirement 10.3**: All Header_Fields, Line_Items, and Payment_Details are editable
- **Requirement 10.4**: Original AI-extracted value displayed adjacent to edit control
- **Requirement 10.6**: Confirmation prompt when navigating away with unsaved changes
- **Requirement 4.2**: AI-generated draft label always visible and persistent
