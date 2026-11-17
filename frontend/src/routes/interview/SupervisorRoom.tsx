import { useEffect, useMemo, useState } from 'react';
import ZoomInterviewerTile from '../../components/ZoomInterviewerTile';
import { api } from '../../lib/api';
import type { SupervisorSessionInfo, SupervisorTranscriptFeed, Transcript } from '../../types';

function useUrlToken(): string | null {
  if (typeof window === 'undefined') return null;
  return new URLSearchParams(window.location.search).get('token');
}

function isLiveStatus(status?: string): boolean {
  return status === 'active' || status === 'in_progress' || status === 'done' || status === 'completed';
}

function statusLabel(status?: string): string {
  if (status === 'pending') return '等待开始';
  if (status === 'active' || status === 'in_progress') return '面试进行中';
  if (status === 'done' || status === 'completed') return '面试已结束';
  return status || '未知状态';
}

interface VideoPanelProps {
  title: string;
  subtitle: string;
  initials: string;
  tone?: 'cyan' | 'green' | 'violet';
  current?: boolean;
}

function VideoPanel({ title, subtitle, initials, tone = 'cyan', current = false }: VideoPanelProps) {
  const toneClass = {
    cyan: 'border-cyan-300/40 bg-cyan-300/10 text-cyan-100',
    green: 'border-emerald-300/40 bg-emerald-300/10 text-emerald-100',
    violet: 'border-violet-300/40 bg-violet-300/10 text-violet-100',
  }[tone];

  return (
    <section className="relative min-h-[150px] overflow-hidden rounded-lg bg-[#101827] ring-1 ring-white/10">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(125,211,252,0.16),transparent_58%),linear-gradient(135deg,#162033,#0a0f1c)]" />
      <div className="relative flex h-full flex-col items-center justify-center gap-2 px-4 text-center">
        <div className={`flex h-12 w-12 items-center justify-center rounded-full border text-sm font-semibold ${toneClass}`}>
          {initials}
        </div>
        <div className="text-sm font-semibold text-white/90">{title}</div>
        <div className="text-xs text-white/50">{subtitle}</div>
        {current && (
          <div className="absolute right-2 top-2 rounded-full bg-white/10 px-2 py-0.5 text-[11px] font-medium text-white/65">
            当前
          </div>
        )}
      </div>
    </section>
  );
}

function TranscriptRow({ item }: { item: Transcript }) {
  const isCandidate = item.role === 'candidate';
  return (
    <div className={`flex ${isCandidate ? 'justify-end' : 'justify-start'}`}>
      <div
        className={[
          'max-w-[86%] rounded-lg px-3 py-2 text-sm leading-relaxed',
          isCandidate
            ? 'bg-emerald-400/10 text-emerald-50 ring-1 ring-emerald-300/20'
            : 'bg-cyan-400/10 text-cyan-50 ring-1 ring-cyan-300/20',
        ].join(' ')}
      >
        <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-white/42">
          {isCandidate ? '候选人' : 'AI 面试官'}
        </div>
        <div>{item.text}</div>
      </div>
    </div>
  );
}

export default function SupervisorRoom() {
  const token = useUrlToken();
  const [info, setInfo] = useState<SupervisorSessionInfo | null>(null);
  const [feed, setFeed] = useState<SupervisorTranscriptFeed | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      setError('缺少监督链接 token');
      return;
    }

    const supervisorToken = token;
    let disposed = false;

    async function load() {
      try {
        const [sessionInfo, transcriptFeed] = await Promise.all([
          api.getSupervisorSession(supervisorToken),
          api.listSupervisorTranscripts(supervisorToken),
        ]);
        if (disposed) return;
        setInfo(sessionInfo);
        setFeed(transcriptFeed);
        setError(null);
      } catch (err) {
        if (disposed) return;
        setError(err instanceof Error ? err.message : '加载监督视角失败');
      } finally {
        if (!disposed) setLoading(false);
      }
    }

    void load();
    const id = window.setInterval(() => void load(), 2500);
    return () => {
      disposed = true;
      window.clearInterval(id);
    };
  }, [token]);

  const live = isLiveStatus(feed?.status || info?.status);
  const supervisors = useMemo(() => info?.supervisors ?? [], [info?.supervisors]);

  return (
    <div className="min-h-screen min-h-[100svh] bg-[#0b0f18] font-sans text-white">
      <header className="flex h-16 items-center justify-between border-b border-white/10 bg-[#111827] px-4 md:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <img
            src="/kunyao-logo.svg"
            alt=""
            className="h-9 w-9 shrink-0 object-contain drop-shadow-[0_0_14px_rgba(126,221,255,0.32)]"
            aria-hidden="true"
          />
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">坤曜监督端</div>
            <div className="truncate text-xs text-white/50">
              {info ? `${info.candidate_name} · ${info.job.title}` : '加载中'}
            </div>
          </div>
        </div>
        <div className="rounded-full border border-white/10 bg-white/8 px-3 py-1.5 text-xs font-semibold text-white/75">
          {statusLabel(feed?.status || info?.status)}
        </div>
      </header>

      <main className="grid min-h-[calc(100svh-4rem)] grid-cols-1 gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <section className="grid min-h-[520px] grid-rows-[minmax(320px,1fr)_auto] gap-4">
          <ZoomInterviewerTile active={live} speaking={false} className="min-h-[320px]" />

          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <VideoPanel
              title={info?.candidate_name || '候选人'}
              subtitle={live ? '候选人视频窗口' : '等待候选人开始'}
              initials="C"
              tone="green"
            />
            {supervisors.slice(0, 2).map((peer, index) => (
              <VideoPanel
                key={`${peer.label}-${index}`}
                title={peer.label}
                subtitle={peer.is_current ? '你的监督视角' : '部门监督人员'}
                initials={`S${index + 1}`}
                tone={index % 2 === 0 ? 'cyan' : 'violet'}
                current={peer.is_current}
              />
            ))}
            {supervisors.length === 0 && (
              <VideoPanel title="监督员" subtitle="等待接入" initials="S" tone="cyan" current />
            )}
          </div>
        </section>

        <aside className="flex min-h-[520px] flex-col rounded-lg bg-[#111827] ring-1 ring-white/10">
          <div className="border-b border-white/10 px-4 py-3">
            <div className="text-sm font-semibold text-white/90">实时记录</div>
            <div className="mt-1 text-xs text-white/45">
              {feed?.live ? '已同步面试转写' : '候选人点击开始面试后显示'}
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {loading && <div className="text-sm text-white/55">加载中...</div>}
            {error && <div className="rounded-lg bg-red-500/12 p-3 text-sm text-red-100">{error}</div>}
            {!loading && !error && !feed?.live && (
              <div className="flex h-full items-center justify-center text-center text-sm text-white/45">
                等待面试开始
              </div>
            )}
            {!loading && !error && feed?.live && feed.transcripts.length === 0 && (
              <div className="flex h-full items-center justify-center text-center text-sm text-white/45">
                暂无转写内容
              </div>
            )}
            {!loading && !error && feed?.live && feed.transcripts.length > 0 && (
              <div className="space-y-3">
                {feed.transcripts.map((item, index) => (
                  <TranscriptRow key={`${item.ts ?? 'tx'}-${index}`} item={item} />
                ))}
              </div>
            )}
          </div>
        </aside>
      </main>
    </div>
  );
}
