const DEFAULT_OUTPUT_SAMPLE_RATE = 24000;

export interface PcmPlayer {
  /**
   * Play a chunk of mono PCM16 audio (as received from the backend, default
   * 24kHz). Chunks are scheduled back-to-back using an internal cursor so a
   * burst of frames plays as a continuous stream instead of overlapping at
   * `currentTime`.
   */
  playPcm: (pcm: ArrayBuffer, sampleRate?: number) => void;
  /** Rewind the scheduling cursor (e.g. on teardown or a new turn). */
  reset: () => void;
}

/**
 * Create a PCM player bound to a specific AudioContext. The caller owns the
 * context lifecycle (creation and `close()`), which keeps playback resources
 * tied to the active session instead of a module-level singleton.
 */
export function createPlayer(ctx: AudioContext): PcmPlayer {
  let nextPlayTime = 0;

  function playPcm(
    pcm: ArrayBuffer,
    sampleRate: number = DEFAULT_OUTPUT_SAMPLE_RATE
  ): void {
    const int16 = new Int16Array(pcm);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
      float32[i] = int16[i] / 0x8000;
    }

    const buffer = ctx.createBuffer(1, float32.length, sampleRate);
    buffer.copyToChannel(float32, 0);

    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);

    // Schedule each chunk after the previous one, but never in the past.
    const startAt = Math.max(ctx.currentTime, nextPlayTime);
    source.start(startAt);
    nextPlayTime = startAt + buffer.duration;
  }

  function reset(): void {
    nextPlayTime = 0;
  }

  return { playPcm, reset };
}
