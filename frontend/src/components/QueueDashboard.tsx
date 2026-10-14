import React, { useEffect, useState, useRef } from 'react';
import { RequestStatus } from '../types/index';
import { fetchRequests, reportPageLoadTelemetry } from '../services/api';

interface QueueDashboardProps {
  onNavigate?: (requestId: string, targetScreen: string) => void;
}

interface QueueItem {
  request_id: string;
  client_name: string;
  vendor_name: string;
  status: RequestStatus;
  created_at: string;
}

const QueueDashboard: React.FC<QueueDashboardProps> = ({ onNavigate }) => {
  const [requests, setRequests] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigationStartTime = useRef<number>(0);
  const pageLoadReported = useRef(false);

  useEffect(() => {
    // Record the start time when component mounts
    navigationStartTime.current = performance.now();
  }, []);

  useEffect(() => {
    const fetchRequestsData = async () => {
      try {
        setLoading(true);
        setError(null);

        const data = await fetchRequests();
        setRequests(data);

        // Report page load time once data is loaded and table is ready to be interactive
        if (!pageLoadReported.current && data.length >= 0) {
          reportPageLoadTime();
          pageLoadReported.current = true;
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Unknown error occurred';
        setError(message);
        console.error('Error fetching requests:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchRequestsData();
  }, []);

  const reportPageLoadTime = async () => {
    try {
      const endTime = performance.now();
      const duration = Math.round(endTime - navigationStartTime.current);

      await reportPageLoadTelemetry('QUEUE_DASHBOARD', duration);
    } catch (err) {
      console.error('Error reporting page load time:', err);
    }
  };

  const getDetailScreenTarget = (status: RequestStatus): string => {
    if (status === 'READY_FOR_REVIEW' || status === 'EXCEPTION') {
      return 'ReviewWorkspace';
    } else if (status === 'AMIGA_REVIEWED') {
      return 'VoucherPreview';
    } else {
      return 'RequestDetail';
    }
  };

  const handleRowClick = (requestId: string, status: RequestStatus) => {
    const targetScreen = getDetailScreenTarget(status);
    if (onNavigate) {
      onNavigate(requestId, targetScreen);
    }
  };

  const formatDate = (dateString: string): string => {
    try {
      const date = new Date(dateString);
      return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateString;
    }
  };

  const getStatusBadgeClass = (status: RequestStatus): string => {
    const baseClass = 'status-badge status-';
    return baseClass + status.toLowerCase();
  };

  if (loading) {
    return (
      <div className="queue-dashboard loading">
        <h1>Queue Dashboard</h1>
        <p>Loading requests...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="queue-dashboard error">
        <h1>Queue Dashboard</h1>
        <div className="error-message">
          <p>Error: {error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="queue-dashboard">
      <h1>Queue Dashboard</h1>
      
      {requests.length === 0 ? (
        <div className="empty-state">
          <p>No requests to display.</p>
        </div>
      ) : (
        <div className="table-container">
          <table className="requests-table" role="table">
            <thead>
              <tr>
                <th>Request ID</th>
                <th>Client Name</th>
                <th>Vendor Name</th>
                <th>Status</th>
                <th>Submission Date</th>
              </tr>
            </thead>
            <tbody>
              {requests.map((request) => (
                <tr
                  key={request.request_id}
                  onClick={() => handleRowClick(request.request_id, request.status)}
                  className="clickable-row"
                  role="row"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      handleRowClick(request.request_id, request.status);
                    }
                  }}
                >
                  <td className="request-id">{request.request_id}</td>
                  <td className="client-name">{request.client_name || '-'}</td>
                  <td className="vendor-name">{request.vendor_name || '-'}</td>
                  <td className="status">
                    <span className={getStatusBadgeClass(request.status)}>
                      {request.status.replace(/_/g, ' ')}
                    </span>
                  </td>
                  <td className="submission-date">{formatDate(request.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <style>{`
        .queue-dashboard {
          padding: 24px;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
          background-color: #ffffff;
          min-height: 100vh;
        }

        .queue-dashboard h1 {
          font-size: 28px;
          font-weight: 600;
          margin: 0 0 24px 0;
          color: #1a1a1a;
        }

        .queue-dashboard.loading,
        .queue-dashboard.error {
          text-align: center;
          padding: 48px 24px;
        }

        .queue-dashboard.loading p {
          color: #666;
          font-size: 16px;
        }

        .error-message {
          background-color: #fee;
          border: 1px solid #fcc;
          border-radius: 4px;
          padding: 12px;
          margin: 12px 0;
          color: #c33;
        }

        .empty-state {
          text-align: center;
          padding: 48px 24px;
          color: #666;
        }

        .table-container {
          overflow-x: auto;
          border: 1px solid #e0e0e0;
          border-radius: 4px;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        }

        .requests-table {
          width: 100%;
          border-collapse: collapse;
          background-color: #fff;
        }

        .requests-table thead {
          background-color: #f5f5f5;
          border-bottom: 2px solid #e0e0e0;
        }

        .requests-table th {
          text-align: left;
          padding: 12px 16px;
          font-weight: 600;
          font-size: 14px;
          color: #333;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .requests-table tbody tr {
          border-bottom: 1px solid #e0e0e0;
          transition: background-color 0.2s ease;
        }

        .requests-table tbody tr:hover {
          background-color: #f9f9f9;
        }

        .requests-table tbody tr.clickable-row {
          cursor: pointer;
        }

        .requests-table tbody tr.clickable-row:focus {
          outline: 2px solid #0066cc;
          outline-offset: -1px;
        }

        .requests-table td {
          padding: 12px 16px;
          font-size: 14px;
          color: #333;
          vertical-align: middle;
        }

        .requests-table .request-id {
          font-family: 'Courier New', monospace;
          font-size: 12px;
          color: #666;
          max-width: 200px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .requests-table .status {
          font-weight: 500;
        }

        .status-badge {
          display: inline-block;
          padding: 4px 8px;
          border-radius: 3px;
          font-size: 12px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .status-badge.status-queued {
          background-color: #e3f2fd;
          color: #1565c0;
        }

        .status-badge.status-processing {
          background-color: #fff3e0;
          color: #e65100;
        }

        .status-badge.status-ready_for_review {
          background-color: #f3e5f5;
          color: #6a1b9a;
        }

        .status-badge.status-exception {
          background-color: #ffebee;
          color: #c62828;
        }

        .status-badge.status-amiga_reviewed {
          background-color: #e8f5e9;
          color: #2e7d32;
        }

        .status-badge.status-sent_to_client {
          background-color: #e0f2f1;
          color: #00695c;
        }

        .status-badge.status-rejected {
          background-color: #fce4ec;
          color: #c2185b;
        }

        .requests-table .submission-date {
          color: #666;
          font-size: 13px;
        }

        @media (max-width: 768px) {
          .queue-dashboard {
            padding: 16px;
          }

          .queue-dashboard h1 {
            font-size: 24px;
            margin-bottom: 16px;
          }

          .requests-table th,
          .requests-table td {
            padding: 8px 12px;
            font-size: 13px;
          }

          .requests-table th {
            font-size: 12px;
          }

          .requests-table .request-id {
            max-width: 120px;
          }
        }
      `}</style>
    </div>
  );
};

export default QueueDashboard;
