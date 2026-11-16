import { expect, it } from 'vitest';
import { initialPresence, observePresence } from './welcomePresence';
it('confirms a person for 500ms and triggers only once while occupied', () => {
 let s=initialPresence();s=observePresence(s,true,0);expect(s.played).toBe(false);
 s=observePresence(s,true,499);expect(s.played).toBe(false);
 s=observePresence(s,true,500);expect(s.played).toBe(true);expect(s.cycle).toBe(1);
 for(let t=750;t<30000;t+=250)s=observePresence(s,true,t);
 expect(s.cycle).toBe(1);
});
it('only rearms after 10 continuous seconds absent and a new confirmed arrival',()=>{
 let s=observePresence(observePresence(initialPresence(),true,0),true,500);
 for(let t=750;t<=10500;t+=250)s=observePresence(s,false,t);
 expect(s.played).toBe(true);
 s=observePresence(s,false,10750);expect(s.played).toBe(false);
 s=observePresence(s,true,11000);s=observePresence(s,true,11500);expect(s.cycle).toBe(2);
});
it('brief absence and another person arriving do not replay',()=>{
 let s=observePresence(observePresence(initialPresence(),true,0),true,500);
 for(let t=750;t<=9000;t+=250)s=observePresence(s,false,t);
 s=observePresence(s,true,9250);expect(s.absentSince).toBeNull();expect(s.cycle).toBe(1);
});
it('unknown camera state or a stalled detector never count as absence',()=>{
 let s=observePresence(observePresence(initialPresence(),true,0),true,500);
 s=observePresence(s,false,750);s=observePresence(s,null,1000);
 s=observePresence(s,false,12000);expect(s.played).toBe(true);expect(s.absentSince).toBe(12000);
 s=observePresence(s,false,25000);expect(s.played).toBe(true);expect(s.absentSince).toBe(25000);
});
it('does not trigger on intermittent false detections',()=>{
 let s=observePresence(initialPresence(),true,0);s=observePresence(s,false,250);
 s=observePresence(s,true,500);expect(s.played).toBe(false);
});
