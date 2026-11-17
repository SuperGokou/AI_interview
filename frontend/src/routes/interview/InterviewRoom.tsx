import { useEffect, useRef, useState } from 'react';
import StateVideoInterviewerTile from '../../components/StateVideoInterviewerTile';
import { useInterviewSession } from '../../hooks/useInterviewSession';
import { useAvatarStateController } from '../../lib/avatarStateController';
import type { IntegrityLevel } from '../../types';
import { api } from '../../lib/api';
import { useWelcomePresence } from '../../hooks/useWelcomePresence';

const LANDING_VIDEOS = {
  welcome: '/kunyao-welcome-transparent-v1.webm',
  ending: '/kunyao-ending-transparent-v1.webm',
} as const;
const OPENING_AVATAR_WIDTH = 720;
const OPENING_AVATAR_HEIGHT = 1280;
const OPENING_AVATAR_ASPECT = OPENING_AVATAR_WIDTH / OPENING_AVATAR_HEIGHT;
const OPENING_AVATAR_ASPECT_CSS = `${OPENING_AVATAR_WIDTH} / ${OPENING_AVATAR_HEIGHT}`;
const LANDING_BACKGROUND_COLOR = '#ddd8f5';
const LANDING_BACKGROUND = [
  `linear-gradient(180deg, ${LANDING_BACKGROUND_COLOR} 0%, ${LANDING_BACKGROUND_COLOR} 100%)`,
].join(', ');
type LandingVideoKind = keyof typeof LANDING_VIDEOS;

/**
 * Formats and runs the interview countdown timer.
 *
 * Args:
 *   running: Whether the countdown should actively decrement.
 *   initialSeconds: Seconds to display before the interview starts.
 *
 * Returns:
 *   The `MM:SS` label for the timer pill and whether a running countdown hit zero.
 */
function useTimer(running: boolean, initialSeconds = 30 * 60) {
  const [seconds, setSeconds] = useState(initialSeconds);

  useEffect(() => {
    setSeconds(initialSeconds);
    if (!running) return;

    const id = setInterval(
      () => setSeconds((s) => (s > 0 ? s - 1 : 0)),
      1000
    );
    return () => clearInterval(id);
  }, [initialSeconds, running]);

  const mm = String(Math.floor(seconds / 60)).padStart(2, '0');
  const ss = String(seconds % 60).padStart(2, '0');
  return { label: `${mm}:${ss}`, expired: running && seconds === 0 };
}

/**
 * Computes a responsive opening avatar width from the active viewport.
 *
 * The generated avatar is tall and can easily collide with controls on short
 * screens, so the calculation is bounded by both viewport height and width.
 *
 * Returns:
 *   A pixel width that keeps the full-body avatar visible across breakpoints.
 */
function useAvatarSize() {
  const getSize = () => {
    if (typeof window === 'undefined') return 440;

    const byHeight =
      window.innerHeight *
      (window.innerWidth < 768 ? 0.56 : 0.9) *
      OPENING_AVATAR_ASPECT;
    const byWidth =
      window.innerWidth * (window.innerWidth < 768 ? 0.72 : 0.37);
    const max = window.innerWidth < 768 ? 275 : 480;
    const min = window.innerWidth < 768 ? 220 : 340;

    return Math.round(
      Math.min(max, Math.max(min, Math.min(byHeight, byWidth)))
    );
  };
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

const INTEGRITY_COLOR: Record<IntegrityLevel, string> = {
  green: 'bg-emerald-400',
  yellow: 'bg-amber-400',
  red: 'bg-red-500',
};

function DisabledSlash() {
  return (
    <svg
      className="pointer-events-none absolute inset-0 z-20 h-full w-full"
      viewBox="0 0 40 40"
      fill="none"
      aria-hidden="true"
    >
      <line
        x1="12"
        y1="29"
        x2="28"
        y2="11"
        stroke="rgba(8,12,22,0.72)"
        strokeWidth="6"
        strokeLinecap="round"
      />
      <line
        x1="12"
        y1="29"
        x2="28"
        y2="11"
        stroke="#ff2d45"
        strokeWidth="3.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

/**
 * Reads an optional interview token from the route query string.
 *
 * Returns:
 *   The token value when present, otherwise `null`.
 */
function useUrlToken(): string | null {
  if (typeof window === 'undefined') return null;
  return new URLSearchParams(window.location.search).get('token')?.trim() || null;
}

/**
 * Creates a local demo interview session for development and smoke testing.
 *
 * Returns:
 *   A backend-issued session token.
 *
 * Throws:
 *   Error: When the backend refuses to create the demo session.
 */
async function fetchDemoToken(): Promise<string> {
  const res = await fetch('/api/dev/demo-session', { method: 'POST' });
  if (!res.ok) throw new Error(`demo-session failed: ${res.status}`);
  const body = (await res.json()) as { token: string };
  return body.token;
}

/**
 * Plays the landing-page video with its original embedded audio.
 *
 * Keeping the narration inside the landing video avoids the drift that
 * happens when video and TTS are triggered separately. If the browser blocks
 * unmuted autoplay, the first non-start-button pointer gesture retries playback
 * with audio.
 *
 * Args:
 *   kind: Which landing clip to play.
 *   playKey: Incrementing key used to replay the same clip after state changes.
 *   width: CSS width assigned by the responsive avatar sizing hook.
 *   onEnded: Optional callback fired when the clip reaches the end.
 *
 * Returns:
 *   A native video player constrained to the source video's aspect ratio.
 */
function LandingVideo({
  kind,
  playKey,
  width,
  onEnded,
  playing = true,
}: {
  kind: LandingVideoKind;
  playKey: number;
  width: number;
  onEnded?: () => void;
  playing?: boolean;
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const audioBlockedRef = useRef(false);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    let disposed = false;
    const resetToStart = () => {
      try {
        video.currentTime = 0;
      } catch {
        // Some browsers reject seeking before metadata is available.
      }
    };

    const playWithSound = async () => {
      if (disposed) return;
      video.muted = false;
      video.volume = 1;
      video.playbackRate = 1;
      try {
        await video.play();
        audioBlockedRef.current = false;
      } catch {
        audioBlockedRef.current = true;
      }
    };

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      if (target?.closest('[data-start-interview="true"]')) return;
      if (playing && audioBlockedRef.current) {
        void playWithSound();
      }
    };

    const handleLoadedMetadata = () => {
      resetToStart();
    };

    const handleEnded = () => {
      onEnded?.();
    };

    audioBlockedRef.current = false;
    resetToStart();
    if (playing) void playWithSound();
    else video.pause();

    video.addEventListener('loadedmetadata', handleLoadedMetadata);
    video.addEventListener('ended', handleEnded);
    window.addEventListener('pointerdown', handlePointerDown, true);

    return () => {
      disposed = true;
      video.pause();
      video.removeEventListener('loadedmetadata', handleLoadedMetadata);
      video.removeEventListener('ended', handleEnded);
      window.removeEventListener('pointerdown', handlePointerDown, true);
    };
  }, [kind, onEnded, playKey, playing]);

  return (
    <div
      className="relative pointer-events-auto overflow-hidden"
      style={{
        width,
        maxWidth: '90vw',
        aspectRatio: OPENING_AVATAR_ASPECT_CSS,
        backgroundColor: LANDING_BACKGROUND_COLOR,
      }}
    >
      <video
        key={`${kind}-${playKey}`}
        ref={videoRef}
        src={LANDING_VIDEOS[kind]}
        autoPlay={playing}
        controls={false}
        loop={false}
        playsInline
        preload="auto"
        aria-label={kind === 'ending' ? 'AI 面试官结束语视频' : 'AI 面试官欢迎视频'}
        className="absolute inset-0 h-full w-full select-none object-contain"
        style={{
          filter: 'none',
        }}
      />

    </div>
  );
}

/**
 * Hosts the candidate-facing interview room and welcome experience.
 *
 * The component coordinates the landing videos and the real interview
 * websocket session. Welcome and ending narration stay embedded in their videos
 * so mouth movement, timing, and audio cannot drift apart.
 *
 * Returns:
 *   The welcome screen or active interview room UI.
 */
export default function InterviewRoom() {
  const avatarSize = useAvatarSize();
  const urlToken = useUrlToken();
  const { command: avatarCommand, setAvatarState } =
    useAvatarStateController('idle');
  const session = useInterviewSession({
    playAudio: true,
    onInterviewerFinalText: () => undefined,
    onInterviewerAudioStart: () => {
      setAvatarState('speaking');
    },
    onInterviewerAudioEnd: () => {
      setAvatarState('listening');
    },
    onUserTranscript: () => {
      setAvatarState('thinking');
    },
    onAvatarStateCommand: (command) => {
      setAvatarState(command.state, {
        text: command.text,
        intent: command.intent,
        tone: command.tone,
        audioUrl: command.audioUrl,
        videoUrl: command.videoUrl,
      });
    },
  });
  const [durationSeconds, setDurationSeconds] = useState(30 * 60);
  const { label: timer, expired: timeExpired } = useTimer(session.active, durationSeconds);
  const [startError, setStartError] = useState('');
  const [showOpeningLine, setShowOpeningLine] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [landingVideo, setLandingVideo] =
    useState<LandingVideoKind>('welcome');
  const [landingPlayKey, setLandingPlayKey] = useState(0);
  const [interviewEnded, setInterviewEnded] = useState(false);
  const [avatarSpeaking, setAvatarSpeaking] = useState(false);
  const startingRef = useRef(false);
  const interviewEndedRef = useRef(false);
  const showInterviewAvatar = session.active || isStarting || showOpeningLine;
  const welcome = useWelcomePresence(!showInterviewAvatar && !interviewEnded);

  /**
   * Starts the live interview after acquiring camera and microphone permissions.
   *
   * The media request remains inside the click path so Chromium can associate it
   * with the user's gesture and avoid unnecessary permission failures.
   */
  const requiresInvite = !urlToken && !import.meta.env.DEV;
  const handleStart = async () => {
    if (requiresInvite) return;
    if (interviewEndedRef.current || interviewEnded || startingRef.current || session.active) return;
    welcome.stop(); // Release the lobby camera before acquiring interview camera + microphone.
    startingRef.current = true;
    setStartError('');
    setShowOpeningLine(false);
    setIsStarting(true);
    setAvatarState('greeting');

    let stream: MediaStream;
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new DOMException(
          'insecure context or unsupported browser',
          'NotSupportedError'
        );
      }
      stream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: { echoCancellation: true, noiseSuppression: true },
      });
    } catch (e) {
      const name = e instanceof DOMException ? e.name : 'Error';
      setStartError(`无法开始面试 [${name}]：请允许摄像头和麦克风，并确认设备可用后重试。`);
      startingRef.current = false;
      setIsStarting(false);
      setAvatarState('idle');
      return;
    }

    setShowOpeningLine(true);

    let token = urlToken;
    if (!token) {
      try {
        token = await fetchDemoToken();
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setStartError(`演示会话暂不可用，请从后台生成专属面试链接后重试。${msg}`);
        stream.getTracks().forEach((t) => t.stop());
        startingRef.current = false;
        setIsStarting(false);
        setShowOpeningLine(false);
        return;
      }
    }
    if (interviewEndedRef.current) {
      stream.getTracks().forEach((t) => t.stop());
      startingRef.current = false;
      setIsStarting(false);
      setShowOpeningLine(false);
      return;
    }
    try {
      const info = await api.getSession(token);
      if (info.status === 'done' || info.status === 'completed') {
        throw new Error('该面试已结束，请联系管理员获取新的面试链接。');
      }
      setDurationSeconds(Math.max(1, info.job.duration_minutes) * 60);
      await api.consent(token);
      setAvatarState('thinking');
      await session.start(token, stream);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setShowOpeningLine(false);
      stream.getTracks().forEach((t) => t.stop());
      setStartError(msg);
    } finally {
      startingRef.current = false;
      setIsStarting(false);
    }
  };

  /**
   * Stops the active interview and clears transient UI state.
   */
  const handleEnd = () => {
    interviewEndedRef.current = true;
    setLandingVideo('ending');
    setLandingPlayKey((value) => value + 1);
    setInterviewEnded(true);
    setAvatarSpeaking(false);
    session.stop();
    setShowOpeningLine(false);
    setIsStarting(false);
    setStartError('');
    setAvatarState('idle');
  };

  // The server enforces the same limit; ending here shows the closing clip
  // instead of an abrupt disconnect.
  const handleEndRef = useRef(handleEnd);
  handleEndRef.current = handleEnd;
  useEffect(() => {
    if (timeExpired) handleEndRef.current();
  }, [timeExpired]);

  const displayError = session.error || startError || (!showInterviewAvatar && !interviewEnded && welcome.error ? welcome.status : '');
  const integrityDot = INTEGRITY_COLOR[session.integrity];
  const startButtonDisabled = isStarting || interviewEnded;

  if (showInterviewAvatar) {
    const statusText = avatarSpeaking
      ? 'AI 面试官正在讲话'
      : session.active
        ? '候选人作答中'
        : '正在连接面试';

    return (
      <div className="relative min-h-screen min-h-[100svh] overflow-hidden bg-[#0b0f18] font-sans text-white">
        <header className="flex h-14 items-center justify-between border-b border-white/10 bg-[#111827] px-4 md:px-6">
          <div className="flex min-w-0 items-center gap-2.5">
            <img
              src="/kunyao-logo.svg"
              alt=""
              className="h-8 w-8 shrink-0 object-contain drop-shadow-[0_0_14px_rgba(126,221,255,0.32)]"
              aria-hidden="true"
            />
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold">坤曜</div>
              <div className="truncate text-[11px] text-white/55">{statusText}</div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden rounded-full border border-red-300 bg-red-600 px-3 py-1 text-xs font-semibold text-white shadow-[0_0_18px_rgba(220,38,38,0.32)] md:block">
              严禁使用 AI 作弊
            </div>
            <div className="rounded-full bg-white/10 px-3 py-1.5 font-mono text-sm">
              {timer}
            </div>
          </div>
        </header>

        <main className="grid h-[calc(100svh-7.5rem)] grid-cols-1 gap-3 p-3 md:h-[calc(100svh-8rem)] md:grid-cols-[1fr_300px] md:gap-4 md:p-4">
          <div className="relative min-h-0">
            <StateVideoInterviewerTile
              command={avatarCommand}
              mouthOpeningRef={session.mouthOpeningRef}
              active={session.active}
              onSpeakingChange={setAvatarSpeaking}
              className="h-full min-h-[360px]"
            />
          </div>

          <aside className="grid min-h-0 grid-cols-2 gap-3 md:grid-cols-1 md:grid-rows-[170px_140px_140px]">
            <section className="relative overflow-hidden rounded-lg bg-[#0f172a] ring-1 ring-white/10">
              {!session.active && (
                <div className="absolute inset-0 bg-gradient-to-br from-slate-700 to-slate-950" />
              )}
              <video
                ref={session.videoRef}
                autoPlay
                playsInline
                muted
                className="relative h-full w-full object-cover"
              />
              {!session.cameraEnabled && (
                <div className="absolute inset-0 flex items-center justify-center bg-slate-950 text-xs font-semibold text-white/75">
                  摄像头已关闭
                </div>
              )}
              <div className="absolute bottom-2 left-2 rounded bg-black/50 px-2 py-1 text-xs font-medium text-white backdrop-blur">
                You
              </div>
              <div className="absolute right-2 top-2 flex items-center gap-1 rounded bg-black/50 px-2 py-1 text-[11px] font-semibold text-white backdrop-blur">
                <span className="h-2 w-2 rounded-full bg-red-400" />
                REC
              </div>
            </section>

            <section className="relative overflow-hidden rounded-lg bg-[#111827] ring-1 ring-white/10">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(45,212,239,0.24),transparent_55%),linear-gradient(135deg,#172033,#0b1020)]" />
              <div className="relative flex h-full flex-col items-center justify-center gap-2 text-center">
                <div className="flex h-11 w-11 items-center justify-center rounded-full border border-cyan-300/40 bg-cyan-300/10 text-sm font-semibold text-cyan-100">
                  S1
                </div>
                <div className="text-xs font-semibold text-white/85">监督员 1</div>
                <div className="text-[11px] text-white/45">等待接入</div>
              </div>
            </section>

            <section className="relative overflow-hidden rounded-lg bg-[#111827] ring-1 ring-white/10">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(167,139,250,0.22),transparent_55%),linear-gradient(135deg,#191b33,#0b1020)]" />
              <div className="relative flex h-full flex-col items-center justify-center gap-2 text-center">
                <div className="flex h-11 w-11 items-center justify-center rounded-full border border-violet-300/40 bg-violet-300/10 text-sm font-semibold text-violet-100">
                  S2
                </div>
                <div className="text-xs font-semibold text-white/85">监督员 2</div>
                <div className="text-[11px] text-white/45">等待接入</div>
              </div>
            </section>
          </aside>
        </main>

        <footer className="flex h-16 items-center justify-center gap-3 border-t border-white/10 bg-[#111827] px-4">
          <button
            type="button"
            onClick={() => session.setMicEnabled(!session.micEnabled)}
            className={[
              'relative flex h-10 w-10 items-center justify-center rounded-full border-2 transition active:scale-95',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-[#111827]',
              session.micEnabled
                ? 'text-white hover:bg-white/16 focus-visible:ring-cyan-300'
                : 'focus-visible:ring-[#ff2d45]',
            ].join(' ')}
            style={{
              color: session.micEnabled ? '#ffffff' : '#ff2d45',
              borderColor: session.micEnabled ? 'rgba(255,255,255,0.14)' : '#ff2d45',
              background: session.micEnabled ? 'rgba(255,255,255,0.10)' : 'rgba(255,45,69,0.18)',
              boxShadow: session.micEnabled ? 'none' : '0 0 20px rgba(255,45,69,0.36)',
            }}
            title={session.micEnabled ? '关闭麦克风' : '打开麦克风'}
            aria-label={session.micEnabled ? '关闭麦克风' : '打开麦克风'}
            aria-pressed={!session.micEnabled}
          >
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
              <rect x="6.2" y="2" width="5.6" height="9" rx="2.8" fill="currentColor" />
              <path d="M3.8 8.8a5.2 5.2 0 0 0 10.4 0M9 14v2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
            {!session.micEnabled && <DisabledSlash />}
          </button>
          <button
            type="button"
            onClick={() => session.setCameraEnabled(!session.cameraEnabled)}
            className={[
              'relative flex h-10 w-10 items-center justify-center rounded-full border-2 transition active:scale-95',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-[#111827]',
              session.cameraEnabled
                ? 'text-white hover:bg-white/16 focus-visible:ring-cyan-300'
                : 'focus-visible:ring-[#ff2d45]',
            ].join(' ')}
            style={{
              color: session.cameraEnabled ? '#ffffff' : '#ff2d45',
              borderColor: session.cameraEnabled ? 'rgba(255,255,255,0.14)' : '#ff2d45',
              background: session.cameraEnabled ? 'rgba(255,255,255,0.10)' : 'rgba(255,45,69,0.18)',
              boxShadow: session.cameraEnabled ? 'none' : '0 0 20px rgba(255,45,69,0.36)',
            }}
            title={session.cameraEnabled ? '关闭摄像头' : '打开摄像头'}
            aria-label={session.cameraEnabled ? '关闭摄像头' : '打开摄像头'}
            aria-pressed={!session.cameraEnabled}
          >
            <svg width="19" height="18" viewBox="0 0 19 18" fill="none" aria-hidden="true">
              <rect x="2" y="5" width="10" height="8" rx="2" fill="currentColor" />
              <path d="m12 7 4-2v8l-4-2V7Z" fill="currentColor" />
            </svg>
            {!session.cameraEnabled && <DisabledSlash />}
          </button>
          <button
            type="button"
            onClick={handleEnd}
            className="rounded-full bg-red-500 px-5 py-2.5 text-sm font-semibold text-white shadow-lg transition hover:bg-red-600 active:scale-95"
          >
            结束面试
          </button>
        </footer>

        {displayError && (
          <div className="absolute bottom-20 left-1/2 z-20 max-w-[420px] -translate-x-1/2 rounded-xl bg-red-600/95 px-5 py-3 text-center text-sm font-medium text-white shadow-lg">
            {displayError}
          </div>
        )}
      </div>
    );
  }

  return (
    <div
      className="relative min-h-screen min-h-[100svh] w-full overflow-hidden font-sans"
      style={{
        background: LANDING_BACKGROUND,
      }}
    >
      <h1 className="sr-only">坤曜</h1>

      <div
        role="alert"
        className={[
          'absolute left-1/2 top-16 z-20 -translate-x-1/2 md:top-6',
          'flex max-w-[92vw] items-center gap-2',
          'rounded-full border border-red-400 bg-red-50/90 px-4 py-2 text-[#e01030] shadow-sm backdrop-blur',
        ].join(' ')}
      >
        <svg
          width="15"
          height="15"
          viewBox="0 0 16 16"
          fill="none"
          aria-hidden="true"
          className="shrink-0"
        >
          <path
            d="M8 1.6 15 14H1L8 1.6Z"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinejoin="round"
          />
          <line
            x1="8"
            y1="6"
            x2="8"
            y2="9.6"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
          />
          <circle cx="8" cy="11.7" r="0.9" fill="currentColor" />
        </svg>
        <span className="text-[12px] font-semibold leading-snug md:text-[13px]">
          严禁使用 AI 作弊 · 平台已启用 AI 诚信评测机制，全程检测，异常将被记录
        </span>
      </div>

      <div className="absolute left-7 top-6 z-10 flex items-center gap-2.5">
        <img
          src="/kunyao-logo.svg"
          alt=""
          className="h-10 w-10 shrink-0 object-contain drop-shadow-[0_8px_18px_rgba(78,94,220,0.26)]"
          aria-hidden="true"
        />
        <span className="text-[20px] font-bold leading-none tracking-[0.04em] text-[#15172a]">
          坤曜
        </span>
      </div>

      <div className="absolute right-7 top-6 z-10 flex items-center gap-2">
        {session.active && (
          <span
            title={`诚信状态：${session.integrity}`}
            className={`h-2.5 w-2.5 shrink-0 rounded-full transition-colors duration-500 ${integrityDot}`}
            aria-label={`诚信指数 ${session.integrity}`}
          />
        )}
        <div className="flex items-center gap-1.5 rounded-full bg-white px-3.5 py-2 text-sm font-medium text-[#2a2b3c] shadow">
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

      <div className="pointer-events-none absolute inset-0 z-0 flex items-center justify-center px-5 pb-40 pt-24 md:px-10 md:pb-28">
        <LandingVideo
          kind={landingVideo}
          playKey={landingVideo === 'welcome' ? welcome.playKey : landingPlayKey}
          playing={landingVideo === 'ending' || welcome.playing}
          onEnded={landingVideo === 'welcome' ? welcome.finished : undefined}
          width={avatarSize}
        />
      </div>

      {requiresInvite && !session.active && (
        <div className="absolute bottom-6 left-1/2 z-20 w-[90%] max-w-md -translate-x-1/2 rounded-2xl bg-white/95 p-5 text-center text-slate-800 shadow-lg">
          <p className="font-semibold">请使用专属面试链接</p>
          <p className="mt-2 text-sm text-slate-600">候选人请打开邀请人发送的完整链接。管理员可进入后台，选择岗位并填写候选人姓名后生成链接。</p>
          <a href="/admin/candidates" className="mt-4 inline-block rounded-full bg-[#4b4fe0] px-5 py-2.5 text-sm font-semibold text-white">前往后台生成面试链接</a>
        </div>
      )}

      {!session.active && !requiresInvite && (
        <button
          type="button"
          data-start-interview="true"
          onClick={() => void handleStart()}
          disabled={startButtonDisabled}
          className={[
            'absolute bottom-6 right-8 z-10',
            'rounded-full px-5 py-2.5',
            'text-sm font-semibold text-white shadow-lg transition-all',
            interviewEnded
              ? 'cursor-not-allowed bg-slate-400 shadow-none'
              : 'bg-[#4b4fe0] hover:bg-[#3a3ecf] active:scale-95 disabled:cursor-wait disabled:bg-[#6b6fe8]',
          ].join(' ')}
        >
          {interviewEnded ? '面试已结束' : isStarting ? '连接中...' : '开始面试'}
        </button>
      )}

      {displayError && (
        <div
          role="alert"
          className={[
            'absolute bottom-20 left-1/2 z-20 -translate-x-1/2',
            'max-w-[360px] rounded-xl bg-red-600/90 px-5 py-3 text-center text-sm font-medium text-white shadow-lg backdrop-blur',
          ].join(' ')}
        >
          {displayError}
          {welcome.error && !showInterviewAvatar && !interviewEnded && <button type="button" onClick={welcome.retry} className="ml-3 underline">重新连接摄像头</button>}
        </div>
      )}
    </div>
  );
}
