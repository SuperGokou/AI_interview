import { useEffect, useState } from 'react';
import { AdminShell, Card, Pill } from '../../ui';
import { api } from '../../lib/api';
import type { DashboardStats, IntegrityLevel, SessionListItem } from '../../types';

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

function integrityColor(lvl: IntegrityLevel | null): string {
  return lvl ? INTEGRITY_COLOR[lvl] : '#8593AD';
}

function integrityLabel(lvl: IntegrityLevel | null): string {
  return lvl ? INTEGRITY_LABEL[lvl] : '未知';
}

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

interface StatCardProps {
  label: string;
  value: number | string;
  accent: string;
}

function StatCard({ label, value, accent }: StatCardProps) {
  return (
    <Card className="flex flex-col gap-2">
      <span className="text-xs text-muted uppercase tracking-wider">{label}</span>
      <span className="text-3xl font-bold" style={{ color: accent }}>
        {value}
      </span>
    </Card>
  );
}

function RecentRow({ s }: { s: SessionListItem }) {
  return (
    <div className="flex items-center gap-3 py-3 border-b border-border last:border-0">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-text truncate">{s.candidate_name}</p>
        <p className="text-xs text-muted truncate">{s.job_title}</p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <Pill color={integrityColor(s.integrity_level)}>
          {integrityLabel(s.integrity_level)}
        </Pill>
        {s.score_overall !== null && (
          <span className="text-xs text-muted">{s.score_overall}分</span>
        )}
        <Pill color={statusColor(s.status)} dot={false}>
          {statusLabel(s.status)}
        </Pill>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.dashboardStats()
      .then((data) => { if (!cancelled) { setStats(data); setLoading(false); } })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '加载失败');
          setLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, []);

  return (
    <AdminShell active="仪表盘">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-text">仪表盘</h1>
        <p className="text-sm text-muted mt-1">菜鸟庆面试 · 运营概览</p>
      </div>

      {loading && (
        <p className="text-muted text-sm">加载中…</p>
      )}
      {error && !loading && (
        <p className="text-red text-sm">数据加载失败：{error}</p>
      )}

      {!loading && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            <StatCard label="进行中职位" value={stats?.active_jobs ?? '—'} accent="#2DD4EF" />
            <StatCard label="待面试" value={stats?.pending_interviews ?? '—'} accent="#FACC15" />
            <StatCard label="已完成面试" value={stats?.completed_interviews ?? '—'} accent="#2BE5A4" />
            <StatCard label="高诚信风险" value={stats?.high_risk ?? '—'} accent="#FB5070" />
          </div>

          <Card>
            <h2 className="text-sm font-semibold text-text mb-4">近期面试</h2>
            {(!stats || stats.recent.length === 0) ? (
              <p className="text-muted text-sm py-4 text-center">暂无近期面试记录</p>
            ) : (
              <div>
                {stats.recent.map((s) => (
                  <RecentRow key={s.token} s={s} />
                ))}
              </div>
            )}
          </Card>
        </>
      )}
    </AdminShell>
  );
}
