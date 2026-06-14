import { useEffect, useRef } from 'react';

export type OrbStatus = 'idle' | 'asking' | 'listening' | 'alert';
export type Integrity = 'green' | 'yellow' | 'red';

export interface PlasmaOrbProps {
  size?: number;
  status?: OrbStatus;
  integrity?: Integrity;
  className?: string;
}

// Helper: random float in [a, b)
function rnd(a: number, b: number): number {
  return a + Math.random() * (b - a);
}

// Color palettes per integrity
const PALETTES: Record<Integrity, [string, string, string]> = {
  green:  ['90,210,255',  '46,140,230',  '25,200,200'],
  yellow: ['250,204,21',  '245,158,11',  '230,180,40'],
  red:    ['251,80,112',  '230,60,90',   '255,120,120'],
};

// Core pulse color (visible center)
const CORE_COLOR: Record<Integrity, string> = {
  green:  '120,240,255',
  yellow: '255,220,80',
  red:    '255,100,130',
};

// Arc + spawn config per status
const STATUS_CONFIG: Record<OrbStatus, { spawnRate: number; maxArcs: number; speedMul: number }> = {
  idle:      { spawnRate: 0.02, maxArcs: 1, speedMul: 0.6 },
  listening: { spawnRate: 0.05, maxArcs: 2, speedMul: 0.7 },
  asking:    { spawnRate: 0.16, maxArcs: 6, speedMul: 1.0 },
  alert:     { spawnRate: 0.30, maxArcs: 8, speedMul: 1.5 },
};

interface FogBlob {
  ox: number; oy: number;   // origin offset from center (–0.5..0.5 of S)
  r: number;                // radius as fraction of S
  alpha: number;
  phaseX: number; phaseY: number;
  freqX: number;  freqY: number;
  colorIdx: number;
}

interface Particle {
  x: number; y: number;
  vx: number; vy: number;
  alpha: number;
  r: number;
  colorIdx: number;
}

interface Arc {
  angle: number;
  dist: number;
  life: number;
  maxLife: number;
  // pre-computed jagged midpoints (relative to center, as fractions of S/2)
  mids: Array<{ dx: number; dy: number }>;
  colorIdx: number;
}

export default function PlasmaOrb({
  size = 240,
  status = 'asking',
  integrity = 'green',
  className = '',
}: PlasmaOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return; // jsdom / headless — do nothing, no crash

    // devicePixelRatio backing, capped at 2
    const dpr = Math.min(window.devicePixelRatio ?? 1, 2);
    const S = size;
    canvas.width  = S * dpr;
    canvas.height = S * dpr;
    canvas.style.width  = `${S}px`;
    canvas.style.height = `${S}px`;
    ctx.scale(dpr, dpr);

    // Reduced-motion: single static frame, no loop
    const prefersReduced =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

    const palette = PALETTES[integrity];
    const coreColor = CORE_COLOR[integrity];
    const cfg = STATUS_CONFIG[status];
    const cx = S / 2;
    const cy = S / 2;

    // ── Seed fog blobs ──────────────────────────────────────────────
    const fogBlobs: FogBlob[] = Array.from({ length: 5 }, (_, i) => ({
      ox: rnd(-0.35, 0.35),
      oy: rnd(-0.35, 0.35),
      r: rnd(0.28, 0.42),
      alpha: rnd(0.08, 0.15),
      phaseX: rnd(0, Math.PI * 2),
      phaseY: rnd(0, Math.PI * 2),
      freqX: rnd(0.25, 0.55),
      freqY: rnd(0.25, 0.55),
      colorIdx: i % 3,
    }));

    // ── Seed particles ──────────────────────────────────────────────
    const particles: Particle[] = Array.from({ length: 50 }, () => ({
      x: rnd(0, S),
      y: rnd(0, S),
      vx: rnd(-0.18, 0.18),
      vy: rnd(-0.18, 0.18),
      alpha: rnd(0.04, 0.12),
      r: rnd(0.8, 2.2),
      colorIdx: Math.floor(rnd(0, 3)),
    }));

    const arcs: Arc[] = [];
    let frame = 0;
    let rafId = 0;

    // ── Helper: draw filter-guarded block ──────────────────────────
    const withFilter = (blur: string, fn: () => void) => {
      const supportsFilter = typeof (ctx as CanvasRenderingContext2D).filter !== 'undefined';
      if (supportsFilter) (ctx as CanvasRenderingContext2D).filter = blur;
      fn();
      if (supportsFilter) (ctx as CanvasRenderingContext2D).filter = 'none';
    };

    // ── Draw one frame ─────────────────────────────────────────────
    const drawFrame = (t: number) => {
      const time = t * cfg.speedMul;

      // 1. Trailing fade — destination-out preserves transparency (no opaque square)
      ctx.globalCompositeOperation = 'destination-out';
      ctx.fillStyle = 'rgba(0,0,0,0.16)';
      ctx.fillRect(0, 0, S, S);
      ctx.globalCompositeOperation = 'lighter';

      // 2. Fog blobs
      withFilter('blur(20px)', () => {
        for (const b of fogBlobs) {
          const bx = cx + (b.ox + 0.12 * Math.sin(time * b.freqX + b.phaseX)) * S;
          const by = cy + (b.oy + 0.12 * Math.cos(time * b.freqY + b.phaseY)) * S;
          const r = b.r * S;
          const grad = ctx.createRadialGradient(bx, by, 0, bx, by, r);
          grad.addColorStop(0, `rgba(${palette[b.colorIdx]},${b.alpha})`);
          grad.addColorStop(1, `rgba(${palette[b.colorIdx]},0)`);
          ctx.fillStyle = grad;
          ctx.beginPath();
          ctx.arc(bx, by, r, 0, Math.PI * 2);
          ctx.fill();
        }
      });

      // 3. Outer glow
      const outerR = S * 0.48;
      const outerGrad = ctx.createRadialGradient(cx, cy, outerR * 0.5, cx, cy, outerR);
      outerGrad.addColorStop(0, `rgba(${palette[0]},0.06)`);
      outerGrad.addColorStop(1, `rgba(${palette[0]},0)`);
      ctx.fillStyle = outerGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, outerR, 0, Math.PI * 2);
      ctx.fill();

      // 4. Electric arcs
      // Spawn
      if (arcs.length < cfg.maxArcs && Math.random() < cfg.spawnRate) {
        const life = Math.round(rnd(20, 40));
        const dist = rnd(0.25, 0.46) * S;
        const angle = rnd(0, Math.PI * 2);
        const midCount = Math.floor(rnd(2, 5));
        const mids = Array.from({ length: midCount }, (_, mi) => {
          const frac = (mi + 1) / (midCount + 1);
          const baseDx = Math.cos(angle) * dist * frac;
          const baseDy = Math.sin(angle) * dist * frac;
          const perp = rnd(-0.06, 0.06) * S;
          const perpX = -Math.sin(angle) * perp;
          const perpY =  Math.cos(angle) * perp;
          return { dx: baseDx + perpX, dy: baseDy + perpY };
        });
        arcs.push({ angle, dist, life, maxLife: life, mids, colorIdx: Math.floor(rnd(0, 3)) });
      }

      // Draw + age arcs
      const expiredIdxs: number[] = [];
      for (let i = 0; i < arcs.length; i++) {
        const arc = arcs[i];
        const progress = arc.life / arc.maxLife;
        const fade = Math.sin(progress * Math.PI); // 0→1→0
        const alpha = fade * 0.22;
        if (alpha < 0.005) { expiredIdxs.push(i); continue; }

        const endX = cx + Math.cos(arc.angle) * arc.dist;
        const endY = cy + Math.sin(arc.angle) * arc.dist;

        withFilter('blur(1.2px)', () => {
          ctx.beginPath();
          ctx.moveTo(cx, cy);
          for (const mid of arc.mids) {
            ctx.lineTo(cx + mid.dx, cy + mid.dy);
          }
          ctx.lineTo(endX, endY);
          ctx.strokeStyle = `rgba(${palette[arc.colorIdx]},${alpha})`;
          ctx.lineWidth = 1;
          ctx.shadowBlur = 12;
          ctx.shadowColor = `rgba(${palette[arc.colorIdx]},${alpha * 0.5})`;
          ctx.stroke();
          ctx.shadowBlur = 0;
        });

        arc.life--;
        if (arc.life <= 0) expiredIdxs.push(i);
      }
      // Remove expired (reverse to keep indices valid)
      for (let i = expiredIdxs.length - 1; i >= 0; i--) {
        arcs.splice(expiredIdxs[i], 1);
      }

      // 5. Particles
      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;
        // Wrap around
        if (p.x < 0) p.x += S;
        if (p.x > S) p.x -= S;
        if (p.y < 0) p.y += S;
        if (p.y > S) p.y -= S;

        // Only draw if inside orb circle
        const dx = p.x - cx;
        const dy = p.y - cy;
        if (dx * dx + dy * dy > (S * 0.47) ** 2) continue;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${palette[p.colorIdx]},${p.alpha})`;
        ctx.fill();
      }

      // 6. Core pulse
      const pulseFreq = status === 'listening' ? 0.4 : (status === 'alert' ? 1.8 : 1.0);
      const pulseAmt = 0.12 * Math.sin(time * pulseFreq * Math.PI * 2) + 0.88;
      const coreR = S * 0.18 * pulseAmt;

      withFilter('blur(2px)', () => {
        const coreGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR);
        coreGrad.addColorStop(0, `rgba(240,252,255,0.90)`);
        coreGrad.addColorStop(0.3, `rgba(${coreColor},0.65)`);
        coreGrad.addColorStop(1, `rgba(${coreColor},0)`);
        ctx.fillStyle = coreGrad;
        ctx.beginPath();
        ctx.arc(cx, cy, coreR, 0, Math.PI * 2);
        ctx.fill();
      });

      // Faint star spikes
      const spikeCount = 4;
      const spikeLen = S * 0.10 * pulseAmt;
      for (let s = 0; s < spikeCount; s++) {
        const sAngle = (s / spikeCount) * Math.PI * 2 + time * 0.3;
        const sx = cx + Math.cos(sAngle) * spikeLen;
        const sy = cy + Math.sin(sAngle) * spikeLen;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(sx, sy);
        ctx.strokeStyle = `rgba(${coreColor},0.15)`;
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    };

    if (prefersReduced) {
      // Static single frame at t=0
      drawFrame(0);
      return;
    }

    // Animation loop
    let startTime: number | null = null;
    const loop = (timestamp: number) => {
      if (startTime === null) startTime = timestamp;
      const t = (timestamp - startTime) / 1000; // seconds
      frame++;
      drawFrame(t);
      rafId = requestAnimationFrame(loop);
    };

    rafId = requestAnimationFrame(loop);

    // Cleanup: cancel the rAF — no leaked loops on unmount / prop change
    return () => {
      cancelAnimationFrame(rafId);
    };
  }, [size, status, integrity]);

  return (
    <canvas
      ref={canvasRef}
      role="img"
      aria-label="AI 面试官能量光球"
      className={className}
      style={{
        display: 'block',
        width: size,
        height: size,
        WebkitMaskImage: 'radial-gradient(circle at 50% 50%, #000 55%, transparent 73%)',
        maskImage: 'radial-gradient(circle at 50% 50%, #000 55%, transparent 73%)',
      }}
    />
  );
}
