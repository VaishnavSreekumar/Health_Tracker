import type { FC } from 'react';

export type NavigationTab = 
  | 'overview'
  | 'patients'
  | 'appointments'
  | 'studio'
  | 'delivery'
  | 'settings';

interface NavigationProps {
  currentTab: NavigationTab;
  onTabChange: (tab: NavigationTab) => void;
  draftsCount?: number;
}

export const Navigation: FC<NavigationProps> = ({
  currentTab,
  onTabChange,
  draftsCount = 0,
}) => {
  return (
    <header style={{
      backgroundColor: 'var(--color-surface)',
      borderBottom: '1px solid var(--color-border)',
      position: 'sticky',
      top: 0,
      zIndex: 50,
    }}>
      <div style={{
        maxWidth: '1440px',
        margin: '0 auto',
        padding: '0 var(--space-6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        height: '64px',
      }}>
        {/* Brand Identity: Dual-Circle Caliper Geometric Mark + Editorial Wordmark */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-6)' }}>
          <div 
            onClick={() => onTabChange('overview')}
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '10px', 
              cursor: 'pointer',
              userSelect: 'none',
            }}
          >
            <svg width="26" height="26" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect width="28" height="28" rx="3" fill="#192720" />
              {/* Geometric caliper / lens instrument */}
              <circle cx="14" cy="14" r="8" stroke="#F6F4ED" strokeWidth="1.5" strokeDasharray="2 2" />
              <circle cx="14" cy="14" r="4.5" fill="#285544" stroke="#F6F4ED" strokeWidth="1" />
              <circle cx="14" cy="14" r="2" fill="#D66A45" />
            </svg>
            <div>
              <div style={{ 
                fontFamily: 'var(--font-serif)', 
                fontSize: '18px', 
                fontWeight: 600, 
                letterSpacing: '-0.02em',
                lineHeight: 1.1,
                color: 'var(--color-ink)',
              }}>
                HealthTrack
              </div>
              <div className="mono-label" style={{ fontSize: '9px', letterSpacing: '0.08em', color: 'var(--color-muted)' }}>
                Follow-up Atelier
              </div>
            </div>
          </div>

          <div style={{ width: '1px', height: '28px', backgroundColor: 'var(--color-border)' }} />

          {/* Clinical Workspace Anchor */}
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontSize: '12px', fontWeight: 500, color: 'var(--color-ink)' }}>
              St. Jude Family Health
            </span>
            <span className="mono-label" style={{ fontSize: '10px' }}>
              Primary Care Ops
            </span>
          </div>
        </div>

        {/* Tab Navigation */}
        <nav style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          {[
            { id: 'overview', label: 'Overview' },
            { id: 'patients', label: 'Patient Register' },
            { id: 'appointments', label: 'Appointments' },
            { 
              id: 'studio', 
              label: 'Follow-up Studio',
              badge: draftsCount > 0 ? draftsCount : undefined 
            },
            { id: 'delivery', label: 'Delivery Log' },
            { id: 'settings', label: 'Settings' },
          ].map((item) => {
            const isActive = currentTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onTabChange(item.id as NavigationTab)}
                style={{
                  padding: '8px 14px',
                  fontSize: '13px',
                  fontWeight: isActive ? 600 : 400,
                  color: isActive ? 'var(--color-ink)' : 'var(--color-muted)',
                  backgroundColor: isActive ? 'var(--color-paper)' : 'transparent',
                  border: '1px solid',
                  borderColor: isActive ? 'var(--color-border)' : 'transparent',
                  borderRadius: 'var(--radius-sm)',
                  position: 'relative',
                }}
              >
                {item.label}
                {item.badge !== undefined && (
                  <span style={{
                    marginLeft: '4px',
                    backgroundColor: 'var(--color-signal)',
                    color: '#FFF',
                    fontSize: '10px',
                    fontFamily: 'var(--font-mono)',
                    fontWeight: 600,
                    padding: '1px 5px',
                    borderRadius: '2px',
                    lineHeight: 1,
                  }}>
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Subtle Workspace Status Indicator */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '4px 10px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--color-border)',
              backgroundColor: 'var(--color-paper)',
              fontSize: '11px',
              fontFamily: 'var(--font-mono)',
              color: 'var(--color-muted)',
            }}
            title="Standalone local operational environment (delivery disabled)"
          >
            <span
              style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                backgroundColor: 'var(--color-primary)',
                display: 'inline-block',
              }}
            />
            Local Workspace
          </div>
        </div>
      </div>
    </header>
  );
};
