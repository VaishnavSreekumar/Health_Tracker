import { useState, useEffect, type FC } from 'react';
import { api, type Appointment, type ReminderDetail } from '../api/client';

interface StudioScreenProps {
  initialAppointmentId?: number | null;
  onNavigateToAppointments?: () => void;
  onRefreshData?: () => void;
}

export const StudioScreen: FC<StudioScreenProps> = ({
  initialAppointmentId,
  onNavigateToAppointments,
  onRefreshData,
}) => {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [selectedAppointmentId, setSelectedAppointmentId] = useState<number | null>(
    initialAppointmentId || null
  );
  const [currentReminder, setCurrentReminder] = useState<ReminderDetail | null>(null);
  const [draftText, setDraftText] = useState<string>('');
  const [showOriginalDiff, setShowOriginalDiff] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);

  // Load appointments
  const fetchAppointments = async () => {
    try {
      const data = await api.getAppointments();
      setAppointments(data);
      if (!selectedAppointmentId && data.length > 0) {
        // Select first eligible appointment or first overall
        const firstEligible = data.find((a) => a.is_eligible && !a.has_reminder) || data[0];
        setSelectedAppointmentId(firstEligible.id);
      }
    } catch (err: any) {
      setErrorMessage(`Failed to load encounters: ${err.message}`);
    }
  };

  useEffect(() => {
    fetchAppointments();
  }, []);

  // When selected appointment changes, load its reminder if existing
  useEffect(() => {
    if (!selectedAppointmentId) {
      setCurrentReminder(null);
      setDraftText('');
      return;
    }

    const apt = appointments.find((a) => a.id === selectedAppointmentId);
    if (apt?.has_reminder && apt.reminder_id) {
      setIsLoading(true);
      api.getReminder(apt.reminder_id)
        .then((rem) => {
          setCurrentReminder(rem);
          setDraftText(rem.message_text);
          setErrorMessage(null);
        })
        .catch((err) => {
          setErrorMessage(`Failed to fetch reminder: ${err.message}`);
        })
        .finally(() => setIsLoading(false));
    } else {
      setCurrentReminder(null);
      setDraftText('');
    }
  }, [selectedAppointmentId, appointments]);

  const selectedAppointment = appointments.find((a) => a.id === selectedAppointmentId);

  // Trigger Draft Generation
  const handleGenerateDraft = async () => {
    if (!selectedAppointmentId) return;
    setIsLoading(true);
    setErrorMessage(null);
    setFeedbackMessage(null);

    try {
      const reminder = await api.draftForAppointment(selectedAppointmentId);
      setCurrentReminder(reminder);
      setDraftText(reminder.message_text);
      setFeedbackMessage('New follow-up draft generated successfully.');
      fetchAppointments();
      if (onRefreshData) onRefreshData();
    } catch (err: any) {
      setErrorMessage(`Generation failed: ${err.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  // Save Text Changes
  const handleSaveText = async () => {
    if (!currentReminder) return;
    setIsSaving(true);
    setErrorMessage(null);
    try {
      const updated = await api.updateReminderText(currentReminder.id, draftText);
      setCurrentReminder(updated);
      setFeedbackMessage('Draft text updated.');
      fetchAppointments();
      if (onRefreshData) onRefreshData();
    } catch (err: any) {
      setErrorMessage(`Failed to save edits: ${err.message}`);
    } finally {
      setIsSaving(false);
    }
  };

  // Approve Reminder
  const handleApprove = async () => {
    if (!currentReminder) return;
    setIsSaving(true);
    setErrorMessage(null);
    try {
      // If there are unsaved text edits, save first
      if (draftText !== currentReminder.message_text) {
        await api.updateReminderText(currentReminder.id, draftText);
      }
      const updated = await api.approveReminder(currentReminder.id);
      setCurrentReminder(updated);
      setFeedbackMessage('Draft approved. Note: External automated delivery is disabled.');
      fetchAppointments();
      if (onRefreshData) onRefreshData();
    } catch (err: any) {
      setErrorMessage(`Approval failed: ${err.message}`);
    } finally {
      setIsSaving(false);
    }
  };

  // Reject Reminder
  const handleReject = async () => {
    if (!currentReminder) return;
    setIsSaving(true);
    setErrorMessage(null);
    try {
      const updated = await api.rejectReminder(currentReminder.id);
      setCurrentReminder(updated);
      setFeedbackMessage('Draft marked as rejected.');
      fetchAppointments();
      if (onRefreshData) onRefreshData();
    } catch (err: any) {
      setErrorMessage(`Rejection failed: ${err.message}`);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div style={{ maxWidth: '1440px', margin: '0 auto', padding: 'var(--space-6)', width: '100%' }}>
      {/* Studio Header */}
      <div style={{ marginBottom: 'var(--space-6)', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <div className="mono-label">Workbench 01 — Follow-up Atelier</div>
          <h1 style={{ marginTop: '2px' }}>Follow-up Studio</h1>
          <p style={{ color: 'var(--color-muted)', fontSize: '13px', marginTop: '4px' }}>
            Transform recent clinical encounters into personalized, guardrailed patient reminders with transparent provenance and human review.
          </p>
        </div>

        {selectedAppointment && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span className="mono-label">Active Encounter:</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', fontWeight: 600 }}>
              APT-{selectedAppointment.id.toString().padStart(4, '0')}
            </span>
          </div>
        )}
      </div>

      {feedbackMessage && (
        <div style={{
          backgroundColor: 'var(--status-approved-bg)',
          border: '1px solid var(--status-approved-border)',
          color: 'var(--status-approved-text)',
          padding: '10px 14px',
          borderRadius: 'var(--radius-sm)',
          marginBottom: 'var(--space-5)',
          fontSize: '13px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}>
          <span>{feedbackMessage}</span>
          <button 
            onClick={() => setFeedbackMessage(null)} 
            style={{ padding: '0 6px', fontSize: '12px', color: 'inherit' }}
          >
            ×
          </button>
        </div>
      )}

      {errorMessage && (
        <div style={{
          backgroundColor: 'var(--status-rejected-bg)',
          border: '1px solid var(--status-rejected-border)',
          color: 'var(--status-rejected-text)',
          padding: '10px 14px',
          borderRadius: 'var(--radius-sm)',
          marginBottom: 'var(--space-5)',
          fontSize: '13px',
        }}>
          {errorMessage}
        </div>
      )}

      {/* Three-Column Workbench Layout */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '320px 1fr 180px',
        gap: 'var(--space-5)',
        alignItems: 'start',
      }}>
        {/* ============================================================== */}
        {/* COLUMN A: APPOINTMENT CONTEXT                                  */}
        {/* ============================================================== */}
        <div className="panel" style={{ height: '100%' }}>
          <div className="panel-header">
            <div>
              <span className="mono-label">Step A</span>
              <h3 style={{ fontSize: '16px' }}>Encounter Queue</h3>
            </div>
            <span className="badge badge-draft">{appointments.length} Total</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '580px', overflowY: 'auto' }}>
            {appointments.map((apt) => {
              const isSelected = apt.id === selectedAppointmentId;
              const dateStr = new Date(apt.appointment_datetime).toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric',
              });

              return (
                <div
                  key={apt.id}
                  onClick={() => setSelectedAppointmentId(apt.id)}
                  style={{
                    padding: '10px 12px',
                    backgroundColor: isSelected ? 'var(--color-paper)' : 'var(--color-surface)',
                    border: '1px solid',
                    borderColor: isSelected ? 'var(--color-primary)' : 'var(--color-border-subtle)',
                    borderRadius: 'var(--radius-sm)',
                    cursor: 'pointer',
                    transition: 'border-color var(--transition-fast)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                    <span style={{ fontWeight: 600, fontSize: '13px', color: 'var(--color-ink)' }}>
                      {apt.patient_name}
                    </span>
                    <span className="mono-label" style={{ fontSize: '10px' }}>
                      APT-{apt.id}
                    </span>
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px', color: 'var(--color-muted)' }}>
                    <span>{apt.appointment_type.replace('_', ' ')}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px' }}>{dateStr}</span>
                  </div>

                  <div style={{ marginTop: '8px', display: 'flex', gap: '6px', alignItems: 'center' }}>
                    {apt.is_eligible ? (
                      <span className="badge badge-eligible" style={{ fontSize: '9px' }}>7d Eligible</span>
                    ) : (
                      <span className="badge badge-ineligible" style={{ fontSize: '9px' }}>Outside Window</span>
                    )}

                    {apt.has_reminder ? (
                      <span className={`badge badge-${apt.reminder_status || 'draft'}`} style={{ fontSize: '9px' }}>
                        {apt.reminder_status}
                      </span>
                    ) : (
                      <span className="badge badge-draft" style={{ fontSize: '9px', opacity: 0.7 }}>
                        No Draft
                      </span>
                    )}
                  </div>
                </div>
              );
            })}

            {appointments.length === 0 && (
              <div style={{ padding: 'var(--space-6)', textAlign: 'center', color: 'var(--color-muted)' }}>
                <p style={{ marginBottom: '12px' }}>
                  No clinical encounters recorded yet. Record an encounter in the Appointments section to start drafting follow-up reminders.
                </p>
                {onNavigateToAppointments && (
                  <button
                    type="button"
                    onClick={onNavigateToAppointments}
                    className="btn-primary"
                    style={{ fontSize: '12px', padding: '6px 14px' }}
                  >
                    Record Encounter
                  </button>
                )}
              </div>
            )}
          </div>
        </div>

        {/* ============================================================== */}
        {/* COLUMN B: MESSAGE WORKBENCH                                    */}
        {/* ============================================================== */}
        <div className="panel" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          <div className="panel-header">
            <div>
              <span className="mono-label">Step B</span>
              <h3 style={{ fontSize: '16px' }}>Message Workbench</h3>
            </div>
            {currentReminder && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                {currentReminder.is_edited && (
                  <span className="badge badge-draft" style={{ backgroundColor: 'var(--color-signal-subtle)', color: 'var(--color-signal)' }}>
                    Edited vs. Original
                  </span>
                )}
                <span className={`badge badge-${currentReminder.status}`}>
                  {currentReminder.status}
                </span>
              </div>
            )}
          </div>

          {selectedAppointment ? (
            <div style={{ display: 'flex', flexDirection: 'column', flex: 1, gap: 'var(--space-4)' }}>
              {/* Patient Banner */}
              <div style={{
                backgroundColor: 'var(--color-paper)',
                padding: '12px 16px',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--color-border)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}>
                <div>
                  <div style={{ fontSize: '14px', fontWeight: 600 }}>{selectedAppointment.patient_name}</div>
                  <div style={{ fontSize: '12px', color: 'var(--color-muted)', marginTop: '2px' }}>
                    {selectedAppointment.patient_email} · Encounter: {selectedAppointment.appointment_type.replace('_', ' ')}
                  </div>
                </div>
                <div>
                  <button
                    onClick={handleGenerateDraft}
                    disabled={isLoading}
                    className="btn-primary"
                  >
                    {isLoading ? 'Generating...' : currentReminder ? 'Regenerate Draft' : 'Generate Initial Draft'}
                  </button>
                </div>
              </div>

              {/* Compact Encounter Lifecycle Timeline */}
              <div style={{
                backgroundColor: 'var(--color-surface)',
                border: '1px solid var(--color-border-subtle)',
                borderRadius: 'var(--radius-sm)',
                padding: '10px 14px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: '11px',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ color: 'var(--color-primary)', fontWeight: 700 }}>●</span>
                  <span style={{ fontWeight: 600 }}>1. Encounter</span>
                  <span style={{ color: 'var(--color-muted)' }}>Recorded</span>
                </div>
                <span style={{ color: 'var(--color-border)' }}>→</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ color: currentReminder ? 'var(--color-primary)' : 'var(--color-muted)', fontWeight: 700 }}>
                    {currentReminder ? '●' : '○'}
                  </span>
                  <span style={{ fontWeight: currentReminder ? 600 : 400 }}>2. Draft</span>
                  <span style={{ color: 'var(--color-muted)' }}>
                    {currentReminder ? (currentReminder.generation_source === 'ai' ? 'AI' : 'Template') : 'Pending'}
                  </span>
                </div>
                <span style={{ color: 'var(--color-border)' }}>→</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ color: currentReminder ? 'var(--color-primary)' : 'var(--color-muted)', fontWeight: 700 }}>
                    {currentReminder?.is_edited ? '●' : currentReminder ? '◐' : '○'}
                  </span>
                  <span style={{ fontWeight: currentReminder ? 600 : 400 }}>3. Review</span>
                  <span style={{ color: 'var(--color-muted)' }}>
                    {currentReminder?.is_edited ? 'Edited' : currentReminder ? 'Unedited' : 'Waiting'}
                  </span>
                </div>
                <span style={{ color: 'var(--color-border)' }}>→</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{
                    color: currentReminder?.status === 'approved' ? 'var(--color-primary)' : currentReminder?.status === 'rejected' ? 'var(--color-signal)' : 'var(--color-muted)',
                    fontWeight: 700,
                  }}>
                    {currentReminder?.status === 'approved' ? '✓' : currentReminder?.status === 'rejected' ? '✕' : '○'}
                  </span>
                  <span style={{ fontWeight: currentReminder?.status !== 'draft' && currentReminder ? 600 : 400 }}>4. Decision</span>
                  <span style={{ color: 'var(--color-muted)' }}>
                    {currentReminder?.status === 'approved' ? 'Approved' : currentReminder?.status === 'rejected' ? 'Rejected' : 'Pending'}
                  </span>
                </div>
                <span style={{ color: 'var(--color-border)' }}>→</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ color: 'var(--color-muted)', fontWeight: 700 }}>○</span>
                  <span style={{ color: 'var(--color-muted)' }}>5. Delivery</span>
                  <span style={{ color: 'var(--color-muted)', fontStyle: 'italic', fontSize: '10px' }}>(Disabled)</span>
                </div>
              </div>

              {/* Message Editor Area */}
              {currentReminder ? (
                <div style={{ display: 'flex', flexDirection: 'column', flex: 1, gap: 'var(--space-3)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <label style={{ fontSize: '12px', fontWeight: 500, color: 'var(--color-muted)' }}>
                      PATIENT-FACING FOLLOW-UP MESSAGE
                    </label>

                    {currentReminder.original_text && (
                      <button
                        type="button"
                        onClick={() => setShowOriginalDiff(!showOriginalDiff)}
                        className="btn-ghost"
                        style={{ fontSize: '11px', padding: '2px 8px' }}
                      >
                        {showOriginalDiff ? 'Hide Original Prompt Diff' : 'Compare with Original Draft'}
                      </button>
                    )}
                  </div>

                  {showOriginalDiff && currentReminder.original_text && (
                    <div style={{
                      backgroundColor: 'var(--color-paper)',
                      border: '1px dashed var(--color-border)',
                      padding: '10px 12px',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: '12px',
                    }}>
                      <div className="mono-label" style={{ fontSize: '9px', marginBottom: '4px' }}>ORIGINAL AI DRAFT</div>
                      <p style={{ fontStyle: 'italic', color: 'var(--color-muted)' }}>
                        "{currentReminder.original_text}"
                      </p>
                    </div>
                  )}

                  <textarea
                    rows={6}
                    value={draftText}
                    onChange={(e) => setDraftText(e.target.value)}
                    disabled={currentReminder.status !== 'draft'}
                    placeholder="Enter or refine follow-up reminder text..."
                    style={{
                      fontFamily: 'var(--font-sans)',
                      fontSize: '14px',
                      lineHeight: '1.6',
                      borderColor: draftText !== currentReminder.original_text ? 'var(--color-signal)' : 'var(--color-border)',
                    }}
                  />

                  {/* Character Counter & Length Bounds Indicator */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', color: 'var(--color-muted)' }}>
                      <span style={{
                        fontFamily: 'var(--font-mono)',
                        color: draftText.length < 15 || draftText.length > 350 ? 'var(--color-signal)' : 'var(--color-muted)',
                        fontWeight: 600,
                      }}>
                        {draftText.length}
                      </span>
                      <span>/ 350 characters (min: 15)</span>
                    </div>

                    {currentReminder.status === 'draft' && (
                      <button
                        onClick={handleSaveText}
                        disabled={isSaving || draftText === currentReminder.message_text}
                        className="btn-secondary"
                        style={{ fontSize: '12px' }}
                      >
                        {isSaving ? 'Saving...' : 'Save Draft Edits'}
                      </button>
                    )}
                  </div>

                  <div style={{
                    marginTop: 'auto',
                    padding: '12px',
                    backgroundColor: 'var(--color-paper)',
                    border: '1px solid var(--color-border)',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '12px',
                    color: 'var(--color-muted)',
                  }}>
                    <strong>Clinical Policy:</strong> Messages must remain non-prescriptive, free of medication instructions, and contain no hallucinated dates or times.
                  </div>
                </div>
              ) : (
                <div style={{
                  padding: 'var(--space-12) var(--space-6)',
                  textAlign: 'center',
                  backgroundColor: 'var(--color-paper)',
                  border: '1px dashed var(--color-border)',
                  borderRadius: 'var(--radius-sm)',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: 'var(--space-3)',
                }}>
                  <div style={{ fontSize: '15px', fontWeight: 500 }}>No follow-up reminder drafted yet</div>
                  <p style={{ color: 'var(--color-muted)', fontSize: '13px', maxWidth: '380px' }}>
                    Click below to generate a clinically guardrailed message based on encounter details for {selectedAppointment.patient_name}.
                  </p>
                  <button
                    onClick={handleGenerateDraft}
                    disabled={isLoading}
                    className="btn-primary"
                    style={{ marginTop: '8px' }}
                  >
                    {isLoading ? 'Generating Draft...' : 'Generate Follow-Up Draft'}
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--color-muted)' }}>
              Select an encounter from the left column to begin.
            </div>
          )}
        </div>

        {/* ============================================================== */}
        {/* COLUMN C: REVIEW & DECISION                                    */}
        {/* ============================================================== */}
        <div className="panel" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="panel-header" style={{ marginBottom: 'var(--space-3)' }}>
            <div>
              <span className="mono-label">Review</span>
              <h3 style={{ fontSize: '15px' }}>Decision</h3>
            </div>
          </div>

          {currentReminder ? (
            <div>
              {currentReminder.status === 'draft' ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <button
                    onClick={handleApprove}
                    disabled={isSaving}
                    className="btn-primary"
                    style={{ width: '100%', justifyContent: 'center' }}
                  >
                    {isSaving ? 'Processing...' : 'Approve Draft'}
                  </button>
                  <button
                    onClick={handleReject}
                    disabled={isSaving}
                    className="btn-danger"
                    style={{ width: '100%', justifyContent: 'center' }}
                  >
                    Reject Draft
                  </button>
                </div>
              ) : (
                <div style={{
                  padding: '10px',
                  backgroundColor: 'var(--color-paper)',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--color-border)',
                  textAlign: 'center',
                }}>
                  <span className="mono-label" style={{ fontSize: '9px' }}>STATUS</span>
                  <div style={{ fontWeight: 600, fontSize: '13px', marginTop: '2px', textTransform: 'capitalize' }}>
                    {currentReminder.status === 'approved' ? 'Approved' : currentReminder.status}
                  </div>
                  {currentReminder.approved_at && (
                    <div style={{ fontSize: '10px', color: 'var(--color-muted)', marginTop: '4px' }}>
                      {new Date(currentReminder.approved_at).toLocaleDateString()}
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div style={{ padding: 'var(--space-3)', textAlign: 'center', color: 'var(--color-muted)', fontSize: '12px' }}>
              Select encounter
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
