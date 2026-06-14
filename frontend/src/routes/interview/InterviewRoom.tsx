import { useEffect, useRef, useState } from 'react';
import HeyGenAvatar, { type HeyGenHandle } from '../../components/HeyGenAvatar';

const GREETING = '你好,我是菜鸟庆,很高兴见到你。请先做个自我介绍吧。';

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

export default function InterviewRoom() {
  const avatarRef = useRef<HeyGenHandle>(null);
  const timer = useTimer();

  function handleTestSpeak() {
    avatarRef.current?.speak(GREETING);
  }

  return (
    <div
      className="relative min-h-screen w-full overflow-hidden"
      style={{
        background:
          'radial-gradient(120% 120% at 50% 0%, #d9d8fb 0%, #c3c4f6 55%, #b3b4f2 100%)',
      }}
    >
      {/* Visually-hidden accessible heading keeps test assertion and SEO */}
      <h1 className="sr-only">菜鸟庆面试</h1>

      {/* ── Top bar ── */}
      <header className="absolute top-0 left-0 right-0 flex items-center justify-between px-6 pt-5 pb-2 z-20">
        {/* Logo */}
        <div className="flex items-center gap-1.5">
          <span className="text-lg font-bold text-indigo-900 tracking-tight">
            菜鸟庆
          </span>
          <span
            className="w-2 h-2 rounded-full bg-indigo-500 mt-0.5"
            aria-hidden="true"
          />
        </div>

        {/* Timer pill */}
        <div className="flex items-center gap-1.5 bg-white/80 backdrop-blur-sm rounded-full px-4 py-1.5 shadow-sm text-sm font-mono font-semibold text-indigo-900">
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
          {timer}
        </div>
      </header>

      {/* ── Main content ── */}
      <main className="flex flex-col md:flex-row items-center justify-center min-h-screen gap-6 px-6 pt-20 pb-10">
        {/* Left: presenter + test button */}
        <div className="flex flex-col items-center gap-4 flex-1 max-w-lg">
          <HeyGenAvatar
            ref={avatarRef}
            className="w-72 h-72 md:w-96 md:h-96 shadow-2xl"
          />

          <button
            onClick={handleTestSpeak}
            className="mt-2 px-5 py-2 rounded-full bg-indigo-600 hover:bg-indigo-700 active:scale-95 transition-all text-white text-sm font-medium shadow-md"
            type="button"
          >
            测试说话
          </button>
        </div>

        {/* Right: chat bubble + recording pill + PiP */}
        <div className="flex flex-col gap-4 items-start w-full md:w-auto md:max-w-xs">
          {/* Question bubble */}
          <div className="bg-white/85 backdrop-blur-sm rounded-2xl rounded-tl-sm px-5 py-4 shadow-md">
            <p className="text-sm leading-relaxed text-indigo-950">
              你好！我是菜鸟庆，你的 AI 面试官。欢迎参加面试，先做个简单的自我介绍吧？
            </p>
          </div>

          {/* Recording pill */}
          <div className="flex items-center gap-2 bg-white/80 backdrop-blur-sm rounded-full px-4 py-1.5 shadow-sm self-start">
            <span
              className="w-2 h-2 rounded-full bg-red-500 animate-pulse"
              aria-hidden="true"
            />
            <span className="text-xs font-semibold text-red-600 tracking-wide uppercase">
              Recording
            </span>
          </div>

          {/* Candidate self-view PiP */}
          <div
            className="relative rounded-2xl overflow-hidden shadow-lg"
            style={{ width: 190, height: 120 }}
            aria-label="候选人自视角"
          >
            {/* Placeholder gradient for camera preview */}
            <div
              className="absolute inset-0"
              style={{
                background:
                  'linear-gradient(135deg, #e0e7ff 0%, #c7d2fe 50%, #a5b4fc 100%)',
              }}
            />
            {/* "You" pill */}
            <div className="absolute bottom-2 left-2 flex items-center gap-1.5 bg-black/60 backdrop-blur-sm rounded-full px-2.5 py-1">
              <svg
                width="10"
                height="10"
                viewBox="0 0 10 10"
                fill="none"
                aria-hidden="true"
              >
                <ellipse cx="5" cy="3.5" rx="2" ry="2" fill="white" />
                <path
                  d="M1 9c0-2.2 1.8-4 4-4s4 1.8 4 4"
                  stroke="white"
                  strokeWidth="1.2"
                  strokeLinecap="round"
                />
              </svg>
              <span className="text-white text-[10px] font-semibold">You</span>
              {/* Mic glyph */}
              <svg
                width="9"
                height="9"
                viewBox="0 0 9 9"
                fill="none"
                aria-hidden="true"
                className="ml-0.5"
              >
                <rect
                  x="3"
                  y="0.5"
                  width="3"
                  height="5"
                  rx="1.5"
                  fill="white"
                />
                <path
                  d="M1.5 4.5c0 1.65 1.35 3 3 3s3-1.35 3-3"
                  stroke="white"
                  strokeWidth="1"
                  strokeLinecap="round"
                />
                <line
                  x1="4.5"
                  y1="7.5"
                  x2="4.5"
                  y2="8.5"
                  stroke="white"
                  strokeWidth="1"
                  strokeLinecap="round"
                />
              </svg>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
