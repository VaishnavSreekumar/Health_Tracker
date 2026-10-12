/**
 * HealthTrack API Client
 * Centralized, typed HTTP client interfacing with the backend.
 */

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  environment: string;
}

export interface OverviewMetrics {
  total_patients: number;
  total_appointments: number;
  eligible_appointments: number;
  drafts_pending_review: number;
  approved_reminders: number;
  dispatched_reminders: number;
  failed_deliveries: number;
  ai_generated_count: number;
  fallback_count: number;
}

export interface ActivityItem {
  id: number;
  reminder_id: number;
  appointment_id: number;
  patient_name: string;
  action_type: string;
  timestamp: string;
  detail: string;
}

export interface Patient {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  created_at: string;
  appointment_count: number;
}

export interface Appointment {
  id: number;
  patient_id: number;
  patient_name: string;
  patient_email: string;
  appointment_type: string;
  appointment_datetime: string;
  is_eligible: boolean;
  has_reminder: boolean;
  reminder_id: number | null;
  reminder_status: string | null;
  created_at: string;
}

export interface ValidationCheck {
  id: string;
  label: string;
  passed: boolean;
  detail: string;
}

export interface ReminderDetail {
  id: number;
  appointment_id: number;
  patient_id: number;
  patient_name: string;
  patient_email: string;
  appointment_type: string;
  appointment_datetime: string;
  message_text: string;
  original_text: string;
  is_edited: boolean;
  status: 'draft' | 'approved' | 'rejected' | 'pending' | 'sent' | 'failed';
  generation_source: 'ai' | 'template_fallback';
  model_name: string | null;
  fallback_reason: string | null;
  validation_checks: ValidationCheck[];
  created_at: string;
  approved_at: string | null;
  approved_by: string | null;
  delivery_provider: string | null;
  delivery_reference_id: string | null;
  delivery_error: string | null;
}

export interface SystemSettings {
  project_name: string;
  version: string;
  environment: string;
  database_type: string;
  llm_provider: string;
  llm_model: string;
  llm_configured: boolean;
  llm_status: 'configured' | 'offline_fallback' | 'unverified';
  delivery_provider: string;
  delivery_enabled: boolean;
  delivery_status: 'disabled_safe_mode' | 'live' | 'unconfigured';
}

export interface DeliveryLog {
  id: number;
  reminder_id: number;
  patient_name: string;
  patient_email: string;
  status: string;
  provider: string;
  reference_id: string | null;
  error_detail: string | null;
  created_at: string;
}

const BASE_URL = '';

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${BASE_URL}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  });

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status} ${response.statusText}`;
    try {
      const errorJson = await response.json();
      if (errorJson.detail) {
        errorDetail = typeof errorJson.detail === 'string' ? errorJson.detail : JSON.stringify(errorJson.detail);
      }
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }

  return response.json() as Promise<T>;
}

export const api = {
  getHealth: () => request<HealthResponse>('/health'),
  getOverviewMetrics: () => request<OverviewMetrics>('/api/v1/overview/metrics'),
  getOverviewActivity: () => request<ActivityItem[]>('/api/v1/overview/activity'),

  getPatients: () => request<Patient[]>('/api/v1/patients'),
  createPatient: (data: { first_name: string; last_name: string; email: string }) =>
    request<Patient>('/api/v1/patients', { method: 'POST', body: JSON.stringify(data) }),

  getAppointments: (eligibleOnly = false) =>
    request<Appointment[]>(`/api/v1/appointments${eligibleOnly ? '?eligible_only=true' : ''}`),
  createAppointment: (data: { patient_id: number; appointment_type: string; appointment_datetime: string }) =>
    request<Appointment>('/api/v1/appointments', { method: 'POST', body: JSON.stringify(data) }),

  getReminders: (statusFilter?: string) =>
    request<ReminderDetail[]>(`/api/v1/reminders${statusFilter ? `?status=${statusFilter}` : ''}`),
  getReminder: (id: number) => request<ReminderDetail>(`/api/v1/reminders/${id}`),

  draftForAppointment: (appointmentId: number) =>
    request<ReminderDetail>(`/api/v1/reminders/appointments/${appointmentId}/draft`, { method: 'POST' }),

  updateReminderText: (id: number, messageText: string) =>
    request<ReminderDetail>(`/api/v1/reminders/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ message_text: messageText }),
    }),

  approveReminder: (id: number) =>
    request<ReminderDetail>(`/api/v1/reminders/${id}/approve`, { method: 'POST' }),

  rejectReminder: (id: number) =>
    request<ReminderDetail>(`/api/v1/reminders/${id}/reject`, { method: 'POST' }),

  dispatchReminder: (id: number) =>
    request<ReminderDetail>(`/api/v1/reminders/${id}/dispatch`, { method: 'POST' }),

  generateBatchReminders: (windowDays = 7) =>
    request<{
      status: string;
      total_reviewed: number;
      reminders_created: number;
      reminders_skipped: number;
      failures: number;
    }>('/api/v1/reminders/generate', {
      method: 'POST',
      body: JSON.stringify({ window_days: windowDays }),
    }),

  getDeliveryLogs: () => request<DeliveryLog[]>('/api/v1/delivery/logs'),
  getSystemSettings: () => request<SystemSettings>('/api/v1/system/settings'),

  resetWorkspace: () => request<{ status: string; message: string }>('/api/v1/system/reset', { method: 'POST' }),
};
