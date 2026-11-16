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
  CreateSupervisorLinksResponse,
  SupervisorLink,
  SupervisorSessionInfo,
  SupervisorTranscriptFeed,
} from '../types';

const ADMIN_KEY_STORAGE_KEY = 'kunyao.adminKey';

function readEnv(name: string): string {
  const env = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env;
  return env?.[name]?.trim() ?? '';
}

function stripTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

function apiUrl(path: string): string {
  const origin = stripTrailingSlash(readEnv('VITE_API_ORIGIN') || readEnv('VITE_API_BASE_URL'));
  return origin ? `${origin}${path}` : path;
}

function readAdminKey(): string {
  const envKey = readEnv('VITE_ADMIN_API_KEY');
  if (envKey) return envKey;
  if (typeof window === 'undefined') return '';
  return window.localStorage.getItem(ADMIN_KEY_STORAGE_KEY)?.trim() ?? '';
}

function adminHeaders(): Record<string, string> {
  const key = readAdminKey();
  return key ? { 'X-Admin-Key': key } : {};
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const url = apiUrl(path);
  const res = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

async function adminReq<T>(path: string, init?: RequestInit): Promise<T> {
  return req<T>(path, {
    ...init,
    headers: { ...adminHeaders(), ...(init?.headers ?? {}) },
  });
}

export const api = {
  health: () => req<HealthResponse>('/api/health'),

  createSession: (job_id: number, candidate_name: string) =>
    adminReq<CreateSessionResponse>('/api/sessions', {
      method: 'POST',
      body: JSON.stringify({ job_id, candidate_name }),
    }),

  getSession: (token: string) => req<SessionInfo>(`/api/sessions/${token}`),

  consent: (token: string) =>
    req<{ ok: boolean; consented: boolean }>(`/api/sessions/${token}/consent`, {
      method: 'POST',
    }),

  getCheat: (token: string) =>
    adminReq<CheatResponse>(`/api/sessions/${token}/cheat`),

  createReport: (token: string) =>
    adminReq<ReportOut>(`/api/sessions/${token}/report`, { method: 'POST' }),

  getReport: (token: string) =>
    adminReq<ReportOut>(`/api/sessions/${token}/report`),

  // Jobs
  listJobs: () => adminReq<Job[]>('/api/jobs'),
  createJob: (body: Omit<Job, 'id' | 'question_count' | 'candidate_count'>) =>
    adminReq<Job>('/api/jobs', { method: 'POST', body: JSON.stringify(body) }),
  getJob: (id: number) => adminReq<Job>(`/api/jobs/${id}`),
  updateJob: (id: number, body: Partial<Omit<Job, 'id' | 'question_count' | 'candidate_count'>>) =>
    adminReq<Job>(`/api/jobs/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteJob: (id: number) => adminReq<{ ok: boolean }>(`/api/jobs/${id}`, { method: 'DELETE' }),

  // Questions
  listQuestions: (jobId: number) => adminReq<Question[]>(`/api/jobs/${jobId}/questions`),
  createQuestion: (jobId: number, body: Omit<Question, 'id' | 'job_id'>) =>
    adminReq<Question>(`/api/jobs/${jobId}/questions`, { method: 'POST', body: JSON.stringify(body) }),
  updateQuestion: (id: number, body: Partial<Omit<Question, 'id' | 'job_id'>>) =>
    adminReq<Question>(`/api/questions/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteQuestion: (id: number) =>
    adminReq<{ ok: boolean }>(`/api/questions/${id}`, { method: 'DELETE' }),

  // Sessions list
  listSessions: () => adminReq<SessionListItem[]>('/api/sessions'),

  // Dashboard
  dashboardStats: () => adminReq<DashboardStats>('/api/dashboard/stats'),

  // Transcripts
  listTranscripts: (token: string) =>
    adminReq<Transcript[]>(`/api/sessions/${token}/transcripts`),

  createSupervisorLinks: (token: string, count = 1, labels?: string[]) =>
    adminReq<CreateSupervisorLinksResponse>(`/api/sessions/${token}/supervisors`, {
      method: 'POST',
      body: JSON.stringify(labels?.length ? { labels } : { count }),
    }),

  listSupervisorLinks: (token: string) =>
    adminReq<SupervisorLink[]>(`/api/sessions/${token}/supervisors`),

  getSupervisorSession: (token: string) =>
    req<SupervisorSessionInfo>(`/api/supervisors/${token}`),

  listSupervisorTranscripts: (token: string) =>
    req<SupervisorTranscriptFeed>(`/api/supervisors/${token}/transcripts`),
};

export function interviewWsUrl(token: string): string {
  const explicitWsOrigin = stripTrailingSlash(readEnv('VITE_WS_ORIGIN'));
  if (explicitWsOrigin) {
    return `${explicitWsOrigin}/ws/interview?token=${encodeURIComponent(token)}`;
  }

  const apiOrigin = stripTrailingSlash(readEnv('VITE_API_ORIGIN') || readEnv('VITE_API_BASE_URL'));
  if (apiOrigin) {
    const url = new URL(apiOrigin);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${url.origin}/ws/interview?token=${encodeURIComponent(token)}`;
  }

  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${location.host}/ws/interview?token=${encodeURIComponent(token)}`;
}
