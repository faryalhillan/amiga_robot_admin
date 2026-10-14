/**
 * Shared type definitions for the AMIGA Robot Admin frontend
 */

export type RequestStatus = 'QUEUED' | 'PROCESSING' | 'READY_FOR_REVIEW' | 'EXCEPTION' | 'AMIGA_REVIEWED' | 'SENT_TO_CLIENT' | 'REJECTED';

export type FlagType = 'MISSING_EVIDENCE' | 'POSSIBLE_DUPLICATE' | 'CALC_DISCREPANCY';

export interface CalculationDiscrepancy {
  field_name: string;
  computed: number | string;
  extracted: number | string;
}

export interface MatchingRequestRef {
  request_id: string;
  status: RequestStatus;
  invoice_date: string;
  total_amount: number | string;
}

export interface FlagDetail {
  flag_type: FlagType;
  missing_fields?: string[]; // for MISSING_EVIDENCE
  matching_requests?: MatchingRequestRef[]; // for POSSIBLE_DUPLICATE
  discrepancies?: CalculationDiscrepancy[]; // for CALC_DISCREPANCY
  details?: Record<string, any>; // for any additional details
}

export interface Request {
  request_id: string;
  client_id: string;
  client_name: string;
  vendor_name: string;
  invoice_number: string;
  status: RequestStatus;
  flags: FlagType[];
  flag_details: FlagDetail[];
  created_at: string;
  uploader_id: string;
  assigned_reviewer?: string;
}
