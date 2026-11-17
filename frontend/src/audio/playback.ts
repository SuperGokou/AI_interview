const DEFAULT_OUTPUT_SAMPLE_RATE = 24000;
export interface PcmPlayer {
  /** Queue PCM16 audio. `notBefore` (context time) holds the start back; returns
   *  the context time at which this chunk will begin, or null for empty input. */
  playPcm: (pcm: ArrayBuffer, sampleRate?: number, notBefore?: number) => number | null;
  reset: () => void;
  sample: () => { opening: number; playing: boolean };
  /** The playback position being heard now, on the context clock. */
  now: () => number;
}
export interface PcmPlayerOptions { playbackRate?: number }

/** PCM and mouth envelopes use the same playback clock, never packet arrival time.
 * Adapted from our KY-BOT frontDesk speech-timeline and lip-motion approach.
 * This is energy-driven articulation, not phoneme recognition.
 */
export function createPlayer(ctx: AudioContext, options: PcmPlayerOptions = {}): PcmPlayer {
  let nextPlayTime = 0, opening = 0, previousTime = 0;
  const rate = Math.max(.5, Math.min(2, options.playbackRate ?? 1));
  const frames: {start:number; end:number; rms:number}[] = [];
  const sources = new Set<AudioBufferSourceNode>();
  function playPcm(pcm: ArrayBuffer, sampleRate = DEFAULT_OUTPUT_SAMPLE_RATE, notBefore = 0): number | null {
    const int16 = new Int16Array(pcm);
    if (!int16.length) return null;
    const samples = Float32Array.from(int16, x=>x/0x8000);
    const buffer = ctx.createBuffer(1, samples.length, sampleRate);
    buffer.copyToChannel(samples, 0);
    const source = ctx.createBufferSource();
    source.buffer = buffer; source.playbackRate.value = rate;
    source.connect(ctx.destination); sources.add(source);
    source.onended = ()=>{ sources.delete(source); source.disconnect(); };
    const start = Math.max(ctx.currentTime, nextPlayTime, notBefore);
    const windowSize = Math.max(1, Math.round(sampleRate*.01));
    for(let i=0;i<samples.length;i+=windowSize){
      const end=Math.min(samples.length,i+windowSize);let sum=0,crossings=0;
      for(let j=i;j<end;j++){sum+=samples[j]**2;if(j>i&&samples[j]*samples[j-1]<0)crossings++;}
      const articulation=1-.65*Math.min(1,Math.max(0,(crossings/Math.max(1,end-i-1)-.18)/.3));
      frames.push({start:start+i/sampleRate/rate,end:start+end/sampleRate/rate,rms:Math.sqrt(sum/(end-i))*articulation});
    }
    source.start(start); nextPlayTime=start+buffer.duration/rate;
    return start;
  }
  function currentTime(): number {
    const stamp = ctx.getOutputTimestamp?.();
    return stamp && typeof stamp.contextTime === 'number' && stamp.contextTime>0 && typeof stamp.performanceTime === 'number' ? Math.min(ctx.currentTime, stamp.contextTime+Math.max(0,performance.now()-stamp.performanceTime)/1000) : ctx.currentTime;
  }
  function sample() {
    const now = currentTime();
    const dt=Math.min(.1,Math.max(0,now-previousTime));previousTime=now;
    while(frames.length&&frames[0].end<=now)frames.shift();
    const playing=frames.length>0&&frames[0].start<=now&&ctx.state!=='suspended';
    const rms=playing?frames[0].rms:0;
    const target=rms>.007?.9*(1-Math.exp(-(rms-.004)/.09)):0;
    opening+=(target-opening)*(1-Math.exp(-dt/(target>opening?.012:.025)));
    if(!playing||opening<.008)opening=0;
    return {opening,playing};
  }
  function reset(){
    for(const source of sources){source.onended=null;try{source.stop();}catch{/* already ended */}source.disconnect();}
    sources.clear();frames.length=0;nextPlayTime=0;opening=0;previousTime=ctx.currentTime;
  }
  return {playPcm,reset,sample,now:currentTime};
}
