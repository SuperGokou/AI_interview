import { useEffect, useRef, useState } from 'react';
import Avatar3D from '../../components/Avatar3D';

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

export default function InterviewRoom() {
  const timer = useTimer();
  const [speaking, setSpeaking] = useState(false);
  const speakTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const avatarSize = useAvatarSize();

  function handleTestSpeak() {
    setSpeaking(true);
    if (speakTimerRef.current) clearTimeout(speakTimerRef.current);
    speakTimerRef.current = setTimeout(() => setSpeaking(false), 4000);
  }

  useEffect(() => {
    return () => {
      if (speakTimerRef.current) clearTimeout(speakTimerRef.current);
    };
  }, []);

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

      {/* ── Timer pill (top-right) ── */}
      <div className="absolute top-6 right-7 z-10 flex items-center gap-1.5 bg-white rounded-full px-3.5 py-2 text-sm font-medium text-[#2a2b3c] shadow">
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

      {/* ── 3D Avatar — centered and dominant ── */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <Avatar3D size={avatarSize} speaking={speaking} />
      </div>

      {/* ── AI message bubble (desktop: right side; mobile: bottom center above PiP) ── */}
      <div
        className={[
          'z-10 bg-white/85 backdrop-blur rounded-2xl px-5 py-4 shadow-lg',
          'text-[15px] leading-relaxed text-[#23243a] font-medium',
          // Desktop: absolute right, vertically centered
          'hidden md:block absolute right-8 top-1/2 -translate-y-1/2 w-[300px]',
        ].join(' ')}
      >
        你好！我是菜鸟庆，你的 AI 面试官。欢迎参加面试，先做个简单的自我介绍吧？
      </div>
      {/* Mobile bubble — above PiP area */}
      <div
        className={[
          'md:hidden z-10 bg-white/85 backdrop-blur rounded-2xl px-5 py-4 shadow-lg',
          'text-[14px] leading-relaxed text-[#23243a] font-medium',
          'absolute bottom-[180px] left-4 right-4',
        ].join(' ')}
      >
        你好！我是菜鸟庆，你的 AI 面试官。欢迎参加面试，先做个简单的自我介绍吧？
      </div>

      {/* ── Candidate video PiP (bottom-left) ── */}
      <div
        className={[
          'absolute bottom-6 left-6 z-10',
          'rounded-2xl overflow-hidden border-4 border-white shadow-2xl',
          // Bigger: desktop 340×230, mobile 200×136
          'w-[200px] h-[136px] md:w-[340px] md:h-[230px]',
        ].join(' ')}
        aria-label="候选人自视角"
      >
        {/* Placeholder gradient (real webcam later) */}
        <div
          className="absolute inset-0 bg-gradient-to-br from-[#9aa3b2] to-[#6f7a8c]"
          aria-hidden="true"
        />

        {/* ── TOP-RIGHT: pulsing REC indicator ── */}
        <div className="absolute top-2.5 right-2.5 flex items-center gap-1.5 bg-black/45 rounded-full px-2.5 py-1">
          {/* Ping ring (classic live-REC look) */}
          <span className="relative flex h-2.5 w-2.5 shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#ff3b4e] opacity-75" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-[#ff3b4e]" />
          </span>
          <span className="text-white text-[11px] font-semibold tracking-wide leading-none">
            REC
          </span>
        </div>

        {/* ── BOTTOM-LEFT: "You" label with mic icon ── */}
        <div className="absolute bottom-2 left-2 flex items-center gap-1.5 bg-black/55 text-white rounded-lg px-2.5 py-1 text-xs font-medium">
          {/* Mic icon */}
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

      {/* ── "测试说话" button (bottom-right, unobtrusive) ── */}
      <button
        type="button"
        onClick={handleTestSpeak}
        className="absolute bottom-6 right-8 z-10 px-4 py-2 rounded-full bg-white/80 hover:bg-white active:scale-95 transition-all text-[#2a2b3c] text-sm font-medium shadow border border-white/60 backdrop-blur"
      >
        测试说话
      </button>
    </div>
  );
}
