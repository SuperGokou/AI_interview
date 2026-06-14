export type IntegrityLevel = 'green' | 'yellow' | 'red';
export type RiskLevel = 'low' | 'medium' | 'high';
export type JobStatus = 'active' | 'draft' | 'closed';
export type Difficulty = '初级' | '中级' | '高级';
export type InterviewerVoice =
  | 'Serena'
  | 'Sunny'
  | 'Kiki'
  | 'Tina'
  | 'Ethan'
  | 'Dylan'
  | 'Peter'
  | 'Aiden';

export interface Job {
  id: number;
  title: string;
  jd: string;
  interviewer_voice: InterviewerVoice;
  language: string;
  duration_minutes: number;
  status: JobStatus;
  question_count: number;
  candidate_count: number;
}

export interface Question {
  id: number;
  job_id: number;
  prompt: string;
  key_points: string;
  reference_answer: string;
  difficulty: Difficulty;
  is_probe: boolean;
}

export interface SessionListItem {
  token: string;
  candidate_name: string;
  job_title: string;
  status: string;
  integrity_level: IntegrityLevel | null;
  score_overall: number | null;
  created_at: string;
}

export interface DashboardStats {
  active_jobs: number;
  pending_interviews: number;
  completed_interviews: number;
  high_risk: number;
  recent: SessionListItem[];
}

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

export interface Transcript {
  role: string;
  text: string;
  ts: string | null;
}
