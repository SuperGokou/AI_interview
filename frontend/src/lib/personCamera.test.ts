import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { startPersonCamera } from './personCamera';
let worker: { onmessage?: (e:{data:{type:string;present?:boolean}})=>void; onerror?:()=>void; postMessage:ReturnType<typeof vi.fn>; terminate:ReturnType<typeof vi.fn> };
let track: { stop:ReturnType<typeof vi.fn>; muted:boolean; onended:null|(()=>void); onmute:null|(()=>void); onunmute:null|(()=>void) };
let stream: MediaStream;
beforeEach(()=>{
 vi.useFakeTimers();
 vi.spyOn(HTMLMediaElement.prototype,'play').mockResolvedValue();
 vi.spyOn(HTMLMediaElement.prototype,'pause').mockImplementation(()=>{});
 track={stop:vi.fn(),muted:false,onended:null,onmute:null,onunmute:null};
 stream={getTracks:()=>[track],getVideoTracks:()=>[track]} as unknown as MediaStream;
 Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{getUserMedia:vi.fn().mockResolvedValue(stream)}});
 vi.stubGlobal('Worker',class {constructor(){worker=this;}postMessage=vi.fn();terminate=vi.fn();});
});
afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals();vi.useRealTimers();Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:undefined});});
it('requests video only and releases the camera and worker on exit',async()=>{
 const stop=startPersonCamera(vi.fn(),vi.fn());await vi.advanceTimersByTimeAsync(0);
 expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith(expect.objectContaining({audio:false}));
 expect(worker.postMessage).toHaveBeenCalledWith({type:'init'});
 stop();expect(track.stop).toHaveBeenCalledTimes(1);expect(worker.terminate).toHaveBeenCalledTimes(1);
});
it('releases a camera permission request that resolves after starting the interview',async()=>{
 let resolve!:(s:MediaStream)=>void;
 vi.mocked(navigator.mediaDevices.getUserMedia).mockImplementation(()=>new Promise(r=>{resolve=r;}));
 const stop=startPersonCamera(vi.fn(),vi.fn());stop();resolve(stream);await vi.advanceTimersByTimeAsync(0);
 expect(track.stop).toHaveBeenCalledTimes(1);
});
it('a camera disconnect emits unknown, not absent, and cleans up',async()=>{
 const sample=vi.fn(),status=vi.fn();startPersonCamera(sample,status);await vi.advanceTimersByTimeAsync(0);
 track.onended!();expect(sample).toHaveBeenLastCalledWith(null);expect(status).toHaveBeenLastCalledWith(expect.stringContaining('断开'),true);
 expect(track.stop).toHaveBeenCalled();expect(worker.terminate).toHaveBeenCalled();
});
it('permission refusal exposes a recoverable error rather than an empty-room result',async()=>{
 vi.mocked(navigator.mediaDevices.getUserMedia).mockRejectedValue(new Error('denied'));
 const sample=vi.fn(),status=vi.fn();startPersonCamera(sample,status);await vi.advanceTimersByTimeAsync(0);
 expect(sample).toHaveBeenCalledWith(null);expect(sample).not.toHaveBeenCalledWith(false);expect(status).toHaveBeenLastCalledWith(expect.stringContaining('权限'),true);
});
it('treats an ended track as an error even if the browser emits no ended event',async()=>{
 const sample=vi.fn(),status=vi.fn();startPersonCamera(sample,status);await vi.advanceTimersByTimeAsync(0);
 Object.assign(track,{readyState:'ended'});worker.onmessage!({data:{type:'ready'}});
 await vi.advanceTimersByTimeAsync(300);
 expect(sample).toHaveBeenCalledWith(null);expect(sample).not.toHaveBeenCalledWith(false);
 expect(status).toHaveBeenLastCalledWith(expect.stringContaining('断开'),true);
});
it('explains what it is waiting for when the camera does not open',async()=>{
 vi.mocked(navigator.mediaDevices.getUserMedia).mockImplementation(()=>new Promise(()=>{}));
 Object.defineProperty(navigator,'permissions',{configurable:true,value:{query:vi.fn().mockResolvedValue({state:'prompt'})}});
 const status=vi.fn();const stop=startPersonCamera(vi.fn(),status);
 await vi.advanceTimersByTimeAsync(3900);expect(status).toHaveBeenCalledTimes(1);
 await vi.advanceTimersByTimeAsync(200);
 expect(status).toHaveBeenLastCalledWith(expect.stringContaining('点“允许”'),false);
 vi.mocked(navigator.permissions.query).mockResolvedValue({state:'granted'} as PermissionStatus);
 stop();
 const second=vi.fn();const stopSecond=startPersonCamera(vi.fn(),second);await vi.advanceTimersByTimeAsync(4100);
 expect(second).toHaveBeenLastCalledWith(expect.stringContaining('其他程序'),false);stopSecond();
});
it('says nothing extra when the camera opens promptly',async()=>{
 const status=vi.fn();startPersonCamera(vi.fn(),status);await vi.advanceTimersByTimeAsync(0);
 const calls=status.mock.calls.length;await vi.advanceTimersByTimeAsync(5000);
 expect(status.mock.calls.slice(calls).every(([message])=>!String(message).includes('等待'))).toBe(true);
});
