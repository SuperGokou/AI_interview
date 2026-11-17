import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../../lib/api';
import { SEVERITY_LABEL, clockTime, eventLabel } from '../../lib/eventLabels';
import type {
  CheatEvent,
  IntegrityLevel,
  RiskLevel,
  SupervisorSessionInfo,
  SupervisorTranscriptFeed,
  Transcript,
} from '../../types';

const FEED_REFRESH_MS = 2500;
const FRAME_REFRESH_MS = 1000;

const INTEGRITY: Record<IntegrityLevel, { label: string; className: string }> = {
  green: { label: '诚信正常', className: 'border-emerald-300/30 bg-emerald-400/10 text-emerald-200' },
  yellow: { label: '需要留意', className: 'border-amber-300/30 bg-amber-400/10 text-amber-200' },
  red: { label: '高风险', className: 'border-red-300/30 bg-red-500/15 text-red-200' },
};

const SEVERITY_DOT: Record<RiskLevel, string> = {
  low: 'bg-sky-300',
  medium: 'bg-amber-300',
  high: 'bg-red-400',
};

function useUrlToken(): string | null {
  if (typeof window === 'undefined') return null;
  return new URLSearchParams(window.location.search).get('token');
}

function isInProgress(status?: string): boolean {
  return status === 'active' || status === 'in_progress';
}

function isOver(status?: string): boolean {
  return status === 'done' || status === 'completed';
}

function statusLabel(status?: string): string {
  if (status === 'pending') return '等待开始';
  if (isInProgress(status)) return '面试进行中';
  if (isOver(status)) return '面试已结束';
  return status || '未知状态';
}

/** Polls the candidate's newest camera frame while the interview is in progress. */
function useLiveFrame(token: string | null, enabled: boolean): string | null {
  const [url, setUrl] = useState<string | null>(null);
  const urlRef = useRef<string | null>(null);

  useEffect(() => {
    const release = () => {
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    };
    if (!token || !enabled) {
      release();
      setUrl(null);
      return;
    }
    let disposed = false;
    let busy = false;

    async function refresh(supervisorToken: string) {
      if (busy) return; // a slow link must not pile requests up
      busy = true;
      try {
        const blob = await api.supervisorFrame(supervisorToken);
        if (disposed) return;
        release();
        urlRef.current = blob ? URL.createObjectURL(blob) : null;
        setUrl(urlRef.current);
      } catch {
        // Keep the last picture; the next tick tries again.
      } finally {
        busy = false;
      }
    }

    void refresh(token);
    const id = window.setInterval(() => void refresh(token), FRAME_REFRESH_MS);
    return () => {
      disposed = true;
      window.clearInterval(id);
      release();
    };
  }, [token, enabled]);

  return url;
}

interface CandidateViewProps {
  name: string;
  status?: string;
  frameUrl: string | null;
}

function CandidateView({ name, status, frameUrl }: CandidateViewProps) {
  const inProgress = isInProgress(status);
  const placeholder = !inProgress
    ? isOver(status)
      ? '面试已结束'
      : '等待候选人开始面试'
    : '暂时没有画面（候选人可能关闭了摄像头）';

  return (
    <section
      aria-label="候选人实时画面"
      className="relative aspect-video w-full overflow-hidden rounded-xl bg-[#0d1422] ring-1 ring-white/10"
    >
      {frameUrl ? (
        <img src={frameUrl} alt={`${name}的实时画面`} className="h-full w-full object-contain" />
      ) : (
        <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-full border border-white/15 bg-white/5 text-xl font-semibold text-white/70">
            {name.slice(0, 1) || '候'}
          </div>
          <div className="text-sm text-white/50">{placeholder}</div>
        </div>
      )}

      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-center justify-between p-3">
        <div className="rounded-md bg-black/55 px-2.5 py-1 text-xs font-medium text-white/90 backdrop-blur">
          {name}
        </div>
        {inProgress && frameUrl && (
          <div className="flex items-center gap-1.5 rounded-md bg-black/55 px-2.5 py-1 text-xs font-semibold text-white/90 backdrop-blur">
            <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" aria-hidden="true" />
            实时
          </div>
        )}
      </div>
      {inProgress && frameUrl && (
        <div className="pointer-events-none absolute bottom-3 left-3 rounded-md bg-black/45 px-2 py-0.5 text-[11px] text-white/55 backdrop-blur">
          画面约每秒更新一次
        </div>
      )}
    </section>
  );
}

function FindingRow({ event }: { event: CheatEvent }) {
  return (
    <li className="flex gap-3 rounded-lg bg-white/[0.04] px-3 py-2.5 ring-1 ring-white/5">
      <span
        className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${SEVERITY_DOT[event.severity] ?? 'bg-white/40'}`}
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <span className="text-sm font-medium text-white/90">{eventLabel(event.kind)}</span>
          <span className="text-[11px] text-white/45">
            {SEVERITY_LABEL[event.severity] ?? event.severity}风险 · {clockTime(event.ts)}
          </span>
        </div>
        {event.evidence && (
          <p className="mt-1 text-xs leading-relaxed text-white/55">{event.evidence}</p>
        )}
      </div>
    </li>
  );
}

function TranscriptRow({ item }: { item: Transcript }) {
  const isCandidate = item.role === 'candidate';
  return (
    <div className={`flex ${isCandidate ? 'justify-end' : 'justify-start'}`}>
      <div
        className={[
          'max-w-[88%] rounded-lg px-3 py-2 text-sm leading-relaxed',
          isCandidate
            ? 'bg-emerald-400/10 text-emerald-50 ring-1 ring-emerald-300/20'
            : 'bg-cyan-400/10 text-cyan-50 ring-1 ring-cyan-300/20',
        ].join(' ')}
      >
        <div className="mb-1 text-[11px] font-semibold tracking-wide text-white/45">
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
    const id = window.setInterval(() => void load(), FEED_REFRESH_MS);
    return () => {
      disposed = true;
      window.clearInterval(id);
    };
  }, [token]);

  const status = feed?.status || info?.status;
  const inProgress = isInProgress(status);
  const frameUrl = useLiveFrame(token, inProgress);
  const transcripts = feed?.transcripts ?? [];
  // Newest finding first: that is the one a supervisor needs to see.
  const findings = useMemo(() => [...(feed?.events ?? [])].reverse(), [feed?.events]);
  const integrity = feed?.integrity_level ? INTEGRITY[feed.integrity_level] : null;
  const me = info?.supervisors.find((peer) => peer.is_current)?.label;
  const others = (info?.supervisors.length ?? 1) - 1;

  // Follow the conversation as new lines arrive. Only the transcript box scrolls:
  // scrollIntoView would drag the whole page down and hide the candidate.
  const transcriptBoxRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const box = transcriptBoxRef.current;
    if (box) box.scrollTop = box.scrollHeight;
  }, [transcripts.length]);

  return (
    <div className="min-h-screen min-h-[100svh] bg-[#0b0f18] font-sans text-white">
      <header className="flex min-h-16 flex-wrap items-center justify-between gap-3 border-b border-white/10 bg-[#111827] px-4 py-3 md:px-6">
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
        <div className="flex flex-wrap items-center gap-2 text-xs font-semibold">
          {me && (
            <span className="rounded-full border border-white/10 px-3 py-1.5 font-medium text-white/55">
              {me}
              {others > 0 ? ` · 另有 ${others} 位监督员` : ''}
            </span>
          )}
          {integrity && (
            <span className={`rounded-full border px-3 py-1.5 ${integrity.className}`}>
              {integrity.label}
            </span>
          )}
          <span className="flex items-center gap-1.5 rounded-full border border-white/10 bg-white/8 px-3 py-1.5 text-white/80">
            {inProgress && (
              <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" aria-hidden="true" />
            )}
            {statusLabel(status)}
          </span>
        </div>
      </header>

      {error && (
        <div className="mx-4 mt-4 rounded-lg bg-red-500/12 p-3 text-sm text-red-100 md:mx-6" role="alert">
          {error}
        </div>
      )}

      <main className="grid grid-cols-1 gap-4 p-4 md:p-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex min-w-0 flex-col gap-4">
          <CandidateView
            name={info?.candidate_name || '候选人'}
            status={status}
            frameUrl={frameUrl}
          />

          <section className="rounded-xl bg-[#111827] ring-1 ring-white/10">
            <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
              <h2 className="text-sm font-semibold text-white/90">监考发现</h2>
              <span className="text-xs text-white/45">{findings.length} 条</span>
            </div>
            <div className="max-h-[320px] overflow-y-auto p-3">
              {findings.length === 0 ? (
                <p className="px-1 py-4 text-center text-sm text-white/45">
                  {inProgress ? '目前没有发现异常' : '没有监考记录'}
                </p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {findings.map((event, index) => (
                    <FindingRow key={`${event.ts ?? 'ev'}-${event.kind}-${index}`} event={event} />
                  ))}
                </ul>
              )}
            </div>
          </section>
        </div>

        <aside className="flex max-h-[calc(100svh-7rem)] min-h-[420px] flex-col rounded-xl bg-[#111827] ring-1 ring-white/10 lg:sticky lg:top-4">
          <div className="border-b border-white/10 px-4 py-3">
            <h2 className="text-sm font-semibold text-white/90">对话记录</h2>
            <div className="mt-1 text-xs text-white/45">
              {feed?.live ? '随面试实时更新' : '候选人开始面试后显示'}
            </div>
          </div>

          <div ref={transcriptBoxRef} className="min-h-0 flex-1 overflow-y-auto p-4">
            {loading && <div className="text-sm text-white/55">加载中...</div>}
            {!loading && !error && !feed?.live && (
              <div className="flex h-full items-center justify-center text-center text-sm text-white/45">
                等待面试开始
              </div>
            )}
            {!loading && !error && feed?.live && transcripts.length === 0 && (
              <div className="flex h-full items-center justify-center text-center text-sm text-white/45">
                暂无对话内容
              </div>
            )}
            {!loading && !error && feed?.live && transcripts.length > 0 && (
              <div className="space-y-3">
                {transcripts.map((item, index) => (
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
