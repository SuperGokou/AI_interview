import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react';
import StreamingAvatar, {
  AvatarQuality,
  StreamingEvents,
  TaskType,
} from '@heygen/streaming-avatar';

export interface HeyGenHandle {
  speak: (text: string) => void;
}

interface HeyGenAvatarProps {
  className?: string;
  onReady?: () => void;
}

interface TokenResponse {
  token: string;
  avatar_id: string;
}

type ConnectionState = 'loading' | 'connected' | 'error';

const HeyGenAvatar = forwardRef<HeyGenHandle, HeyGenAvatarProps>(
  function HeyGenAvatar({ className, onReady }, ref) {
    const videoRef = useRef<HTMLVideoElement>(null);
    const avatarRef = useRef<StreamingAvatar | null>(null);
    const [state, setState] = useState<ConnectionState>('loading');
    const mountedRef = useRef(true);

    useImperativeHandle(ref, () => ({
      speak(text: string) {
        if (!avatarRef.current || state !== 'connected') return;
        avatarRef.current
          .speak({ text, taskType: TaskType.REPEAT })
          .catch(() => {
            // silently ignore speak errors (e.g. session expired)
          });
      },
    }));

    useEffect(() => {
      mountedRef.current = true;
      let avatar: StreamingAvatar | null = null;

      async function init() {
        try {
          const res = await fetch('/api/heygen/token', { method: 'POST' });
          if (!res.ok) {
            throw new Error(`Token fetch failed: ${res.status}`);
          }
          const data = (await res.json()) as TokenResponse;

          if (!mountedRef.current) return;

          avatar = new StreamingAvatar({ token: data.token });
          avatarRef.current = avatar;

          avatar.on(StreamingEvents.STREAM_READY, (event: unknown) => {
            if (!mountedRef.current) return;
            // The event payload carries the MediaStream
            const mediaStream =
              (event as { detail?: MediaStream })?.detail ??
              avatar?.mediaStream ??
              null;
            if (videoRef.current && mediaStream) {
              videoRef.current.srcObject = mediaStream;
            }
            setState('connected');
            onReady?.();
          });

          avatar.on(StreamingEvents.STREAM_DISCONNECTED, () => {
            if (!mountedRef.current) return;
            setState('error');
          });

          await avatar.createStartAvatar({
            quality: AvatarQuality.Low,
            avatarName: data.avatar_id,
            language: 'zh',
          });
        } catch {
          if (!mountedRef.current) return;
          setState('error');
        }
      }

      void init();

      return () => {
        mountedRef.current = false;
        if (avatar) {
          avatar.stopAvatar().catch(() => {});
          avatarRef.current = null;
        }
      };
      // onReady is intentionally excluded to avoid re-running on every render
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    if (state === 'error') {
      return (
        <div
          className={[
            'flex flex-col items-center justify-center rounded-2xl',
            'bg-white/10 border border-white/20 text-center p-6',
            'min-w-[200px] min-h-[200px]',
            className ?? '',
          ].join(' ')}
          aria-label="数字人未连接"
        >
          <div className="text-4xl mb-3">🤖</div>
          <p className="text-sm text-black/50 leading-snug">
            数字人未连接
            <br />
            请配置 HEYGEN_API_KEY
          </p>
        </div>
      );
    }

    return (
      <div className={['relative', className ?? ''].join(' ')}>
        {state === 'loading' && (
          <div className="absolute inset-0 flex items-center justify-center rounded-2xl bg-black/10 backdrop-blur-sm z-10">
            <div className="flex flex-col items-center gap-2">
              <div className="w-8 h-8 rounded-full border-2 border-indigo-400 border-t-transparent animate-spin" />
              <span className="text-xs text-black/50">连接中…</span>
            </div>
          </div>
        )}
        <video
          ref={videoRef}
          autoPlay
          playsInline
          className="w-full h-full object-cover rounded-2xl"
          style={{ display: state === 'connected' ? 'block' : 'none' }}
        />
        {state === 'loading' && (
          <div className="w-full h-full min-h-[200px] min-w-[200px] rounded-2xl bg-white/10" />
        )}
      </div>
    );
  }
);

export default HeyGenAvatar;
