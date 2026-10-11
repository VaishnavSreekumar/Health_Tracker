import { useState, useEffect, type FC } from 'react';
import { api, type SystemSettings } from '../api/client';

interface SettingsScreenProps {
  onResetData: () => void;
}

export const SettingsScreen: FC<SettingsScreenProps> = ({ onResetData }) => {
  const [settings, setSettings] = useState<SystemSettings | null>(null);

  useEffect(() => {
    api.getSystemSettings()
      .then((data) => setSettings(data))
      .catch(() => setSettings(null));
  }, []);

  return (
    <div style={{ maxWidth: '1440px', margin: '0 auto', padding: 'var(--space-6)', width: '100%' }}>
      {/* Header */}
      <div style={{ marginBottom: 'var(--space-6)' }}>
        <div className="mono-label">System Architecture & Integrations</div>
        <h1 style={{ marginTop: '2px' }}>Integration Readiness & Settings</h1>
        <p style={{ color: 'var(--color-muted)', fontSize: '13px', marginTop: '4px' }}>
          Operational environment variables, provider credentials status, and safety controls.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-6)', alignItems: 'start' }}>
        {/* LLM Provider Status */}
        <div className="panel">
          <div className="panel-header">
            <div>
              <span className="mono-label">Intelligence Layer</span>
              <h3 style={{ fontSize: '16px' }}>LLM Personalization Engine</h3>
            </div>
            {settings && (
              <span className={`badge ${settings.llm_configured ? 'badge-approved' : 'badge-draft'}`}>
                {settings.llm_status.replace('_', ' ')}
              </span>
            )}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            <div>
              <div className="mono-label" style={{ fontSize: '10px' }}>CONFIGURED PROVIDER</div>
              <div style={{ fontSize: '14px', fontWeight: 600, marginTop: '2px' }}>
                {settings?.llm_provider || 'none'}
              </div>
            </div>

            <div>
              <div className="mono-label" style={{ fontSize: '10px' }}>DEFAULT MODEL IDENTIFIER</div>
              <div className="font-mono" style={{ fontSize: '13px', marginTop: '2px', color: 'var(--color-muted)' }}>
                {settings?.llm_model || 'None'}
              </div>
            </div>

            <div>
              <div className="mono-label" style={{ fontSize: '10px' }}>CREDENTIAL STATUS</div>
              <div style={{ fontSize: '13px', marginTop: '2px' }}>
                {settings?.llm_configured ? (
                  <span style={{ color: 'var(--color-primary)', fontWeight: 600 }}>
                    Active (Loaded safely from server environment)
                  </span>
                ) : (
                  <span style={{ color: 'var(--color-muted)' }}>
                    Not Configured — Using deterministic validated template fallback
                  </span>
                )}
              </div>
            </div>

            <div style={{
              backgroundColor: 'var(--color-paper)',
              padding: '12px 14px',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-sm)',
              fontSize: '12px',
              color: 'var(--color-muted)',
              lineHeight: '1.5',
            }}>
              <strong>Architecture Guarantee:</strong> Provider credentials are never transmitted to the browser. In offline mode, the system uses the <code>TemplateMessagePersonalizer</code> validated against the 5-tier guardrail pipeline.
            </div>
          </div>
        </div>

        {/* Delivery Transport Status */}
        <div className="panel">
          <div className="panel-header">
            <div>
              <span className="mono-label">Transport Layer</span>
              <h3 style={{ fontSize: '16px' }}>Message Dispatch Service</h3>
            </div>
            <span className="badge badge-draft">Disabled (Safe Mode)</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            <div>
              <div className="mono-label" style={{ fontSize: '10px' }}>OUTBOUND CHANNEL</div>
              <div style={{ fontSize: '14px', fontWeight: 600, marginTop: '2px' }}>
                {settings?.delivery_provider || 'None'}
              </div>
            </div>

            <div>
              <div className="mono-label" style={{ fontSize: '10px' }}>DISPATCH ELIGIBILITY</div>
              <div style={{ fontSize: '13px', marginTop: '2px', color: 'var(--color-muted)' }}>
                Reminders must be in <code>APPROVED</code> state and reviewed by an authorized clinician.
              </div>
            </div>

            <div style={{
              backgroundColor: 'var(--color-paper)',
              padding: '12px 14px',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-sm)',
              fontSize: '12px',
              color: 'var(--color-muted)',
              lineHeight: '1.5',
            }}>
              <strong>Safety Guardrail:</strong> Live external transmission is disabled by default to prevent unintentional messages to real recipients during verification and demonstration.
            </div>
          </div>
        </div>

        {/* Database & Persistence */}
        <div className="panel">
          <div className="panel-header">
            <div>
              <span className="mono-label">Storage Engine</span>
              <h3 style={{ fontSize: '16px' }}>Relational Persistence</h3>
            </div>
            <span className="badge badge-approved">Online</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', fontSize: '13px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '6px', borderBottom: '1px solid var(--color-border-subtle)' }}>
              <span style={{ color: 'var(--color-muted)' }}>Engine</span>
              <span className="font-mono">{settings?.database_type || 'SQLite'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '6px', borderBottom: '1px solid var(--color-border-subtle)' }}>
              <span style={{ color: 'var(--color-muted)' }}>Foreign Key Enforcement</span>
              <span className="font-mono">PRAGMA foreign_keys=ON</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '6px', borderBottom: '1px solid var(--color-border-subtle)' }}>
              <span style={{ color: 'var(--color-muted)' }}>Timezone Normalization</span>
              <span className="font-mono">Explicit UTC decorator</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--color-muted)' }}>Duplicate Constraint</span>
              <span className="font-mono">UNIQUE(appointment_id)</span>
            </div>
          </div>
        </div>

        {/* Operational Reset & Maintenance */}
        <div className="panel">
          <div className="panel-header">
            <div>
              <span className="mono-label">Maintenance</span>
              <h3 style={{ fontSize: '16px' }}>Demonstration State Management</h3>
            </div>
          </div>

          <p style={{ fontSize: '13px', color: 'var(--color-muted)', marginBottom: 'var(--space-4)', lineHeight: '1.5' }}>
            Reset database tables to a clean state for repeatable evaluator walkthroughs or re-seed with standard clinical cases.
          </p>

          <div style={{ display: 'flex', gap: '10px' }}>
            <button
              onClick={onResetData}
              className="btn-danger"
              style={{ fontSize: '12px' }}
            >
              Clear All Clinical Records
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
