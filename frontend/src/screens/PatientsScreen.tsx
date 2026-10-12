import { useState, useEffect, type FC, type FormEvent } from 'react';
import { api, type Patient } from '../api/client';

export const PatientsScreen: FC = () => {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // New patient modal state
  const [showModal, setShowModal] = useState<boolean>(false);
  const [firstName, setFirstName] = useState<string>('');
  const [lastName, setLastName] = useState<string>('');
  const [email, setEmail] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [formError, setFormError] = useState<string | null>(null);

  const fetchPatients = async () => {
    setErrorMessage(null);
    try {
      const data = await api.getPatients();
      setPatients(data);
    } catch (err: any) {
      setErrorMessage(`Failed to load patient register: ${err.message}`);
    }
  };

  useEffect(() => {
    fetchPatients();
  }, []);

  const handleCreatePatient = async (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!firstName.trim() || !lastName.trim() || !email.trim()) {
      setFormError('First name, last name, and email are required.');
      return;
    }

    setIsSubmitting(true);
    try {
      await api.createPatient({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: email.trim().toLowerCase(),
      });
      setShowModal(false);
      setFirstName('');
      setLastName('');
      setEmail('');
      fetchPatients();
    } catch (err: any) {
      setFormError(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const filteredPatients = patients.filter((p) => {
    const query = searchQuery.toLowerCase();
    return (
      p.first_name.toLowerCase().includes(query) ||
      p.last_name.toLowerCase().includes(query) ||
      p.email.toLowerCase().includes(query) ||
      `PAT-${p.id}`.toLowerCase().includes(query)
    );
  });

  return (
    <div style={{ maxWidth: '1440px', margin: '0 auto', padding: 'var(--space-6)', width: '100%' }}>
      {/* Header */}
      <div style={{ marginBottom: 'var(--space-6)', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <div className="mono-label">Clinical Directory</div>
          <h1 style={{ marginTop: '2px' }}>Patient Register</h1>
          <p style={{ color: 'var(--color-muted)', fontSize: '13px', marginTop: '4px' }}>
            Validated synthetic patient profiles and clinical encounter counts.
          </p>
        </div>

        <button onClick={() => setShowModal(true)} className="btn-primary">
          + Register Patient
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

      {/* Search Bar */}
      <div style={{ marginBottom: 'var(--space-4)', maxWidth: '380px' }}>
        <input
          type="text"
          placeholder="Filter by name, synthetic email, or ID..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
      </div>

      {/* Patient Table */}
      <div className="panel" style={{ padding: 0, overflow: 'hidden' }}>
        <table className="editorial-table">
          <thead>
            <tr>
              <th style={{ width: '100px' }}>Patient ID</th>
              <th style={{ width: '220px' }}>Full Name</th>
              <th>Synthetic Email</th>
              <th style={{ width: '140px' }}>Encounters</th>
              <th style={{ width: '160px' }}>Registered Date</th>
            </tr>
          </thead>
          <tbody>
            {filteredPatients.map((p) => (
              <tr key={p.id}>
                <td className="font-mono" style={{ fontSize: '12px' }}>
                  PAT-{p.id.toString().padStart(4, '0')}
                </td>
                <td style={{ fontWeight: 600 }}>
                  {p.first_name} {p.last_name}
                </td>
                <td className="font-mono" style={{ fontSize: '12px', color: 'var(--color-muted)' }}>
                  {p.email}
                </td>
                <td>
                  <span className="badge badge-draft">
                    {p.appointment_count} visit{p.appointment_count === 1 ? '' : 's'}
                  </span>
                </td>
                <td className="font-mono" style={{ fontSize: '12px', color: 'var(--color-muted)' }}>
                  {new Date(p.created_at).toLocaleDateString('en-US', {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric',
                  })}
                </td>
              </tr>
            ))}

            {filteredPatients.length === 0 && (
              <tr>
                <td colSpan={5} style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--color-muted)' }}>
                  {searchQuery ? 'No matching patient records found.' : 'No patients registered yet. Click "+ Register Patient" above to add your first patient.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Modal: Register Patient */}
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
          <div className="panel" style={{ width: '440px', backgroundColor: 'var(--color-surface)' }}>
            <div className="panel-header">
              <div>
                <span className="mono-label">New Record</span>
                <h3 style={{ fontSize: '16px' }}>Register Patient</h3>
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

            <form onSubmit={handleCreatePatient} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              <div>
                <label style={{ fontSize: '12px', fontWeight: 500, color: 'var(--color-muted)', display: 'block', marginBottom: '4px' }}>
                  FIRST NAME
                </label>
                <input
                  type="text"
                  required
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  placeholder="e.g. Clara"
                />
              </div>

              <div>
                <label style={{ fontSize: '12px', fontWeight: 500, color: 'var(--color-muted)', display: 'block', marginBottom: '4px' }}>
                  LAST NAME
                </label>
                <input
                  type="text"
                  required
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  placeholder="e.g. Barton"
                />
              </div>

              <div>
                <label style={{ fontSize: '12px', fontWeight: 500, color: 'var(--color-muted)', display: 'block', marginBottom: '4px' }}>
                  SYNTHETIC EMAIL (IDENTIFIER)
                </label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="e.g. clara.barton@example.synthetic"
                />
                <span style={{ fontSize: '11px', color: 'var(--color-muted)', marginTop: '2px', display: 'block' }}>
                  Notice: Only synthetic email identifiers are accepted.
                </span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: 'var(--space-4)' }}>
                <button type="button" onClick={() => setShowModal(false)} className="btn-secondary">
                  Cancel
                </button>
                <button type="submit" disabled={isSubmitting} className="btn-primary">
                  {isSubmitting ? 'Registering...' : 'Save Patient Record'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
