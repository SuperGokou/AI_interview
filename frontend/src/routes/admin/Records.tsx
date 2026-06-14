import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AdminShell, Card, Pill } from '../../ui';
import { api } from '../../lib/api';
import type { SessionListItem, IntegrityLevel } from '../../types';

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

export default function Records() {
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listSessions()
      .then((data) => { setSessions(data); setLoading(false); })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : '加载失败');
        setLoading(false);
      });
  }, []);

  return (
    <AdminShell active="面试记录">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-text">面试记录</h1>
        <p className="text-sm text-muted mt-1">查看所有候选人的面试记录与报告</p>
      </div>

      {error && <p className="text-red text-sm mb-4">错误：{error}</p>}
      {loading && <p className="text-muted text-sm">加载中…</p>}

      {!loading && sessions.length === 0 && (
        <Card>
          <p className="text-muted text-sm text-center py-8">暂无面试记录。</p>
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
                  <th className="text-left text-xs text-muted font-medium py-3 pr-4">诚信</th>
                  <th className="text-left text-xs text-muted font-medium py-3 pr-4">评分</th>
                  <th className="text-left text-xs text-muted font-medium py-3">操作</th>
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
                    <td className="py-3 pr-4">
                      {s.integrity_level ? (
                        <Pill color={INTEGRITY_COLOR[s.integrity_level]}>
                          {INTEGRITY_LABEL[s.integrity_level]}
                        </Pill>
                      ) : (
                        <span className="text-muted text-xs">—</span>
                      )}
                    </td>
                    <td className="py-3 pr-4 text-muted">
                      {s.score_overall !== null ? `${s.score_overall}分` : '—'}
                    </td>
                    <td className="py-3">
                      <Link
                        to={`/admin/reports/${s.token}`}
                        className="text-cyan text-xs hover:underline"
                      >
                        查看报告
                      </Link>
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
