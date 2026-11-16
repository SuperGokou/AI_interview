/**
 * AudioWorkletProcessor that forwards raw mono Float32 audio frames from the
 * audio rendering thread to the main thread via postMessage. The main thread
 * is responsible for converting these frames to PCM16 and sending them upstream.
 *
 * Registered under the name "pcm-worklet".
 */
class PCMWorklet extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) {
      // Copy the frame; the underlying buffer is reused by the engine.
      this.port.postMessage(channel.slice(0));
    }
    return true;
  }
}

registerProcessor('pcm-worklet', PCMWorklet);
