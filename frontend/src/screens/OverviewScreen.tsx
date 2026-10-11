import { useState, useEffect, type FC } from 'react';
import { api, type ActivityItem, type OverviewMetrics } from '../api/client';

interface OverviewScreenProps {
  onNavigateToStudio: (appointmentId?: number) => void;
  onRefreshData?: () => void;
}

export const OverviewScreen: FC<OverviewScreenProps> = ({
  onNavigateToStudio,
}) => {
  const [metrics, setMetrics] = useState<OverviewMetrics | null>(null);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const loadData = async () => {
    setErrorMessage(null);
    try {
      const [m, a] = await Promise.all([
        api.getOverviewMetrics(),
        api.getOverviewActivity(),
      ]);
      setMetrics(m);
      setActivity(a);
    } catch (err: any) {
      setErrorMessage(`Failed to load operational overview: ${err.message}`);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  return (
    <div style={{ maxWidth: '1440px', margin: '0 auto', padding: 'var(--space-6)', width: '100%' }}>
      {/* Header */}
      <div style={{ marginBottom: 'var(--space-6)' }}>
        <div className="mono-label">Clinic Operations Dashboard</div>
        <h1 style={{ marginTop: '2px' }}>Operational Overview</h1>
        <p style={{ color: 'var(--color-muted)', fontSize: '13px', marginTop: '4px' }}>
          Real-time patient follow-up activity, pending human reviews, and delivery status.
        </p>
      </div>

      {errorMessage && (
        <div style={{
          backgroundColor: 'var(--status-rejected-bg)',
          border: '1px solid var(--status-rejected-border)',
          color: 'var(--status-rejected-text)',
          padding: '12px 16px',
          borderRadius: 'var(--radius-sm)',
          marginBottom: 'var(--space-5)',
          fontSize: '13px',
        }}>
          {errorMessage}
        </div>
      )}

      {/* PRIORITY ACTION CALLOUT: Leads with next operator action */}
      {metrics && metrics.drafts_pending_review > 0 ? (
        <div style={{
          backgroundColor: 'var(--color-signal-subtle)',
          border: '1px solid var(--status-rejected-border)',
          borderRadius: 'var(--radius-sm)',
          padding: '20px 24px',
          marginBottom: 'var(--space-6)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}>
          <div>
            <div className="mono-label" style={{ color: 'var(--color-signal)' }}>ATTENTION REQUIRED</div>
            <h2 style={{ fontSize: '1.4rem', marginTop: '2px', color: 'var(--color-ink)' }}>
              {metrics.drafts_pending_review} follow-up reminder{metrics.drafts_pending_review > 1 ? 's' : ''} awaiting clinical review
            </h2>
            <p style={{ fontSize: '13px', color: 'var(--color-muted)', marginTop: '4px' }}>
              Drafts have passed heuristic guardrails and require clinician review before approval for dispatch.
            </p>
          </div>
          <button
            onClick={() => onNavigateToStudio()}
            className="btn-signal"
            style={{ padding: '10px 18px', fontSize: '13px', whiteSpace: 'nowrap' }}
          >
            Open Review Studio →
          </button>
        </div>
      ) : metrics && metrics.eligible_appointments > 0 ? (
        <div style={{
          backgroundColor: 'var(--color-surface)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-sm)',
          padding: '16px 20px',
          marginBottom: 'var(--space-6)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}>
          <div>
            <div className="mono-label">OPPORTUNITY</div>
            <div style={{ fontSize: '15px', fontWeight: 600, marginTop: '2px' }}>
              {metrics.eligible_appointments} recent encounters ready for follow-up outreach
            </div>
            <p style={{ fontSize: '13px', color: 'var(--color-muted)', marginTop: '2px' }}>
              Encounters within the 7-day lookback window can be drafted in the studio.
            </p>
          </div>
          <button
            onClick={() => onNavigateToStudio()}
            className="btn-primary"
            style={{ padding: '8px 16px' }}
          >
            Launch Follow-up Studio
          </button>
        </div>
      ) : null}

      {/* TYPOGRAPHIC OPERATIONAL METRICS GRID */}
      {metrics && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 'var(--space-4)',
          marginBottom: 'var(--space-6)',
        }}>
          <div className="panel" style={{ padding: '16px' }}>
            <div className="mono-label">Active Patients</div>
            <div style={{ fontSize: '2rem', fontFamily: 'var(--font-serif)', fontWeight: 600, marginTop: '6px' }}>
              {metrics.total_patients}
            </div>
            <div style={{ fontSize: '12px', color: 'var(--color-muted)', marginTop: '4px' }}>
              Registered synthetic records
            </div>
          </div>

          <div className="panel" style={{ padding: '16px' }}>
            <div className="mono-label">Total Encounters</div>
            <div style={{ fontSize: '2rem', fontFamily: 'var(--font-serif)', fontWeight: 600, marginTop: '6px' }}>
              {metrics.total_appointments}
            </div>
            <div style={{ fontSize: '12px', color: 'var(--color-muted)', marginTop: '4px' }}>
              {metrics.eligible_appointments} inside 7-day window
            </div>
          </div>

          <div className="panel" style={{ padding: '16px' }}>
            <div className="mono-label">Approved Reminders</div>
            <div style={{ fontSize: '2rem', fontFamily: 'var(--font-serif)', fontWeight: 600, marginTop: '6px', color: 'var(--color-primary)' }}>
              {metrics.approved_reminders}
            </div>
            <div style={{ fontSize: '12px', color: 'var(--color-muted)', marginTop: '4px' }}>
              Verified by clinical reviewer
            </div>
          </div>

          <div className="panel" style={{ padding: '16px' }}>
            <div className="mono-label">Generation Provenance</div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '6px' }}>
              <span style={{ fontSize: '1.6rem', fontFamily: 'var(--font-serif)', fontWeight: 600 }}>
                {metrics.ai_generated_count}
              </span>
              <span className="mono-label" style={{ fontSize: '11px' }}>AI</span>
              <span style={{ color: 'var(--color-border)', fontSize: '16px' }}>/</span>
              <span style={{ fontSize: '1.6rem', fontFamily: 'var(--font-serif)', fontWeight: 600, color: 'var(--color-muted)' }}>
                {metrics.fallback_count}
              </span>
              <span className="mono-label" style={{ fontSize: '11px' }}>Fallback</span>
            </div>
            <div style={{ fontSize: '12px', color: 'var(--color-muted)', marginTop: '4px' }}>
              Deterministic fallback active
            </div>
          </div>
        </div>
      )}

      {/* RECENT OPERATIONAL ACTIVITY TABLE */}
      <div className="panel">
        <div className="panel-header">
          <div>
            <span className="mono-label">Audit Trail</span>
            <h3 style={{ fontSize: '16px' }}>Recent Operational Actions</h3>
          </div>
          <button onClick={loadData} className="btn-ghost" style={{ fontSize: '12px' }}>
            Refresh
          </button>
        </div>

        {activity.length > 0 ? (
          <table className="editorial-table">
            <thead>
              <tr>
                <th style={{ width: '120px' }}>Encounter</th>
                <th style={{ width: '180px' }}>Patient</th>
                <th style={{ width: '130px' }}>Action</th>
                <th>Operation Details</th>
                <th style={{ width: '160px' }}>Timestamp</th>
                <th style={{ width: '100px', textAlign: 'right' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {activity.map((item) => (
                <tr key={item.id}>
                  <td className="font-mono" style={{ fontSize: '12px' }}>
                    APT-{item.appointment_id.toString().padStart(4, '0')}
                  </td>
                  <td style={{ fontWeight: 500 }}>{item.patient_name}</td>
                  <td>
                    <span className={`badge badge-${item.action_type === 'approved' ? 'approved' : item.action_type === 'rejected' ? 'rejected' : 'draft'}`}>
                      {item.action_type.replace('_', ' ')}
                    </span>
                  </td>
                  <td style={{ color: 'var(--color-ink)' }}>{item.detail}</td>
                  <td className="font-mono" style={{ fontSize: '11px', color: 'var(--color-muted)' }}>
                    {new Date(item.timestamp).toLocaleString('en-US', {
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <button
                      onClick={() => onNavigateToStudio(item.appointment_id)}
                      className="btn-ghost"
                      style={{ fontSize: '11px', padding: '3px 8px' }}
                    >
                      Inspect →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--color-muted)' }}>
            No recent follow-up activity found. Seed demo data or draft a reminder in the studio to generate activity records.
          </div>
        )}
      </div>
    </div>
  );
};
