# Task 31: Checkpoint — Full Handover Flow

## Objective
Verify the complete PDF generation and delivery workflow:
1. Approve a request (transition to `AMIGA_REVIEWED`)
2. Generate PDF via `POST /requests/{id}/voucher-pdf`
3. Download PDF twice via `GET /requests/{id}/voucher-pdf`
4. Verify exactly one `SENT_TO_CLIENT` event and status change
5. Confirm second download does not create duplicate event

## Requirements Tested
- **15.1, 15.2, 15.6**: PDF generation with disclaimer included
- **16.1, 16.2**: First download → `SENT_TO_CLIENT` event + status change
- **16.4, 16.5**: Audit timestamp displayed on detail screen
- **30.2, 30.3, 30.5**: Download endpoint idempotency (exactly one event for multiple downloads)

## Prerequisites
1. Backend running with Python 3.12+
2. PostgreSQL database initialized with all migrations (`alembic upgrade head`)
3. Real AWS S3 credentials configured (or moto mock)
4. At least one Client created in the database

## Manual Test Steps

### Step 1: Start Backend Server
```bash
cd backend
source venv/bin/activate  # or use Windows equivalent
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Step 2: Create or Identify a Test Client
```bash
curl -X GET http://localhost:8000/clients \
  -H "Authorization: Bearer <SYSTEM_ADMIN_TOKEN>"
```

Note the `client_id` of an existing client or create one:
```bash
curl -X POST http://localhost:8000/clients \
  -H "Authorization: Bearer <SYSTEM_ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"client_name": "Test Client for Checkpoint 31"}'
```

### Step 3: Create or Setup a Test Request in READY_FOR_REVIEW Status

Option A: Upload a test invoice via `POST /requests` to create a QUEUED request:
```bash
curl -X POST http://localhost:8000/requests \
  -H "Authorization: Bearer <CLIENT_PIC_TOKEN>" \
  -F "files=@/path/to/test_invoice.pdf" \
  -F "client_id=<CLIENT_ID>" \
  -F "request_date=2024-01-15" \
  -F "request_type=standard" \
  -F "channel=upload"
```

Wait for the extraction job to complete (check logs or poll the request status).

Option B: Create a request directly in the database at READY_FOR_REVIEW status:
```sql
-- Using PostgreSQL psql client
INSERT INTO invoiceRequest (request_id, client_id, uploader_id, request_type, channel, request_date, status, flags, invoice_file_key, invoice_page_count, created_at, updated_at)
VALUES (
  'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'::uuid,  -- Generate a UUID
  '<CLIENT_ID>'::uuid,
  '<UPLOADER_ID>'::uuid,
  'standard',
  'upload',
  '2024-01-15',
  'READY_FOR_REVIEW',
  '{}',
  'evidence/test/1_invoice.pdf',
  1,
  NOW(),
  NOW()
);

-- Also create minimal draft and fields (see schema)
```

### Step 4: Transition Request to AMIGA_REVIEWED

Use the new approval endpoint (now implemented):

```bash
curl -X POST http://localhost:8000/requests/<REQUEST_ID>/approve \
  -H "Authorization: Bearer <FINANCE_REVIEWER_TOKEN>" \
  -H "Content-Type: application/json"
```

Expected response:
```json
{
  "request_id": "<REQUEST_ID>",
  "status": "AMIGA_REVIEWED",
  "approved_at": "2024-01-15T10:25:30.123456Z"
}
```

This endpoint:
- Checks that the Finance Reviewer has an active client assignment
- Enforces segregation of duties (user cannot approve their own upload)
- Rejects approval if there are active EXCEPTION flags
- Transitions status from `READY_FOR_REVIEW` to `AMIGA_REVIEWED`
- Logs both `APPROVED` and `STATUS_CHANGED` audit events

**Verify the status changed:**
```bash
curl -X GET http://localhost:8000/requests/<REQUEST_ID> \
  -H "Authorization: Bearer <FINANCE_REVIEWER_TOKEN>"
```

Expected response includes `"status": "AMIGA_REVIEWED"`.

### Step 5: Generate Voucher PDF

```bash
curl -X POST http://localhost:8000/requests/<REQUEST_ID>/voucher-pdf \
  -H "Authorization: Bearer <CLIENT_PIC_TOKEN>"
```

Expected response:
```json
{
  "voucher_pdf_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "file_key": "vouchers/<REQUEST_ID>/voucher.pdf",
  "generated_at": "2024-01-15T10:30:45.123456Z"
}
```

### Step 6: Download PDF — First Time

```bash
curl -X GET http://localhost:8000/requests/<REQUEST_ID>/voucher-pdf \
  -H "Authorization: Bearer <CLIENT_PIC_TOKEN>" \
  -o /tmp/voucher_first_download.pdf
```

Expected:
- HTTP 200
- Binary PDF content streamed
- Request status transitions to `SENT_TO_CLIENT`
- Two new AuditEvents created: `VOUCHER_DOWNLOADED` and `STATUS_CHANGED`

**Verify status changed:**
```bash
curl -X GET http://localhost:8000/requests/<REQUEST_ID> \
  -H "Authorization: Bearer <CLIENT_PIC_TOKEN>"
```

Expected response includes `"status": "SENT_TO_CLIENT"`.

### Step 7: Download PDF — Second Time

```bash
curl -X GET http://localhost:8000/requests/<REQUEST_ID>/voucher-pdf \
  -H "Authorization: Bearer <CLIENT_PIC_TOKEN>" \
  -o /tmp/voucher_second_download.pdf
```

Expected:
- HTTP 200
- Binary PDF content streamed (identical to first download)
- **NO new AuditEvents created** (idempotency check)
- Request status remains `SENT_TO_CLIENT`

### Step 8: Verify Audit Trail

Query the audit trail to confirm exactly one `SENT_TO_CLIENT`-related event:

```sql
SELECT event_id, event_type, occurred_at, payload
FROM auditEvent
WHERE request_id = '<REQUEST_ID>'::uuid
ORDER BY occurred_at ASC;
```

Expected:
- Exactly **ONE** `VOUCHER_DOWNLOADED` event (from Step 6)
- Exactly **ONE** `STATUS_CHANGED` event with:
  - `old_status`: `AMIGA_REVIEWED`
  - `new_status`: `SENT_TO_CLIENT`
- No additional events from Step 7 download

### Step 9: Verify PDF Content Integrity

Confirm both downloads return the same PDF:

```bash
md5sum /tmp/voucher_first_download.pdf /tmp/voucher_second_download.pdf
```

Expected: Both files have identical MD5 hashes.

### Step 10: Verify Timestamps in Audit Events

Check that `VOUCHER_DOWNLOADED` and `STATUS_CHANGED` events contain correct UTC timestamps:

```sql
SELECT 
  event_type,
  (payload->>'downloaded_at')::timestamptz as download_time,
  (payload->>'transitioned_at')::timestamptz as transition_time,
  occurred_at
FROM auditEvent
WHERE request_id = '<REQUEST_ID>'::uuid AND event_type IN ('VOUCHER_DOWNLOADED', 'STATUS_CHANGED')
ORDER BY occurred_at ASC;
```

Expected: All timestamps are in UTC (end with `Z` or `+00:00`).

## Automated Test File

A comprehensive pytest-based test file has been created at:
```
backend/tests/test_checkpoint_31_handover_flow.py
```

When Python 3.12+ is available, run:
```bash
cd backend
python -m pytest tests/test_checkpoint_31_handover_flow.py -v
```

The test file covers:
- ✓ First download creates exactly one `SENT_TO_CLIENT` event
- ✓ Second download is idempotent (no duplicate events)
- ✓ Non-CLIENT_PIC roles are denied (403)
- ✓ Users without active client assignment are denied (403)
- ✓ Requests not in `AMIGA_REVIEWED` or `SENT_TO_CLIENT` status are blocked (400)
- ✓ Already-SENT_TO_CLIENT requests can still be downloaded
- ✓ Missing PDF returns 404
- ✓ VOUCHER_DOWNLOADED event includes required metadata

## Success Criteria

All the following must be true:

1. ✓ First `GET /requests/{id}/voucher-pdf` returns HTTP 200 with PDF content
2. ✓ After first download, request status is `SENT_TO_CLIENT`
3. ✓ Exactly **ONE** `SENT_TO_CLIENT`-equivalent event in audit trail:
   - One `VOUCHER_DOWNLOADED` event
   - One `STATUS_CHANGED` event (AMIGA_REVIEWED → SENT_TO_CLIENT)
4. ✓ Second `GET /requests/{id}/voucher-pdf` returns HTTP 200 with identical PDF
5. ✓ After second download, **NO new audit events** are created
6. ✓ Request status remains `SENT_TO_CLIENT` after second download
7. ✓ All timestamps are UTC-formatted
8. ✓ Both PDF downloads have identical content (MD5 hash match)

## Questions for User

After running this checkpoint, please confirm:

1. Were you able to successfully approve a request and generate a PDF?
2. Did the first download transition the request to `SENT_TO_CLIENT` status?
3. Was exactly one `SENT_TO_CLIENT` event recorded (one `VOUCHER_DOWNLOADED` + one `STATUS_CHANGED`)?
4. Did the second download return the same PDF without creating additional events?
5. Were there any errors or unexpected behavior?

---

**Task Status**: Checkpoint test procedures documented. Ready for manual or automated execution once Python 3.12+ is available.
