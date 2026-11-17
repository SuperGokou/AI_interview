import { useEffect, useRef, type MutableRefObject } from 'react';
import type { MouthConfig } from '../lib/mouthTimeline';

/** A decoded mouth frame; `serial` changes whenever the picture to show changes. */
export interface MouthFrame {
  image: CanvasImageSource;
  serial: number;
}

interface MouthOverlayProps {
  config: MouthConfig | null;
  frameRef: MutableRefObject<MouthFrame | null>;
  /** Called when rendered frames start or stop being shown. */
  onActiveChange?: (active: boolean) => void;
}

/** Cross-fade between the idle picture underneath and the rendered head. */
const FADE_MS = 220;

/** Pixels over which the patch fades into the picture underneath. The base layer is
 *  a video and the patch is a JPEG of the portrait, so their tones can differ slightly;
 *  a soft edge keeps the patch rectangle from ever showing. */
const EDGE_FEATHER = 8;

function buildEdgeMask(width: number, height: number): HTMLCanvasElement | null {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (!ctx || typeof ctx.createImageData !== 'function') return null;
  const pixels = ctx.createImageData(width, height);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const edge = Math.min(x, y, width - 1 - x, height - 1 - y);
      pixels.data[(y * width + x) * 4 + 3] = Math.round(255 * Math.min(1, edge / EDGE_FEATHER));
    }
  }
  ctx.putImageData(pixels, 0, 0);
  return canvas;
}

/**
 * Paints server-rendered mouth frames over the interviewer portrait.
 *
 * The canvas has the portrait's pixel size and the same object-fit rules as the
 * picture beneath it, so patch coordinates from the server line up without any
 * layout maths. When there is no frame it is fully transparent.
 */
export default function MouthOverlay({ config, frameRef, onActiveChange }: MouthOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const onActiveChangeRef = useRef(onActiveChange);
  onActiveChangeRef.current = onActiveChange;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !config) return;
    const ctx = canvas.getContext('2d');
    const { x, y, width, height } = config.patch;
    const mask = buildEdgeMask(width, height);
    const scratch = document.createElement('canvas');
    scratch.width = width;
    scratch.height = height;
    const scratchCtx = scratch.getContext('2d');
    if (!ctx || !mask || !scratchCtx) return; // no 2D canvas: keep the audio-driven mouth

    let raf = 0;
    let painted = -1;
    let active = false;
    const paint = () => {
      const frame = frameRef.current;
      const serial = frame?.serial ?? 0;
      if (frame && serial !== painted) {
        painted = serial;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        scratchCtx.globalCompositeOperation = 'copy';
        scratchCtx.drawImage(frame.image, 0, 0, width, height);
        scratchCtx.globalCompositeOperation = 'destination-in';
        scratchCtx.drawImage(mask, 0, 0);
        ctx.drawImage(scratch, x, y);
      }
      // When frames stop, the last one stays drawn and fades out over the idle
      // picture instead of vanishing in a single step.
      if ((frame !== null) !== active) {
        active = frame !== null;
        canvas.style.opacity = active ? '1' : '0';
        onActiveChangeRef.current?.(active);
      }
      raf = requestAnimationFrame(paint);
    };
    raf = requestAnimationFrame(paint);
    return () => {
      cancelAnimationFrame(raf);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    };
  }, [config, frameRef]);

  if (!config) return null;
  return (
    <canvas
      ref={canvasRef}
      width={config.frame.width}
      height={config.frame.height}
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 h-full w-full object-cover object-top"
      style={{ opacity: 0, transition: `opacity ${FADE_MS}ms ease-out` }}
    />
  );
}
