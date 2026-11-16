import { useEffect, useRef, useState, type MutableRefObject } from 'react';
import LightweightInterviewer from './LightweightInterviewer';

const WIDTH = 1672, HEIGHT = 942;

/** Matched listening/talking frames share one decoder and clock. Approximate lip sync. */
export default function NeuralInterviewer({ mouthOpeningRef }: { mouthOpeningRef?: MutableRefObject<number> }) {
  const video = useRef<HTMLVideoElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const media = video.current, surface = canvas.current;
    if (!media || !surface || failed) return;
    const ctx = surface.getContext('2d', { alpha: false });
    if (!ctx) { setFailed(true); return; }
    let disposed = false, frame = 0, previous = 0, pending = false;
    let opacity = 0, quietMs = 500, paintedTime = -1, paintedOpacity = -1;
    const fail = () => { if (!disposed) setFailed(true); };
    const tick = (now: number) => {
      if (disposed) return;
      const dt = previous ? Math.min(100, Math.max(0, now - previous)) : 16;
      previous = now;
      const level = mouthOpeningRef?.current ?? 0;
      const audible = Number.isFinite(level) && level > .015;
      quietMs = audible ? 0 : quietMs + dt;
      // Bridge short phoneme gaps; close promptly after the actual audio stops.
      opacity = audible ? Math.min(1, opacity + dt / 100)
        : quietMs <= 100 ? opacity : Math.max(0, opacity - dt / 140);
      if (!document.hidden && media.readyState >= 2) {
        if (media.videoWidth !== WIDTH * 2 || media.videoHeight !== HEIGHT) { fail(); return; }
        if (media.paused && !pending) {
          pending = true;
          void media.play().catch(fail).finally(() => { pending = false; });
        }
        if (paintedTime !== media.currentTime || paintedOpacity !== opacity) {
          try {
            ctx.globalAlpha = 1;
            ctx.drawImage(media, 0, 0, WIDTH, HEIGHT, 0, 0, WIDTH, HEIGHT);
            if (opacity > 0) {
              ctx.globalAlpha = opacity;
              ctx.drawImage(media, WIDTH, 0, WIDTH, HEIGHT, 0, 0, WIDTH, HEIGHT);
            }
            ctx.globalAlpha = 1;
            surface.style.opacity = '1';
            paintedTime = media.currentTime; paintedOpacity = opacity;
          } catch { fail(); return; }
        }
      }
      frame = requestAnimationFrame(tick);
    };
    const onVisibility = () => {
      previous = 0;
      if (document.hidden) media.pause();
    };
    document.addEventListener('visibilitychange', onVisibility);
    frame = requestAnimationFrame(tick);
    return () => {
      disposed = true; cancelAnimationFrame(frame); media.pause();
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [mouthOpeningRef, failed]);
  if (failed) return <LightweightInterviewer mouthOpeningRef={mouthOpeningRef} />;
  return <div className="absolute inset-0 overflow-hidden" aria-label="坤耀面试官">
    <img src="/zoom-interviewer-listening.png" alt="坤耀 AI 面试官" className="absolute inset-0 h-full w-full object-cover object-top" draggable={false} />
    <canvas ref={canvas} width={WIDTH} height={HEIGHT} aria-hidden="true" className="absolute inset-0 h-full w-full object-cover object-top" style={{ opacity: 0 }} />
    <video ref={video} src="/interviewer-continuous-v1.mp4" muted autoPlay playsInline loop preload="auto" aria-hidden="true" style={{position:'absolute',width:1,height:1,opacity:0,pointerEvents:'none'}} onError={() => setFailed(true)} />
  </div>;
}
