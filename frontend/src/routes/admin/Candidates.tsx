import { useEffect, useId, useState } from 'react';
import { AdminShell, Card, Button, Field, Pill } from '../../ui';
import { api } from '../../lib/api';
import type { Job, SessionListItem, IntegrityLevel } from '../../types';

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

function statusColor(status: string): string {
  if (status === 'completed') return '#2BE5A4';
  if (status === 'in_progress') return '#2DD4EF';
  if (status === 'pending') return '#FACC15';
  return '#8593AD';
}

function statusLabel(status: string): string {
  if (status === 'completed') return '已完成';
  if (status === 'in_progress') return '进行中';
  if (status === 'pending') return '待面试';
  return status;
}

export default function Candidates() {
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // New interview link form
  const [showLinkForm, setShowLinkForm] = useState(false);
  const [selectedJobId, setSelectedJobId] = useState('');
  const [candidateName, setCandidateName] = useState('');
  const [generating, setGenerating] = useState(false);
  const [generatedLink, setGeneratedLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const jobSelectId = useId();

  function loadData() {
    setLoading(true);
    Promise.all([api.listSessions(), api.listJobs()])
      .then(([s, j]) => { setSessions(s); setJobs(j); setLoading(false); })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : '加载失败');
        setLoading(false);
      });
  }

  useEffect(() => { loadData(); }, []);

  async function handleGenerate() {
    if (!selectedJobId || !candidateName.trim()) return;
    setGenerating(true);
    try {
      const res = await api.createSession(Number(selectedJobId), candidateName.trim());
      const link = `${window.location.origin}/interview?token=${res.token}`;
      setGeneratedLink(link);
      loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '生成失败');
    } finally {
      setGenerating(false);
    }
  }

  async function handleCopy() {
    if (!generatedLink) return;
    try {
      await navigator.clipboard.writeText(generatedLink);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard not available in some envs
    }
  }

  const inputStyle: React.CSSProperties = {
    background: '#0E1525',
    border: '1px solid #243049',
    borderRadius: 14,
    padding: '10px 16px',
    color: '#E8EEF9',
    fontSize: 14,
    width: '100%',
    outline: 'none',
    boxSizing: 'border-box',
  };

  return (
    <AdminShell active="候选人">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-text">候选人</h1>
          <p className="text-sm text-muted mt-1">管理候选人及面试邀请链接</p>
        </div>
        <Button onClick={() => { setShowLinkForm((v) => !v); setGeneratedLink(null); }}>
          + 生成面试链接
        </Button>
      </div>

      {error && <p className="text-red text-sm mb-4">错误：{error}</p>}

      {showLinkForm && (
        <Card className="mb-6">
          <h2 className="text-sm font-semibold text-text mb-4">生成面试邀请链接</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <label htmlFor={jobSelectId} className="text-sm font-medium text-muted">选择职位</label>
              <select
                id={jobSelectId}
                value={selectedJobId}
                onChange={(e) => setSelectedJobId(e.target.value)}
                style={inputStyle}
              >
                <option value="">— 请选择职位 —</option>
                {jobs.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}
              </select>
            </div>
            <Field
              label="候选人姓名"
              value={candidateName}
              onChange={(e) => setCandidateName(e.target.value)}
              placeholder="请输入候选人姓名"
            />
          </div>
          <div className="mt-4 flex gap-3">
            <Button
              onClick={() => void handleGenerate()}
              disabled={generating || !selectedJobId || !candidateName.trim()}
            >
              {generating ? '生成中…' : '生成链接'}
            </Button>
            <Button variant="ghost" onClick={() => { setShowLinkForm(false); setGeneratedLink(null); }}>
              取消
            </Button>
          </div>

          {generatedLink && (
            <div className="mt-4 p-4 rounded-xl" style={{ background: '#0E1525', border: '1px solid #243049' }}>
              <p className="text-xs text-muted mb-2">面试链接（发送给候选人）：</p>
              <div className="flex items-center gap-3 flex-wrap">
                <span className="text-sm text-cyan break-all flex-1">{generatedLink}</span>
                <Button variant="ghost" onClick={() => void handleCopy()}>
                  {copied ? '已复制 ✓' : '复制链接'}
                </Button>
              </div>
            </div>
          )}
        </Card>
      )}

      {loading && <p className="text-muted text-sm">加载中…</p>}

      {!loading && sessions.length === 0 && (
        <Card>
          <p className="text-muted text-sm text-center py-8">暂无候选人记录。</p>
        </Card>
      )}

      {!loading && sessions.length > 0 && (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left text-xs text-muted font-medium py-3 pr-4">候选人</th>
                  <th className="text-left text-xs text-muted font-medium py-3 pr-4">职位</th>
                  <th className="text-left text-xs text-muted font-medium py-3 pr-4">状态</th>
                  <th className="text-left text-xs text-muted font-medium py-3">诚信</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((s) => (
                  <tr key={s.token} className="border-b border-border/50 last:border-0">
                    <td className="py-3 pr-4 text-text font-medium">{s.candidate_name}</td>
                    <td className="py-3 pr-4 text-muted">{s.job_title}</td>
                    <td className="py-3 pr-4">
                      <Pill color={statusColor(s.status)}>{statusLabel(s.status)}</Pill>
                    </td>
                    <td className="py-3">
                      {s.integrity_level ? (
                        <Pill color={INTEGRITY_COLOR[s.integrity_level]}>
                          {INTEGRITY_LABEL[s.integrity_level]}
                        </Pill>
                      ) : (
                        <span className="text-muted text-xs">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </AdminShell>
  );
}
