/**
 * Realtime lip-sync bookkeeping for the browser.
 *
 * The server tags every interviewer audio chunk with (utterance, sample position)
 * and sends mouth frames tagged with (utterance, frame index). Frame i of an
 * utterance belongs at audio position i / fps. This module maps that position
 * onto the audio playback clock, so each frame is shown exactly when its sound
 * is heard, no matter how early or late the frame arrived over the network.
 */

export interface PatchRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface MouthConfig {
  fps: number;
  /** How long to hold back the start of each utterance so its first frames can arrive. */
  delaySeconds: number;
  frame: { width: number; height: number };
  patch: PatchRect;
}

export interface MouthFrameHeader {
  utterance: number;
  index: number;
  jpeg: ArrayBuffer;
}

export interface TimedFrame<T> {
  utterance: number;
  index: number;
  /** Playback-clock time at which this frame should appear. */
  time: number;
  image: T;
}

const HEADER_BYTES = 8;
const MAX_DELAY_SECONDS = 2;
const KEPT_UTTERANCES = 3;

function isPositive(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0;
}

function isCoordinate(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0;
}

/** Validate the server's `mouth_config` message; null for anything malformed. */
export function parseMouthConfig(message: unknown): MouthConfig | null {
  if (typeof message !== 'object' || message === null) return null;
  const { fps, delay_ms: delayMs, frame, patch } = message as Record<string, unknown>;
  const f = frame as Record<string, unknown> | undefined;
  const p = patch as Record<string, unknown> | undefined;
  if (!isPositive(fps) || !f || !p) return null;
  if (!isPositive(f.width) || !isPositive(f.height)) return null;
  if (!isCoordinate(p.x) || !isCoordinate(p.y) || !isPositive(p.width) || !isPositive(p.height)) {
    return null;
  }
  if (p.x + p.width > f.width || p.y + p.height > f.height) return null;
  const delay = isCoordinate(delayMs) ? Math.min(delayMs / 1000, MAX_DELAY_SECONDS) : 0;
  return {
    fps,
    delaySeconds: delay,
    frame: { width: f.width, height: f.height },
    patch: { x: p.x, y: p.y, width: p.width, height: p.height },
  };
}

/** Split a binary frame message: little-endian u32 utterance, u32 frame index, then JPEG. */
export function parseMouthFrame(message: ArrayBuffer): MouthFrameHeader | null {
  if (message.byteLength <= HEADER_BYTES) return null;
  const view = new DataView(message);
  return {
    utterance: view.getUint32(0, true),
    index: view.getUint32(4, true),
    jpeg: message.slice(HEADER_BYTES),
  };
}

interface Segment {
  /** Audio position of the chunk within its utterance, in seconds. */
  position: number;
  /** Playback-clock time at which the chunk starts. */
  start: number;
}

/** Where each stretch of interviewer audio sits on the playback clock. */
export class MouthTimeline {
  private readonly utterances = new Map<number, Segment[]>();

  constructor(private readonly sampleRate: number) {}

  addAudio(utterance: number, positionSamples: number, startTime: number): void {
    const segments = this.utterances.get(utterance) ?? [];
    this.utterances.set(utterance, [
      ...segments,
      { position: positionSamples / this.sampleRate, start: startTime },
    ]);
    for (const key of this.utterances.keys()) {
      if (key <= utterance - KEPT_UTTERANCES) this.utterances.delete(key);
    }
  }

  hasUtterance(utterance: number): boolean {
    return this.utterances.has(utterance);
  }

  /** Playback time of a frame, or null when its audio has not been scheduled. */
  timeOfFrame(utterance: number, index: number, fps: number): number | null {
    const segments = this.utterances.get(utterance);
    if (!segments || segments.length === 0) return null;
    const position = index / fps;
    // Chunks normally play back to back, but an underrun shifts later chunks,
    // so anchor on the chunk that actually contains this position.
    let anchor = segments[0];
    for (const segment of segments) {
      if (segment.position <= position) anchor = segment;
      else break;
    }
    return anchor.start + (position - anchor.position);
  }

  clear(): void {
    this.utterances.clear();
  }
}

export interface FramePick<T> {
  /** The newest frame that is due; null when nothing new is due. */
  due: TimedFrame<T> | null;
  /** Frames still in the future, in order. */
  waiting: TimedFrame<T>[];
  /** Frames that were due but superseded, so the caller can release them. */
  skipped: TimedFrame<T>[];
}

/** Take every frame whose time has come; only the newest of them is shown. */
export function pickDueFrame<T>(queue: readonly TimedFrame<T>[], now: number): FramePick<T> {
  const ready = queue.filter((frame) => frame.time <= now);
  const waiting = queue.filter((frame) => frame.time > now);
  if (ready.length === 0) return { due: null, waiting, skipped: [] };
  const due = ready.reduce((latest, frame) => (frame.time >= latest.time ? frame : latest));
  return { due, waiting, skipped: ready.filter((frame) => frame !== due) };
}

/** Insert keeping the queue ordered by display time (frames can decode out of order). */
export function enqueueFrame<T>(
  queue: readonly TimedFrame<T>[],
  frame: TimedFrame<T>
): TimedFrame<T>[] {
  const at = queue.findIndex((queued) => queued.time > frame.time);
  return at === -1 ? [...queue, frame] : [...queue.slice(0, at), frame, ...queue.slice(at)];
}
