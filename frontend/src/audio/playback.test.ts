import { createPlayer } from './playback';
function setup() {
  const sources: any[] = [];
  const ctx = {currentTime: 0, destination: {}, createBuffer: (_: number,n: number,r: number)=>({duration:n/r,copyToChannel:vi.fn()}),createBufferSource:()=>{const s={playbackRate:{value:1},connect:vi.fn(),disconnect:vi.fn(),start:vi.fn(),stop:vi.fn(),onended:null};sources.push(s);return s;}};
  return {ctx,sources,player:createPlayer(ctx as unknown as AudioContext)};
}
test('mouth follows scheduled playback, including queued speech and silent gaps',()=>{
 const {ctx,player}=setup();
 player.playPcm(new Int16Array(2400).fill(8000).buffer);
 player.playPcm(new Int16Array(2400).buffer);
 player.playPcm(new Int16Array(2400).fill(8000).buffer);
 ctx.currentTime=.04;expect(player.sample().opening).toBeGreaterThan(.1);
 ctx.currentTime=.19;expect(player.sample().opening).toBeLessThan(.02);
 ctx.currentTime=.24;expect(player.sample().opening).toBeGreaterThan(.1);
 ctx.currentTime=.31;expect(player.sample()).toEqual({opening:0,playing:false});
});
test('reset stops queued audio and closes the mouth',()=>{
 const {player,sources}=setup();player.playPcm(new Int16Array(2400).fill(8000).buffer);player.reset();
 expect(sources[0].stop).toHaveBeenCalled();expect(player.sample()).toEqual({opening:0,playing:false});
});
test('playPcm reports where each chunk lands and honours a hold-back',()=>{
 const {ctx,player}=setup();ctx.currentTime=1;
 expect(player.playPcm(new Int16Array(2400).fill(8000).buffer,24000,1.45)).toBeCloseTo(1.45);
 expect(player.playPcm(new Int16Array(2400).fill(8000).buffer)).toBeCloseTo(1.55);
 expect(player.playPcm(new Int16Array(0).buffer)).toBeNull();
 expect(player.now()).toBe(1);
});
