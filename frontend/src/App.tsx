import { useState, useEffect } from 'react';
import { Navigation, type NavigationTab } from './components/Navigation';
import { OverviewScreen } from './screens/OverviewScreen';
import { StudioScreen } from './screens/StudioScreen';
import { PatientsScreen } from './screens/PatientsScreen';
import { AppointmentsScreen } from './screens/AppointmentsScreen';
import { DeliveryScreen } from './screens/DeliveryScreen';
import { SettingsScreen } from './screens/SettingsScreen';
import { api } from './api/client';

export function App() {
  const [currentTab, setCurrentTab] = useState<NavigationTab>('studio');
  const [studioAppointmentId, setStudioAppointmentId] = useState<number | null>(null);
  const [draftsCount, setDraftsCount] = useState<number>(0);
  const [isSeeding, setIsSeeding] = useState<boolean>(false);
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Poll/fetch metrics to update draft count badge
  const updateDraftBadge = async () => {
    try {
      const m = await api.getOverviewMetrics();
      setDraftsCount(m.drafts_pending_review);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    updateDraftBadge();
  }, [currentTab]);

  const handleSeedDemo = async () => {
    setIsSeeding(true);
    setNotification(null);
    try {
      const res = await api.seedDemoData();
      setNotification({
        type: 'success',
        message: `${res.message} (${res.patients_count} patients loaded across active lifecycle states)`,
      });
      updateDraftBadge();
      // Auto-switch to studio so user can immediately experience the workbench
      setCurrentTab('studio');
    } catch (err: any) {
      setNotification({ type: 'error', message: `Failed to seed demo data: ${err.message}` });
    } finally {
      setIsSeeding(false);
    }
  };

  const handleResetDemo = async () => {
    try {
      await api.resetDemoData();
      setNotification({ type: 'success', message: 'All demo records cleared from database.' });
      setDraftsCount(0);
      setStudioAppointmentId(null);
      setCurrentTab('overview');
    } catch (err: any) {
      setNotification({ type: 'error', message: `Reset failed: ${err.message}` });
    }
  };

  const navigateToStudioWithAppointment = (appointmentId?: number) => {
    if (appointmentId) {
      setStudioAppointmentId(appointmentId);
    }
    setCurrentTab('studio');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', backgroundColor: 'var(--color-paper)' }}>
      {/* Top Application Shell Navigation */}
      <Navigation
        currentTab={currentTab}
        onTabChange={(tab) => {
          setCurrentTab(tab);
        }}
        draftsCount={draftsCount}
        onSeedDemo={handleSeedDemo}
        isSeeding={isSeeding}
      />

      {/* Global Notification Toast */}
      {notification && (
        <div style={{
          backgroundColor: notification.type === 'success' ? 'var(--status-approved-bg)' : 'var(--status-rejected-bg)',
          borderBottom: '1px solid',
          borderColor: notification.type === 'success' ? 'var(--status-approved-border)' : 'var(--status-rejected-border)',
          color: notification.type === 'success' ? 'var(--status-approved-text)' : 'var(--status-rejected-text)',
          padding: '10px var(--space-6)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontSize: '13px',
        }}>
          <div style={{ maxWidth: '1440px', margin: '0 auto', width: '100%', display: 'flex', justifyContent: 'space-between' }}>
            <span>{notification.message}</span>
            <button
              onClick={() => setNotification(null)}
              style={{ padding: '0 6px', fontSize: '12px', color: 'inherit' }}
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Screen Routing */}
      <main style={{ flex: 1, paddingBottom: 'var(--space-12)' }}>
        {currentTab === 'overview' && (
          <OverviewScreen
            onNavigateToStudio={navigateToStudioWithAppointment}
            onRefreshData={updateDraftBadge}
          />
        )}

        {currentTab === 'studio' && (
          <StudioScreen
            initialAppointmentId={studioAppointmentId}
            onRefreshData={updateDraftBadge}
          />
        )}

        {currentTab === 'patients' && <PatientsScreen />}

        {currentTab === 'appointments' && (
          <AppointmentsScreen onDraftInStudio={navigateToStudioWithAppointment} />
        )}

        {currentTab === 'delivery' && <DeliveryScreen />}

        {currentTab === 'settings' && <SettingsScreen onResetData={handleResetDemo} />}
      </main>

      {/* Editorial Clinical Ops Footer */}
      <footer style={{
        backgroundColor: 'var(--color-surface)',
        borderTop: '1px solid var(--color-border)',
        padding: 'var(--space-6)',
        marginTop: 'auto',
      }}>
        <div style={{
          maxWidth: '1440px',
          margin: '0 auto',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontSize: '12px',
          color: 'var(--color-muted)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
            <span style={{ fontWeight: 600, color: 'var(--color-ink)' }}>HealthTrack Atelier</span>
            <span>·</span>
            <span>Precision Post-Encounter Operations</span>
            <span>·</span>
            <span>Deterministic 5-Tier Heuristic Guardrails</span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
            <span className="mono-label">SQLite PRAGMA FK ON</span>
            <span>·</span>
            <span className="mono-label">UTC Normalized</span>
            <span>·</span>
            <span className="mono-label">Human-in-the-Loop Approved</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;
