import { useState, useEffect, type FC } from 'react';
import { api, type DeliveryLog } from '../api/client';

export const DeliveryScreen: FC = () => {
  const [logs, setLogs] = useState<DeliveryLog[]>([]);

  useEffect(() => {
    api.getDeliveryLogs()
      .then((data) => setLogs(data))
      .catch(() => setLogs([]));
  }, []);

  return (
    <div style={{ maxWidth: '1440px', margin: '0 auto', padding: 'var(--space-6)', width: '100%' }}>
      {/* Header */}
      <div style={{ marginBottom: 'var(--space-6)' }}>
        <div className="mono-label">Transmission Channel</div>
        <h1 style={{ marginTop: '2px' }}>Outbound Delivery Log</h1>
        <p style={{ color: 'var(--color-muted)', fontSize: '13px', marginTop: '4px' }}>
          Verification and audit records for SMS and email dispatch transports.
        </p>
      </div>

      {/* TRUTHFUL OPERATIONAL STATUS BANNER */}
      <div style={{
        backgroundColor: 'var(--color-paper)',
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius-sm)',
        padding: '20px 24px',
        marginBottom: 'var(--space-6)',
        display: 'flex',
        alignItems: 'flex-start',
        gap: 'var(--space-4)',
      }}>
        <div style={{
          width: '32px',
          height: '32px',
          borderRadius: 'var(--radius-sm)',
          backgroundColor: 'var(--color-surface)',
          border: '1px solid var(--color-border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'var(--font-mono)',
          fontWeight: 700,
          color: 'var(--color-muted)',
          flexShrink: 0,
        }}>
          !
        </div>

        <div>
          <div className="mono-label" style={{ color: 'var(--color-muted)' }}>TRANSPARENCY NOTICE</div>
          <h3 style={{ fontSize: '16px', marginTop: '2px' }}>
            External Delivery Transport Disabled (Safe Demonstration Mode)
          </h3>
          <p style={{ fontSize: '13px', color: 'var(--color-muted)', marginTop: '4px', lineHeight: '1.6', maxWidth: '820px' }}>
            In compliance with clinical safety policy, external SMS (Twilio) and email transport credentials are not configured in this local environment. Approved reminders remain securely stored in the clinic database without generating accidental outbound transmissions to real patient devices. No simulated "delivered" events are fabricated.
          </p>
        </div>
      </div>

      {/* Delivery Log Table */}
      <div className="panel" style={{ padding: 0, overflow: 'hidden' }}>
        <div className="panel-header" style={{ padding: '14px 16px', borderBottom: '1px solid var(--color-border)' }}>
          <div>
            <span className="mono-label">Audit Log</span>
            <h3 style={{ fontSize: '15px' }}>Transmission History</h3>
          </div>
          <span className="badge badge-draft">{logs.length} Recorded Attempts</span>
        </div>

        <table className="editorial-table">
          <thead>
            <tr>
              <th style={{ width: '110px' }}>Log ID</th>
              <th style={{ width: '120px' }}>Reminder</th>
              <th style={{ width: '220px' }}>Recipient</th>
              <th style={{ width: '140px' }}>Transport</th>
              <th style={{ width: '130px' }}>Status</th>
              <th>Reference / Error Detail</th>
              <th style={{ width: '160px' }}>Attempt Time</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr key={log.id}>
                <td className="font-mono" style={{ fontSize: '12px' }}>
                  DLV-{log.id.toString().padStart(4, '0')}
                </td>
                <td className="font-mono" style={{ fontSize: '12px' }}>
                  REM-{log.reminder_id.toString().padStart(4, '0')}
                </td>
                <td>
                  <div style={{ fontWeight: 600 }}>{log.patient_name}</div>
                  <div className="font-mono" style={{ fontSize: '11px', color: 'var(--color-muted)' }}>
                    {log.patient_email}
                  </div>
                </td>
                <td>{log.provider}</td>
                <td>
                  <span className={`badge badge-${log.status}`}>
                    {log.status}
                  </span>
                </td>
                <td style={{ fontSize: '12px', color: log.error_detail ? 'var(--color-signal)' : 'var(--color-muted)' }}>
                  {log.error_detail || log.reference_id || 'None'}
                </td>
                <td className="font-mono" style={{ fontSize: '11px', color: 'var(--color-muted)' }}>
                  {new Date(log.created_at).toLocaleString()}
                </td>
              </tr>
            ))}

            {logs.length === 0 && (
              <tr>
                <td colSpan={7} style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--color-muted)' }}>
                  No transmission attempts recorded. Approved reminders remain staged in database.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
