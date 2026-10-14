/**
 * API client utilities for communicating with the AMIGA Robot Admin backend.
 */

interface ApiOptions {
  method?: string;
  headers?: Record<string, string>;
  body?: any;
}

const BASE_URL = '/api';

/**
 * Make an authenticated API request.
 * Automatically includes the JWT token from localStorage.
 */
export async function apiRequest<T>(
  endpoint: string,
  options?: ApiOptions
): Promise<T> {
  const token = localStorage.getItem('token');
  const method = options?.method || 'GET';
  
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers || {}),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const url = `${BASE_URL}${endpoint}`;

  const fetchOptions: RequestInit = {
    method,
    headers,
  };

  if (options?.body) {
    fetchOptions.body = JSON.stringify(options.body);
  }

  const response = await fetch(url, fetchOptions);

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(
      `API Error [${response.status}]: ${response.statusText} - ${errorBody}`
    );
  }

  if (response.status === 204) {
    return undefined as unknown as T;
  }

  return response.json();
}

/**
 * Fetch the list of requests for the queue dashboard.
 */
export async function fetchRequests(): Promise<any[]> {
  return apiRequest('/requests', { method: 'GET' });
}

/**
 * Report page load telemetry to the backend.
 */
export async function reportPageLoadTelemetry(
  page: string,
  duration_ms: number
): Promise<{ record_id: string }> {
  return apiRequest('/telemetry/page-load', {
    method: 'POST',
    body: {
      page,
      duration_ms,
      measured_at: new Date().toISOString(),
    },
  });
}
