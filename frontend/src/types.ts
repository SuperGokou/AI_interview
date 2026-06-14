export type IntegrityLevel = 'green' | 'yellow' | 'red';
export type RiskLevel = 'low' | 'medium' | 'high';

export interface JobSummary {
  title: string;
  language: string;
  duration_minutes: number;
  interviewer_voice: string;
}

export interface SessionInfo {
  token: string;
  status: string;
  candidate_name: string;
  consented: boolean;
  job: JobSummary;
}

export interface CreateSessionResponse {
  token: string;
  status: string;
}

export interface CheatEvent {
  kind: string;
  severity: RiskLevel;
  evidence: string | null;
  ts: string | null;
}

export interface CheatResponse {
  integrity_level: IntegrityLevel;
  events: CheatEvent[];
}

export interface ReportOut {
  score_professional: number | null;
  score_communication: number | null;
  score_job_match: number | null;
  score_demeanor: number | null;
  ai_risk_level: RiskLevel | null;
  feedback: string | null;
  overall: string | null;
}

export interface HealthResponse {
  status: string;
  database: string;
  models: { qwen: boolean; deepseek: boolean };
}
