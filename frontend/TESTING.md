# Testing Guide for ExceptionPanel and ReviewWorkspace Components

## Setup

To run the unit tests for the ExceptionPanel and ReviewWorkspace components, install the required testing dependencies:

```bash
npm install --save-dev @testing-library/react @testing-library/jest-dom @testing-library/user-event jest @babel/preset-react @babel/preset-typescript ts-jest
```

### Jest Configuration

Create a `jest.config.ts` file in the frontend root:

```typescript
import type { Config } from 'jest';

const config: Config = {
  preset: 'ts-jest',
  testEnvironment: 'jsdom',
  roots: ['<rootDir>/src'],
  testMatch: ['**/__tests__/**/*.ts?(x)', '**/?(*.)+(spec|test).ts?(x)'],
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx'],
  moduleNameMapper: {
    '\\.(css|less|scss|sass)$': 'identity-obj-proxy',
  },
  setupFilesAfterEnv: ['<rootDir>/src/setupTests.ts'],
  collectCoverageFrom: [
    'src/**/*.{ts,tsx}',
    '!src/**/*.d.ts',
    '!src/main.tsx',
  ],
};

export default config;
```

### Setup Tests File

Create `src/setupTests.ts`:

```typescript
import '@testing-library/jest-dom';

// Mock window.matchMedia for responsive design tests
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: jest.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: jest.fn(),
    removeListener: jest.fn(),
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  })),
});
```

### Update package.json

Add test scripts to `package.json`:

```json
{
  "scripts": {
    "test": "jest",
    "test:watch": "jest --watch",
    "test:coverage": "jest --coverage"
  }
}
```

## Running Tests

```bash
# Run all tests
npm test

# Run tests in watch mode
npm run test:watch

# Generate coverage report
npm run test:coverage
```

## Test Files

### ExceptionPanel Tests

Located at: `src/components/ExceptionPanel.test.tsx`

Tests cover:

1. **Rendering**
   - No render when no flags present
   - All active flags rendered with correct styling
   - Color-coded badges applied correctly

2. **MISSING_EVIDENCE Flag**
   - Missing field names displayed
   - Correct instruction text shown

3. **POSSIBLE_DUPLICATE Flag**
   - Matching request details displayed
   - Dismiss button rendered and functional
   - Callback invoked on dismiss

4. **CALC_DISCREPANCY Flag**
   - Discrepancy details shown side-by-side
   - Computed and extracted values displayed

5. **Exception Status**
   - Approval notice displayed in EXCEPTION status
   - Approval notice hidden in READY_FOR_REVIEW status

6. **Multiple Flags**
   - All flags rendered when multiple types present
   - All instructions visible

7. **Edge Cases**
   - Empty flag details handled gracefully
   - Undefined arrays handled safely

Run tests:

```bash
npm test -- ExceptionPanel.test.tsx
```

## Example: Adding Integration Tests

Create `src/components/__tests__/ExceptionPanel.integration.test.tsx`:

```typescript
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ExceptionPanel } from '../ExceptionPanel';
import { ReviewWorkspace } from '../ReviewWorkspace';
import { Request, FlagType } from '../../types';

describe('ExceptionPanel Integration Tests', () => {
  describe('Integration with ReviewWorkspace', () => {
    it('should prevent approval when EXCEPTION flags are present', async () => {
      const mockRequest: Request = {
        request_id: 'req-001',
        client_id: 'client-001',
        client_name: 'Test Client',
        vendor_name: 'Test Vendor',
        invoice_number: 'INV-001',
        status: 'EXCEPTION',
        flags: ['MISSING_EVIDENCE'],
        flag_details: [
          {
            flag_type: 'MISSING_EVIDENCE',
            missing_fields: ['bank_account_number'],
          },
        ],
        created_at: '2025-01-15T10:00:00Z',
        uploader_id: 'user-001',
      };

      const mockOnApprove = jest.fn();

      render(
        <ReviewWorkspace
          request={mockRequest}
          onApprove={mockOnApprove}
        />
      );

      // ExceptionPanel should be displayed
      expect(screen.getByText('Missing Evidence')).toBeInTheDocument();
      expect(screen.getByText(/Approval is disabled/i)).toBeInTheDocument();

      // Approve button should be disabled
      const approveButton = screen.getByRole('button', { name: /Approve/i });
      expect(approveButton).toBeDisabled();

      // Clicking disabled button should not call handler
      fireEvent.click(approveButton);
      expect(mockOnApprove).not.toHaveBeenCalled();
    });

    it('should enable approval when no EXCEPTION flags are present', () => {
      const mockRequest: Request = {
        request_id: 'req-001',
        client_id: 'client-001',
        client_name: 'Test Client',
        vendor_name: 'Test Vendor',
        invoice_number: 'INV-001',
        status: 'READY_FOR_REVIEW',
        flags: [],
        flag_details: [],
        created_at: '2025-01-15T10:00:00Z',
        uploader_id: 'user-001',
      };

      const mockOnApprove = jest.fn();

      render(
        <ReviewWorkspace
          request={mockRequest}
          onApprove={mockOnApprove}
        />
      );

      // ExceptionPanel should not be displayed
      expect(screen.queryByText('Missing Evidence')).not.toBeInTheDocument();

      // Approve button should be enabled
      const approveButton = screen.getByRole('button', { name: /Approve/i });
      expect(approveButton).not.toBeDisabled();

      // Clicking button should call handler
      fireEvent.click(approveButton);
      expect(mockOnApprove).toHaveBeenCalled();
    });
  });

  describe('Multiple Flags Workflow', () => {
    it('should display all flags and their instructions', async () => {
      const mockRequest: Request = {
        request_id: 'req-001',
        client_id: 'client-001',
        client_name: 'Test Client',
        vendor_name: 'Test Vendor',
        invoice_number: 'INV-001',
        status: 'EXCEPTION',
        flags: ['MISSING_EVIDENCE', 'POSSIBLE_DUPLICATE', 'CALC_DISCREPANCY'],
        flag_details: [
          {
            flag_type: 'MISSING_EVIDENCE',
            missing_fields: ['bank_account_number'],
          },
          {
            flag_type: 'POSSIBLE_DUPLICATE',
            matching_requests: [
              {
                request_id: 'req-002',
                status: 'AMIGA_REVIEWED',
                invoice_date: '2025-01-14',
                total_amount: 5000,
              },
            ],
          },
          {
            flag_type: 'CALC_DISCREPANCY',
            discrepancies: [
              {
                field_name: 'total_amount',
                computed: 5100,
                extracted: 5050,
              },
            ],
          },
        ],
        created_at: '2025-01-15T10:00:00Z',
        uploader_id: 'user-001',
      };

      render(
        <ReviewWorkspace request={mockRequest} />
      );

      // All flags should be visible
      await waitFor(() => {
        expect(screen.getByText('Missing Evidence')).toBeInTheDocument();
        expect(screen.getByText('Possible Duplicate')).toBeInTheDocument();
        expect(screen.getByText('Calculation Discrepancy')).toBeInTheDocument();
      });

      // All instructions should be visible
      expect(screen.getByText(/Supply the missing field values/i)).toBeInTheDocument();
      expect(screen.getByText(/Compare this request/i)).toBeInTheDocument();
      expect(screen.getByText(/Correct the identified inconsistent value/i)).toBeInTheDocument();

      // Matching request should be linked
      expect(screen.getByText('req-002')).toBeInTheDocument();
    });
  });
});
```

## Testing Best Practices

1. **Isolation**: Each test should be independent and not rely on other tests
2. **Descriptive Names**: Use clear, descriptive test names that explain what is being tested
3. **Arrange-Act-Assert**: Structure tests with clear setup, action, and verification phases
4. **User-Centric**: Test from the user's perspective, not implementation details
5. **Coverage**: Aim for at least 80% code coverage for UI components

## Debugging Tests

Enable verbose output:

```bash
npm test -- --verbose
```

Debug a specific test:

```bash
npm test -- ExceptionPanel.test.tsx --debug
```

## CI/CD Integration

For GitHub Actions, create `.github/workflows/test.yml`:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-node@v2
        with:
          node-version: '18'
      - run: npm install
      - run: npm test -- --coverage
      - uses: codecov/codecov-action@v2
```

## Troubleshooting

### Module Not Found

Ensure all imports use correct relative paths:

```typescript
// ✓ Correct
import { ExceptionPanel } from '../ExceptionPanel';

// ✗ Incorrect
import { ExceptionPanel } from './ExceptionPanel';
```

### CSS Not Loading in Tests

CSS imports can be mocked in Jest configuration:

```typescript
moduleNameMapper: {
  '\\.(css|less|scss)$': 'identity-obj-proxy',
}
```

### Async Test Timeouts

For async tests, ensure proper waiting:

```typescript
import { waitFor } from '@testing-library/react';

it('should load data', async () => {
  render(<Component />);
  
  await waitFor(() => {
    expect(screen.getByText('Loaded')).toBeInTheDocument();
  }, { timeout: 3000 });
});
```

## Additional Resources

- [React Testing Library Docs](https://testing-library.com/docs/react-testing-library/intro/)
- [Jest Documentation](https://jestjs.io/docs/getting-started)
- [Testing React Components Best Practices](https://kentcdodds.com/blog/common-mistakes-with-react-testing-library)
