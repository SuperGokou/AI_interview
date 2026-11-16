import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { AdminShell, Card, Button, Pill } from '../../ui';
import { api } from '../../lib/api';
import type { ReportOut, CheatResponse, RiskLevel, IntegrityLevel, Transcript } from '../../types';

const INTEGRITY_COLOR: Record<IntegrityLevel, string> = {
  green: '#2BE5A4',
  yellow: '#FACC15',
  red: '#FB5070',
};

const INTEGRITY_LABEL: Record<IntegrityLevel, string> = {
  green: '正常',
  yellow: '警告',
  red: '风险',
};

const RISK_COLOR: Record<RiskLevel, string> = {
  low: '#2BE5A4',
  medium: '#FACC15',
  high: '#FB5070',
};

const RISK_LABEL: Record<RiskLevel, string> = {
  low: '低风险',
  medium: '中风险',
  high: '高风险',
};

const SEVERITY_COLOR: Record<RiskLevel, string> = {
  low: '#8593AD',
  medium: '#FACC15',
  high: '#FB5070',
};

interface ScoreCardProps {
  label: string;
  value: number | null;
  accent: string;
}

function ScoreCard({ label, value, accent }: ScoreCardProps) {
  return (
    <Card className="flex flex-col items-center gap-2 py-5">
      <span className="text-xs text-muted text-center">{label}</span>
      <span className="text-3xl font-bold" style={{ color: value !== null ? accent : '#8593AD' }}>
        {value !== null ? value : '—'}
      </span>
    </Card>
  );
}

export default function ReportDetail() {
  const { token } = useParams<{ token: string }>();
  const [report, setReport] = useState<ReportOut | null>(null);
  const [cheat, setCheat] = useState<CheatResponse | null>(null);
  const [transcripts, setTranscripts] = useState<Transcript[]>([]);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);

  function loadReport(t: string) {
    setLoading(true);
    setNotFound(false);
    Promise.all([
      api.getReport(t).catch((err: unknown) => {
        if (err instanceof Error && err.message.includes('404')) {
          setNotFound(true);
          return null;
        }
        throw err;
      }),
      api.getCheat(t).catch(() => null),
      api.listTranscripts(t).catch(() => []),
    ])
      .then(([r, c, tx]) => {
        setReport(r);
        if (c) setCheat(c);
        setTranscripts(tx ?? []);
        setLoading(false);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : '加载失败');
        setLoading(false);
      });
  }

  useEffect(() => {
    if (token) loadReport(token);
  }, [token]);

  async function handleGenerate() {
    if (!token) return;
    setGenerating(true);
    try {
      const r = await api.createReport(token);
      setReport(r);
      setNotFound(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '生成报告失败');
    } finally {
      setGenerating(false);
    }
  }

  return (
    <AdminShell active="面试记录">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-text">面试报告</h1>
        <p className="text-sm text-muted mt-1 font-mono">{token}</p>
      </div>

      {error && <p className="text-red text-sm mb-4">错误：{error}</p>}
      {loading && <p className="text-muted text-sm">加载中…</p>}

      {!loading && notFound && !report && (
        <Card className="mb-6">
          <p className="text-muted text-sm mb-4">该候选人的报告尚未生成。</p>
          <Button onClick={() => void handleGenerate()} disabled={generating}>
            {generating ? '生成中…' : '生成报告'}
          </Button>
        </Card>
      )}

      {!loading && report && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
            <ScoreCard label="专业能力" value={report.score_professional} accent="#2DD4EF" />
            <ScoreCard label="沟通表达" value={report.score_communication} accent="#A78BFA" />
            <ScoreCard label="岗位匹配" value={report.score_job_match} accent="#2BE5A4" />
            <ScoreCard label="仪态表现" value={report.score_demeanor} accent="#FACC15" />
            <Card className="flex flex-col items-center gap-2 py-5">
              <span className="text-xs text-muted text-center">AI 风险</span>
              {report.ai_risk_level ? (
                <Pill color={RISK_COLOR[report.ai_risk_level]}>
                  {RISK_LABEL[report.ai_risk_level]}
                </Pill>
              ) : (
                <span className="text-muted text-2xl">—</span>
              )}
            </Card>
          </div>

          {report.feedback && (
            <Card className="mb-6">
              <h2 className="text-sm font-semibold text-text mb-3">反馈详情</h2>
              <p className="text-sm text-muted leading-relaxed whitespace-pre-wrap">{report.feedback}</p>
            </Card>
          )}

          {report.overall && (
            <Card className="mb-6">
              <h2 className="text-sm font-semibold text-text mb-3">综合评价</h2>
              <p className="text-sm text-muted leading-relaxed whitespace-pre-wrap">{report.overall}</p>
            </Card>
          )}
        </>
      )}

      {!loading && transcripts.length > 0 && (
        <Card className="mb-6">
          <h2 className="text-sm font-semibold text-text mb-4">完整对话转写</h2>
          <div className="flex flex-col gap-3">
            {transcripts.map((tx, i) => (
              <div
                key={i}
                className={`flex gap-3 ${tx.role === 'candidate' ? 'justify-end' : 'justify-start'}`}
              >
                {tx.role === 'interviewer' && (
                  <span
                    className="shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold mt-0.5"
                    style={{ background: '#0E4F6A', color: '#2DD4EF' }}
                    aria-hidden="true"
                  >
                    I
                  </span>
                )}
                <div
                  className="max-w-[78%] rounded-xl px-4 py-2.5"
                  style={
                    tx.role === 'interviewer'
                      ? { background: '#0E3A4F', border: '1px solid #1A5F7A', color: '#7DD3F5' }
                      : { background: '#1E2A3A', border: '1px solid #2A3A4A', color: '#C8D8E8' }
                  }
                >
                  <p className="text-sm leading-relaxed">{tx.text}</p>
                  {tx.ts && (
                    <p className="text-xs mt-1 opacity-50">{tx.ts}</p>
                  )}
                </div>
                {tx.role === 'candidate' && (
                  <span
                    className="shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold mt-0.5"
                    style={{ background: '#1E3A2A', color: '#2BE5A4' }}
                    aria-hidden="true"
                  >
                    C
                  </span>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {!loading && cheat && (
        <Card>
          <div className="flex items-center gap-3 mb-4">
            <h2 className="text-sm font-semibold text-text">诚信检测</h2>
            {cheat.integrity_level && (
              <Pill color={INTEGRITY_COLOR[cheat.integrity_level]}>
                {INTEGRITY_LABEL[cheat.integrity_level]}
              </Pill>
            )}
          </div>

          {cheat.events.length === 0 ? (
            <p className="text-muted text-sm py-4 text-center">未检测到异常事件。</p>
          ) : (
            <div className="relative pl-4">
              {/* Timeline spine */}
              <div
                className="absolute left-0 top-2 bottom-2 w-px"
                style={{ background: '#243049' }}
                aria-hidden="true"
              />
              <div className="flex flex-col gap-4">
                {cheat.events.map((ev, i) => (
                  <div key={i} className="relative">
                    {/* Timeline dot */}
                    <span
                      className="absolute -left-[18px] top-1 w-2.5 h-2.5 rounded-full border-2"
                      style={{
                        background: SEVERITY_COLOR[ev.severity],
                        borderColor: '#121A2E',
                      }}
                      aria-hidden="true"
                    />
                    <div className="flex items-start gap-3 flex-wrap">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap mb-1">
                          <span className="text-sm font-medium text-text">{ev.kind}</span>
                          <Pill color={SEVERITY_COLOR[ev.severity]} dot={false}>
                            {ev.severity === 'low' ? '低' : ev.severity === 'medium' ? '中' : '高'}
                          </Pill>
                          {ev.ts && (
                            <span className="text-xs text-muted">{ev.ts}</span>
                          )}
                        </div>
                        {ev.evidence && (
                          <p className="text-xs text-muted">{ev.evidence}</p>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}
    </AdminShell>
  );
}
