/**
 * AudioWorkletProcessor that batches mono Float32 microphone audio into ~100 ms
 * chunks and transfers them to the main thread, which converts them to PCM16
 * and sends them upstream.
 *
 * The engine calls process() every 128 samples (8 ms at 16 kHz). Forwarding each
 * call would mean ~125 WebSocket messages per second; batching brings that to 10
 * with no audible effect on turn-taking.
 *
 * Served from /audio/ (not bundled) so it loads under a strict script-src 'self'
 * Content-Security-Policy. Registered under the name "pcm-worklet".
 */
const CHUNK_SECONDS = 0.1;

class PCMWorklet extends AudioWorkletProcessor {
  constructor() {
    super();
    // `sampleRate` is a global of AudioWorkletGlobalScope.
    this.chunkSize = Math.max(128, Math.round(sampleRate * CHUNK_SECONDS));
    this.buffer = new Float32Array(this.chunkSize);
    this.filled = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;

    let offset = 0;
    while (offset < channel.length) {
      const count = Math.min(channel.length - offset, this.chunkSize - this.filled);
      this.buffer.set(channel.subarray(offset, offset + count), this.filled);
      this.filled += count;
      offset += count;
      if (this.filled === this.chunkSize) {
        const chunk = this.buffer;
        this.port.postMessage(chunk, [chunk.buffer]); // transfer, no copy
        this.buffer = new Float32Array(this.chunkSize);
        this.filled = 0;
      }
    }
    return true;
  }
}

registerProcessor('pcm-worklet', PCMWorklet);
