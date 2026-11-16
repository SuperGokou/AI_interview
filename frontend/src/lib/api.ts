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

/** Error carrying the HTTP status and the server's own explanation when it sent one. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function errorMessage(res: Response, path: string): Promise<string> {
  try {
    const body: unknown = await res.json();
    if (body && typeof body === 'object' && 'detail' in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === 'string' && detail) return detail;
    }
  } catch {
    // Non-JSON error body: fall through to the generic message.
  }
  return `API ${path} failed: ${res.status}`;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new ApiError(await errorMessage(res, path), res.status);
  return res.json() as Promise<T>;
}

// Admin endpoints are protected by HTTP Basic auth at the server boundary; the
// browser attaches the credentials itself, so no key is stored or sent from JS.
const adminReq = req;

/** Link tokens are URL-safe today, but never trust that when building a path. */
const t = encodeURIComponent;

export const api = {
  health: () => req<HealthResponse>('/api/health'),

  createSession: (job_id: number, candidate_name: string) =>
    adminReq<CreateSessionResponse>('/api/sessions', {
      method: 'POST',
      body: JSON.stringify({ job_id, candidate_name }),
    }),

  getSession: (token: string) => req<SessionInfo>(`/api/sessions/${t(token)}`),

  consent: (token: string) =>
    req<{ ok: boolean; consented: boolean }>(`/api/sessions/${t(token)}/consent`, {
      method: 'POST',
    }),

  getCheat: (token: string) =>
    adminReq<CheatResponse>(`/api/sessions/${t(token)}/cheat`),

  createReport: (token: string) =>
    adminReq<ReportOut>(`/api/sessions/${t(token)}/report`, { method: 'POST' }),

  getReport: (token: string) =>
    adminReq<ReportOut>(`/api/sessions/${t(token)}/report`),

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
    adminReq<Transcript[]>(`/api/sessions/${t(token)}/transcripts`),

  createSupervisorLinks: (token: string, count = 1, labels?: string[]) =>
    adminReq<CreateSupervisorLinksResponse>(`/api/sessions/${t(token)}/supervisors`, {
      method: 'POST',
      body: JSON.stringify(labels?.length ? { labels } : { count }),
    }),

  listSupervisorLinks: (token: string) =>
    adminReq<SupervisorLink[]>(`/api/sessions/${t(token)}/supervisors`),

  getSupervisorSession: (token: string) =>
    req<SupervisorSessionInfo>(`/api/supervisors/${t(token)}`),

  listSupervisorTranscripts: (token: string) =>
    req<SupervisorTranscriptFeed>(`/api/supervisors/${t(token)}/transcripts`),
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
