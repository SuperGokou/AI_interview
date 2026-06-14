import { useEffect, useRef, useState } from 'react';
import Avatar3D from '../../components/Avatar3D';
import { useInterviewSession } from '../../hooks/useInterviewSession';
import type { IntegrityLevel } from '../../types';

// ── Timer ─────────────────────────────────────────────────────────────────────
function useTimer(initialSeconds = 30 * 60) {
  const [seconds, setSeconds] = useState(initialSeconds);

  useEffect(() => {
    const id = setInterval(
      () => setSeconds((s) => (s > 0 ? s - 1 : 0)),
      1000
    );
    return () => clearInterval(id);
  }, []);

  const mm = String(Math.floor(seconds / 60)).padStart(2, '0');
  const ss = String(seconds % 60).padStart(2, '0');
  return `${mm}:${ss}`;
}

// ── Responsive avatar size ────────────────────────────────────────────────────
function useAvatarSize() {
  const getSize = () =>
    typeof window !== 'undefined' && window.innerWidth < 768 ? 300 : 440;
  const [size, setSize] = useState(getSize);

  useEffect(() => {
    function handleResize() {
      setSize(getSize());
    }
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return size;
}

// ── Integrity dot ─────────────────────────────────────────────────────────────
const INTEGRITY_COLOR: Record<IntegrityLevel, string> = {
  green: 'bg-emerald-400',
  yellow: 'bg-amber-400',
  red: 'bg-red-500',
};

// ── Token from URL query string ───────────────────────────────────────────────
function useUrlToken(): string | null {
  if (typeof window === 'undefined') return null;
  return new URLSearchParams(window.location.search).get('token');
}

// ── Demo-session fetch ────────────────────────────────────────────────────────
async function fetchDemoToken(): Promise<string> {
  const res = await fetch('/api/dev/demo-session', { method: 'POST' });
  if (!res.ok) throw new Error(`demo-session failed: ${res.status}`);
  const body = (await res.json()) as { token: string };
  return body.token;
}

// ── Main component ────────────────────────────────────────────────────────────
export default function InterviewRoom() {
  const timer = useTimer();
  const avatarSize = useAvatarSize();
  const urlToken = useUrlToken();

  const session = useInterviewSession();
  const [startError, setStartError] = useState('');
  const startingRef = useRef(false);

  const handleStart = async () => {
    if (startingRef.current || session.active) return;
    startingRef.current = true;
    setStartError('');

    // 1) Acquire media FIRST while still in the user-gesture microtask,
    //    before any network fetch that could break the permission grant.
    let stream: MediaStream;
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new DOMException('insecure context or unsupported browser', 'NotSupportedError');
      }
      stream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: { echoCancellation: true, noiseSuppression: true },
      });
    } catch (e) {
      const name = e instanceof DOMException ? e.name : 'Error';
      setStartError(
        `无法开启摄像头/麦克风 [${name}]。请用 http://localhost 打开、允许浏览器权限,并检查 Windows 隐私设置。`
      );
      startingRef.current = false;
      return;
    }

    // 2) Get a token (URL param takes priority; else create a demo session).
    let token = urlToken;
    if (!token) {
      try {
        token = await fetchDemoToken();
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setStartError(`创建演示会话失败,请确认后端已启动: ${msg}`);
        stream.getTracks().forEach((t) => t.stop());
        startingRef.current = false;
        return;
      }
    }

    // 3) Start the session reusing the already-acquired stream.
    try {
      await session.start(token, stream);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setStartError(msg);
    } finally {
      startingRef.current = false;
    }
  };

  const displayError = session.error || startError;

  // Welcome text before the AI speaks
  const welcomeLine = '你好！我是菜鸟庆，你的 AI 面试官。欢迎参加面试，先做个简单的自我介绍吧？';
  const interviewerLine = session.interviewerText || (session.active ? '' : welcomeLine);

  const integrityDot = INTEGRITY_COLOR[session.integrity];

  return (
    <div
      className="relative min-h-screen w-full overflow-hidden font-sans"
      style={{
        background:
          'radial-gradient(120% 120% at 50% 0%, #d9d8fb 0%, #c3c4f6 55%, #b3b4f2 100%)',
      }}
    >
      {/* Visually-hidden accessible heading keeps test assertion and SEO */}
      <h1 className="sr-only">菜鸟庆面试</h1>

      {/* ── Logo (top-left) ── */}
      <div className="absolute top-6 left-7 z-10 flex items-center gap-1.5">
        <span className="text-[20px] font-bold text-[#1c1d2b] tracking-tight leading-none">
          菜鸟庆
        </span>
        <span
          className="w-2 h-2 rounded-full bg-cyan-500 mt-0.5 shrink-0"
          aria-hidden="true"
        />
      </div>

      {/* ── Timer pill + integrity dot (top-right) ── */}
      <div className="absolute top-6 right-7 z-10 flex items-center gap-2">
        {/* Integrity dot — subtle, only shown during active session */}
        {session.active && (
          <span
            title={`诚信状态: ${session.integrity}`}
            className={`w-2.5 h-2.5 rounded-full shrink-0 transition-colors duration-500 ${integrityDot}`}
            aria-label={`诚信指数 ${session.integrity}`}
          />
        )}
        <div className="flex items-center gap-1.5 bg-white rounded-full px-3.5 py-2 text-sm font-medium text-[#2a2b3c] shadow">
          {/* Clock icon */}
          <svg
            width="14"
            height="14"
            viewBox="0 0 14 14"
            fill="none"
            aria-hidden="true"
            className="shrink-0"
          >
            <circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.5" />
            <path
              d="M7 4v3.5l2 1.5"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span className="font-mono">{timer}</span>
        </div>
      </div>

      {/* ── 3D Avatar — centered and dominant ── */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <Avatar3D size={avatarSize} speaking={session.speaking} />
      </div>

      {/* ── AI message bubble (desktop: right side; mobile: bottom center above PiP) ── */}
      {interviewerLine && (
        <>
          <div
            className={[
              'z-10 bg-white/85 backdrop-blur rounded-2xl px-5 py-4 shadow-lg',
              'text-[15px] leading-relaxed text-[#23243a] font-medium',
              'hidden md:block absolute right-8 top-1/2 -translate-y-1/2 w-[300px]',
            ].join(' ')}
          >
            {interviewerLine}
          </div>
          {/* Mobile bubble — above PiP area */}
          <div
            className={[
              'md:hidden z-10 bg-white/85 backdrop-blur rounded-2xl px-5 py-4 shadow-lg',
              'text-[14px] leading-relaxed text-[#23243a] font-medium',
              'absolute bottom-[180px] left-4 right-4',
            ].join(' ')}
          >
            {interviewerLine}
          </div>
        </>
      )}

      {/* ── Candidate transcript (small, bottom-right area, desktop only) ── */}
      {session.candidateText && (
        <div className="hidden md:block absolute bottom-8 right-8 z-10 max-w-[260px] text-right">
          <span className="inline-block bg-white/70 backdrop-blur rounded-xl px-4 py-2.5 text-[13px] text-[#3a3b50] font-medium shadow">
            {session.candidateText}
          </span>
        </div>
      )}

      {/* ── Candidate video PiP (bottom-left) ── */}
      <div
        className={[
          'absolute bottom-6 left-6 z-10',
          'rounded-2xl overflow-hidden border-4 border-white shadow-2xl',
          'w-[200px] h-[136px] md:w-[340px] md:h-[230px]',
        ].join(' ')}
        aria-label="候选人自视角"
      >
        {/* Placeholder gradient shown when camera is not yet active */}
        {!session.active && (
          <div
            className="absolute inset-0 bg-gradient-to-br from-[#9aa3b2] to-[#6f7a8c]"
            aria-hidden="true"
          />
        )}

        {/* Real webcam feed */}
        <video
          ref={session.videoRef}
          autoPlay
          playsInline
          muted
          className="w-full h-full object-cover"
        />

        {/* ── TOP-RIGHT: pulsing REC indicator (reflects active state) ── */}
        <div className="absolute top-2.5 right-2.5 flex items-center gap-1.5 bg-black/45 rounded-full px-2.5 py-1">
          <span className="relative flex h-2.5 w-2.5 shrink-0">
            {session.active ? (
              <>
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#ff3b4e] opacity-75" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-[#ff3b4e]" />
              </>
            ) : (
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-white/40" />
            )}
          </span>
          <span className="text-white text-[11px] font-semibold tracking-wide leading-none">
            REC
          </span>
        </div>

        {/* ── BOTTOM-LEFT: "You" label with mic icon ── */}
        <div className="absolute bottom-2 left-2 flex items-center gap-1.5 bg-black/55 text-white rounded-lg px-2.5 py-1 text-xs font-medium">
          <svg
            width="11"
            height="11"
            viewBox="0 0 11 11"
            fill="none"
            aria-hidden="true"
          >
            <rect x="3.5" y="0.5" width="4" height="6" rx="2" fill="white" />
            <path
              d="M1.5 5.5c0 2.2 1.79 4 4 4s4-1.8 4-4"
              stroke="white"
              strokeWidth="1.2"
              strokeLinecap="round"
            />
            <line
              x1="5.5"
              y1="9.5"
              x2="5.5"
              y2="10.5"
              stroke="white"
              strokeWidth="1.2"
              strokeLinecap="round"
            />
          </svg>
          You
        </div>
      </div>

      {/* ── "开始面试" button — only shown when session is not active ── */}
      {!session.active && (
        <button
          type="button"
          onClick={() => void handleStart()}
          className={[
            'absolute bottom-6 right-8 z-10',
            'px-5 py-2.5 rounded-full',
            'bg-[#4b4fe0] hover:bg-[#3a3ecf] active:scale-95',
            'transition-all text-white text-sm font-semibold shadow-lg',
          ].join(' ')}
        >
          开始面试
        </button>
      )}

      {/* ── Error toast ── */}
      {displayError && (
        <div
          role="alert"
          className={[
            'absolute bottom-20 left-1/2 -translate-x-1/2 z-20',
            'bg-red-600/90 backdrop-blur text-white',
            'rounded-xl px-5 py-3 text-sm font-medium shadow-lg',
            'max-w-[320px] text-center',
          ].join(' ')}
        >
          {displayError}
        </div>
      )}
    </div>
  );
}
