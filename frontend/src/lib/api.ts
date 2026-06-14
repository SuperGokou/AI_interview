import type {
  SessionInfo,
  CreateSessionResponse,
  CheatResponse,
  ReportOut,
  HealthResponse,
  Job,
  Question,
  SessionListItem,
  DashboardStats,
  Transcript,
} from '../types';

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => req<HealthResponse>('/api/health'),

  createSession: (job_id: number, candidate_name: string) =>
    req<CreateSessionResponse>('/api/sessions', {
      method: 'POST',
      body: JSON.stringify({ job_id, candidate_name }),
    }),

  getSession: (token: string) => req<SessionInfo>(`/api/sessions/${token}`),

  consent: (token: string) =>
    req<{ ok: boolean; consented: boolean }>(`/api/sessions/${token}/consent`, {
      method: 'POST',
    }),

  getCheat: (token: string) =>
    req<CheatResponse>(`/api/sessions/${token}/cheat`),

  createReport: (token: string) =>
    req<ReportOut>(`/api/sessions/${token}/report`, { method: 'POST' }),

  getReport: (token: string) =>
    req<ReportOut>(`/api/sessions/${token}/report`),

  // Jobs
  listJobs: () => req<Job[]>('/api/jobs'),
  createJob: (body: Omit<Job, 'id' | 'question_count' | 'candidate_count'>) =>
    req<Job>('/api/jobs', { method: 'POST', body: JSON.stringify(body) }),
  getJob: (id: number) => req<Job>(`/api/jobs/${id}`),
  updateJob: (id: number, body: Partial<Omit<Job, 'id' | 'question_count' | 'candidate_count'>>) =>
    req<Job>(`/api/jobs/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteJob: (id: number) => req<{ ok: boolean }>(`/api/jobs/${id}`, { method: 'DELETE' }),

  // Questions
  listQuestions: (jobId: number) => req<Question[]>(`/api/jobs/${jobId}/questions`),
  createQuestion: (jobId: number, body: Omit<Question, 'id' | 'job_id'>) =>
    req<Question>(`/api/jobs/${jobId}/questions`, { method: 'POST', body: JSON.stringify(body) }),
  updateQuestion: (id: number, body: Partial<Omit<Question, 'id' | 'job_id'>>) =>
    req<Question>(`/api/questions/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteQuestion: (id: number) =>
    req<{ ok: boolean }>(`/api/questions/${id}`, { method: 'DELETE' }),

  // Sessions list
  listSessions: () => req<SessionListItem[]>('/api/sessions'),

  // Dashboard
  dashboardStats: () => req<DashboardStats>('/api/dashboard/stats'),

  // Transcripts
  listTranscripts: (token: string) =>
    req<Transcript[]>(`/api/sessions/${token}/transcripts`),
};

export function interviewWsUrl(token: string): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${location.host}/ws/interview?token=${encodeURIComponent(token)}`;
}
