import { useState, useEffect, type FC, type FormEvent } from 'react';
import { api, type Appointment, type Patient } from '../api/client';

interface AppointmentsScreenProps {
  onDraftInStudio: (appointmentId: number) => void;
  onNavigateToPatients?: () => void;
}

export const AppointmentsScreen: FC<AppointmentsScreenProps> = ({
  onDraftInStudio,
  onNavigateToPatients,
}) => {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [eligibleOnly, setEligibleOnly] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // New Appointment modal
  const [showModal, setShowModal] = useState<boolean>(false);
  const [patientId, setPatientId] = useState<number | ''>('');
  const [appointmentType, setAppointmentType] = useState<string>('routine_checkup');
  const [appointmentDatetime, setAppointmentDatetime] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [formError, setFormError] = useState<string | null>(null);

  const fetchData = async () => {
    setErrorMessage(null);
    try {
      const [aptData, pData] = await Promise.all([
        api.getAppointments(eligibleOnly),
        api.getPatients(),
      ]);
      setAppointments(aptData);
      setPatients(pData);
      if (pData.length > 0 && patientId === '') {
        setPatientId(pData[0].id);
      }
    } catch (err: any) {
      setErrorMessage(`Failed to load appointments: ${err.message}`);
    }
  };

  useEffect(() => {
    fetchData();
  }, [eligibleOnly]);

  const handleCreateAppointment = async (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!patientId || !appointmentDatetime) {
      setFormError('Patient and encounter date/time are required.');
      return;
    }

    setIsSubmitting(true);
    try {
      // Ensure ISO string with UTC indicator
      const dt = new Date(appointmentDatetime).toISOString();
      await api.createAppointment({
        patient_id: Number(patientId),
        appointment_type: appointmentType,
        appointment_datetime: dt,
      });
      setShowModal(false);
      setAppointmentDatetime('');
      fetchData();
    } catch (err: any) {
      setFormError(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div style={{ maxWidth: '1440px', margin: '0 auto', padding: 'var(--space-6)', width: '100%' }}>
      {/* Header */}
      <div style={{ marginBottom: 'var(--space-6)', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <div className="mono-label">Clinical Encounter Schedule</div>
          <h1 style={{ marginTop: '2px' }}>Appointments & Encounters</h1>
          <p style={{ color: 'var(--color-muted)', fontSize: '13px', marginTop: '4px' }}>
            Encounter timeline governed by the clinic's 7-day follow-up lookback eligibility window.
          </p>
        </div>

        <button onClick={() => setShowModal(true)} className="btn-primary">
          + Record Encounter
        </button>
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

      {/* Filter Toolbar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-4)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <label style={{ fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={eligibleOnly}
              onChange={(e) => setEligibleOnly(e.target.checked)}
              style={{ width: 'auto' }}
            />
            Show only encounters in 7-day eligibility window
          </label>
        </div>

        <span className="mono-label">
          {appointments.length} encounter{appointments.length === 1 ? '' : 's'} listed
        </span>
      </div>

      {/* Appointments Table */}
      <div className="panel" style={{ padding: 0, overflow: 'hidden' }}>
        <table className="editorial-table">
          <thead>
            <tr>
              <th style={{ width: '100px' }}>Encounter</th>
              <th style={{ width: '220px' }}>Patient Name</th>
              <th style={{ width: '180px' }}>Encounter Type</th>
              <th style={{ width: '180px' }}>Encounter Date</th>
              <th style={{ width: '140px' }}>7d Window</th>
              <th style={{ width: '140px' }}>Follow-Up Status</th>
              <th style={{ width: '140px', textAlign: 'right' }}>Studio Action</th>
            </tr>
          </thead>
          <tbody>
            {appointments.map((apt) => {
              const dt = new Date(apt.appointment_datetime);
              return (
                <tr key={apt.id}>
                  <td className="font-mono" style={{ fontSize: '12px' }}>
                    APT-{apt.id.toString().padStart(4, '0')}
                  </td>
                  <td style={{ fontWeight: 600 }}>
                    {apt.patient_name}
                  </td>
                  <td>
                    <span style={{ textTransform: 'capitalize' }}>
                      {apt.appointment_type.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="font-mono" style={{ fontSize: '12px' }}>
                    {dt.toLocaleDateString('en-US', {
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric',
                    })}
                  </td>
                  <td>
                    {apt.is_eligible ? (
                      <span className="badge badge-eligible">Eligible</span>
                    ) : (
                      <span className="badge badge-ineligible">Outside Window</span>
                    )}
                  </td>
                  <td>
                    {apt.has_reminder ? (
                      <span className={`badge badge-${apt.reminder_status || 'draft'}`}>
                        {apt.reminder_status}
                      </span>
                    ) : (
                      <span style={{ fontSize: '12px', color: 'var(--color-muted)' }}>None</span>
                    )}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <button
                      onClick={() => onDraftInStudio(apt.id)}
                      className="btn-secondary"
                      style={{ fontSize: '11px', padding: '4px 10px' }}
                    >
                      {apt.has_reminder ? 'Open in Studio' : 'Draft Follow-up'}
                    </button>
                  </td>
                </tr>
              );
            })}

            {appointments.length === 0 && (
              <tr>
                <td colSpan={7} style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--color-muted)' }}>
                  {eligibleOnly ? (
                    'No encounters within the 7-day lookback window. Uncheck filter or record a recent encounter.'
                  ) : patients.length === 0 ? (
                    <div>
                      <p style={{ marginBottom: '12px' }}>
                        No clinical encounters recorded. Register your first patient in the Patient Register to begin scheduling visits.
                      </p>
                      {onNavigateToPatients && (
                        <button
                          type="button"
                          onClick={onNavigateToPatients}
                          className="btn-primary"
                          style={{ fontSize: '12px', padding: '6px 14px' }}
                        >
                          Register Patient
                        </button>
                      )}
                    </div>
                  ) : (
                    'No encounters recorded yet. Click "+ Record Encounter" above to schedule a patient visit.'
                  )}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Modal: Record Encounter */}
      {showModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(25, 39, 32, 0.45)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 100,
        }}>
          <div className="panel" style={{ width: '460px', backgroundColor: 'var(--color-surface)' }}>
            <div className="panel-header">
              <div>
                <span className="mono-label">New Encounter</span>
                <h3 style={{ fontSize: '16px' }}>Record Clinical Appointment</h3>
              </div>
              <button onClick={() => setShowModal(false)} className="btn-ghost" style={{ padding: '2px 8px' }}>
                ✕
              </button>
            </div>

            {formError && (
              <div style={{
                backgroundColor: 'var(--status-rejected-bg)',
                border: '1px solid var(--status-rejected-border)',
                color: 'var(--status-rejected-text)',
                padding: '8px 12px',
                borderRadius: 'var(--radius-sm)',
                marginBottom: 'var(--space-4)',
                fontSize: '12px',
              }}>
                {formError}
              </div>
            )}

            <form onSubmit={handleCreateAppointment} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              <div>
                <label style={{ fontSize: '12px', fontWeight: 500, color: 'var(--color-muted)', display: 'block', marginBottom: '4px' }}>
                  PATIENT
                </label>
                <select
                  value={patientId}
                  onChange={(e) => setPatientId(Number(e.target.value))}
                  required
                >
                  {patients.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.first_name} {p.last_name} (PAT-{p.id})
                    </option>
                  ))}
                </select>
                {patients.length === 0 && (
                  <span style={{ fontSize: '11px', color: 'var(--color-signal)', marginTop: '2px', display: 'block' }}>
                    No patients registered. Please register a patient first.
                  </span>
                )}
              </div>

              <div>
                <label style={{ fontSize: '12px', fontWeight: 500, color: 'var(--color-muted)', display: 'block', marginBottom: '4px' }}>
                  ENCOUNTER TYPE
                </label>
                <select
                  value={appointmentType}
                  onChange={(e) => setAppointmentType(e.target.value)}
                >
                  <option value="routine_checkup">Routine Checkup</option>
                  <option value="follow_up">Follow-up Visit</option>
                  <option value="specialist_consultation">Specialist Consultation</option>
                  <option value="annual_physical">Annual Physical</option>
                  <option value="post_procedure">Post-Procedure Recovery</option>
                </select>
              </div>

              <div>
                <label style={{ fontSize: '12px', fontWeight: 500, color: 'var(--color-muted)', display: 'block', marginBottom: '4px' }}>
                  ENCOUNTER DATE & TIME
                </label>
                <input
                  type="datetime-local"
                  required
                  value={appointmentDatetime}
                  onChange={(e) => setAppointmentDatetime(e.target.value)}
                />
                <span style={{ fontSize: '11px', color: 'var(--color-muted)', marginTop: '2px', display: 'block' }}>
                  To be eligible for follow-up reminders, the encounter must fall within the previous 7 days.
                </span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: 'var(--space-4)' }}>
                <button type="button" onClick={() => setShowModal(false)} className="btn-secondary">
                  Cancel
                </button>
                <button type="submit" disabled={isSubmitting || patients.length === 0} className="btn-primary">
                  {isSubmitting ? 'Recording...' : 'Save Encounter'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
