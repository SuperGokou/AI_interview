import type {
  SessionInfo,
  CreateSessionResponse,
  CheatResponse,
  ReportOut,
  HealthResponse,
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
};

export function interviewWsUrl(token: string): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${location.host}/ws/interview?token=${encodeURIComponent(token)}`;
}
