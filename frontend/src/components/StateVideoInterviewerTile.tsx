import { useEffect, useMemo, useRef, useState, type MutableRefObject } from 'react';
import MouthOverlay, { type MouthFrame } from './MouthOverlay';
import NeuralInterviewer from './NeuralInterviewer';
import type {
  AvatarState,
  AvatarStateCommand,
} from '../lib/avatarStateController';
import type { MouthConfig } from '../lib/mouthTimeline';


const STATE_LABELS: Record<AvatarState, string> = {
  idle: '\u81ea\u7136\u5f85\u673a',
  greeting: '\u6b22\u8fce\u5019\u9009\u4eba',
  listening: '\u8ba4\u771f\u503e\u542c\u4e2d',
  speaking: '\u6570\u5b57\u4eba\u8bb2\u8bdd\u4e2d',
  thinking: '\u6b63\u5728\u601d\u8003\u8ffd\u95ee',
};

interface StateVideoInterviewerTileProps {
  command: AvatarStateCommand;
  mouthOpeningRef?: MutableRefObject<number>;
  /** Realtime lip-sync frames from the server; omitted when the service is not in use. */
  mouthConfig?: MouthConfig | null;
  mouthFrameRef?: MutableRefObject<MouthFrame | null>;
  active?: boolean;
  className?: string;
  onSpeakingChange?: (speaking: boolean) => void;
}

/** Keep the original interviewer and animate her mouth from output audio.
 * Optional generated clips remain supported for a later GPU renderer. */
export default function StateVideoInterviewerTile({
  command,
  mouthOpeningRef,
  mouthConfig = null,
  mouthFrameRef,
  active = false,
  className,
  onSpeakingChange,
}: StateVideoInterviewerTileProps) {
  const generatedVideoUrl =
    command.state === 'speaking' && command.videoUrl ? command.videoUrl : '';
  const [videoReady, setVideoReady] = useState(false);
  const speechVideoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    setVideoReady(false);
  }, [generatedVideoUrl]);

  useEffect(() => {
    const video = speechVideoRef.current;
    if (!generatedVideoUrl || !video) return;

    video.muted = false;
    video.volume = 1;
    const playPromise = video.play();
    if (playPromise !== undefined) {
      void playPromise.catch(() => {
        // Keep the waiting loop visible if Chrome blocks unmuted playback.
        setVideoReady(false);
      });
    }
  }, [generatedVideoUrl]);

  useEffect(() => {
    onSpeakingChange?.(Boolean(generatedVideoUrl));
  }, [generatedVideoUrl, onSpeakingChange]);

  const status = STATE_LABELS[command.state] ?? STATE_LABELS.idle;

  const dotClass = useMemo(() => {
    if (generatedVideoUrl || command.state === 'speaking') return 'bg-emerald-400';
    if (command.state === 'thinking') return 'bg-amber-300';
    if (command.state === 'listening') return 'bg-sky-400';
    if (active) return 'bg-cyan-300';
    return 'bg-slate-300';
  }, [active, command.state, generatedVideoUrl]);

  return (
    <section
      className={[
        'relative overflow-hidden rounded-lg bg-[#101827] shadow-2xl',
        'ring-1 ring-white/10',
        className ?? '',
      ].join(' ')}
      aria-label={'AI \u9762\u8bd5\u5b98\u52a8\u6001\u89c6\u9891\u753b\u9762'}
    >
      <NeuralInterviewer mouthOpeningRef={mouthOpeningRef} />
      {mouthFrameRef && <MouthOverlay config={mouthConfig} frameRef={mouthFrameRef} />}

      {generatedVideoUrl && (
        <video
          key={generatedVideoUrl}
          ref={speechVideoRef}
          src={generatedVideoUrl}
          autoPlay
          playsInline
          preload="auto"
          className={[
            'absolute inset-0 h-full w-full select-none object-cover object-top',
            'transition-opacity duration-300 ease-out',
            videoReady ? 'opacity-100' : 'opacity-0',
          ].join(' ')}
          aria-label={'AI \u9762\u8bd5\u5b98\u53e3\u578b\u89c6\u9891'}
          onCanPlay={() => {
            const video = speechVideoRef.current;
            if (!video) return;
            video.muted = false;
            video.volume = 1;
            void video.play().catch(() => setVideoReady(false));
          }}
          onLoadedData={() => {
            const video = speechVideoRef.current;
            if (!video) return;
            video.muted = false;
            video.volume = 1;
            void video.play().catch(() => setVideoReady(false));
          }}
          onPlaying={() => setVideoReady(true)}
          onEnded={() => {
            setVideoReady(false);
            onSpeakingChange?.(false);
          }}
        />
      )}

      <div className="absolute inset-0 bg-gradient-to-b from-slate-950/10 via-transparent to-slate-950/24" />

      <div className="absolute inset-x-0 top-0 flex items-center justify-between bg-gradient-to-b from-black/55 to-transparent px-4 py-3">
        <div className="flex items-center gap-2 rounded bg-black/35 px-2.5 py-1 text-xs font-medium text-white backdrop-blur">
          <span
            className={['h-2 w-2 rounded-full', dotClass].join(' ')}
            aria-hidden="true"
          />
          {status}
        </div>
        <div className="rounded bg-black/35 px-2.5 py-1 text-xs font-medium text-white/90 backdrop-blur">
          {'坤曜 AI \u9762\u8bd5\u5b98'}
        </div>
      </div>
    </section>
  );
}
