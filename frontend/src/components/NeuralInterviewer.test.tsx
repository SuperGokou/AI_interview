import { act, fireEvent, render, screen, cleanup } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import NeuralInterviewer from './NeuralInterviewer';
let tick: FrameRequestCallback;
let draws: number[];
beforeEach(()=>{
 vi.spyOn(HTMLMediaElement.prototype,'pause').mockImplementation(()=>{});
 vi.spyOn(HTMLMediaElement.prototype,'play').mockResolvedValue();
 vi.spyOn(window,'requestAnimationFrame').mockImplementation(cb=>{tick=cb;return 1;});
 vi.spyOn(window,'cancelAnimationFrame').mockImplementation(()=>{});
 draws=[];
 const context={globalAlpha:1,drawImage:vi.fn(function(this:{globalAlpha:number}){draws.push(this.globalAlpha);})};
 vi.spyOn(HTMLCanvasElement.prototype,'getContext').mockReturnValue(context as unknown as CanvasRenderingContext2D);
});
afterEach(()=>{cleanup();vi.restoreAllMocks();});
function ready(container:HTMLElement){
 const video=container.querySelector('video')!;
 Object.defineProperties(video,{readyState:{value:4},videoWidth:{value:3344},videoHeight:{value:942}});
 return video;
}
it('autoplays a silent shared-clock face clip without controls or independent eye patches',()=>{
 const {container}=render(<NeuralInterviewer mouthOpeningRef={{current:0}}/>);
 expect(screen.getByAltText('坤曜 AI 面试官')).toHaveAttribute('src','/zoom-interviewer-listening.png');
 const video=ready(container);
 expect(video.muted).toBe(true);expect(video.autoplay).toBe(true);expect(video.controls).toBe(false);
 expect(container.querySelectorAll('video')).toHaveLength(1);
 act(()=>tick(16));expect(draws).toEqual([1]);
 expect(container.querySelector('canvas')?.style.opacity).toBe('1');
});
it('blends into talking, bridges short gaps, then returns to closed-mouth listening',()=>{
 const mouth={current:1};const {container}=render(<NeuralInterviewer mouthOpeningRef={mouth}/>);ready(container);
 for(const t of [16,116,216])act(()=>tick(t));
 expect(draws[draws.length - 1]).toBe(1);
 mouth.current=0;draws=[];act(()=>tick(266));expect(draws).toEqual([]);
 act(()=>tick(366));expect(draws[draws.length - 1]).toBeCloseTo(1-100/140);
 draws=[];act(()=>tick(466));expect(draws).toEqual([1]);
});
it('falls back when the clip cannot load',()=>{
 const {container}=render(<NeuralInterviewer mouthOpeningRef={{current:0}}/>);
 fireEvent.error(container.querySelector('video')!);
 expect(container.querySelector('video[src*="continuous"]')).toBeNull();
 expect(screen.getByLabelText('坤曜轻量口型数字人')).toBeInTheDocument();
});
it('stops playback and cancels animation when removed',()=>{
 const {unmount}=render(<NeuralInterviewer />);unmount();
 expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled();
 expect(window.cancelAnimationFrame).toHaveBeenCalledWith(1);
});
