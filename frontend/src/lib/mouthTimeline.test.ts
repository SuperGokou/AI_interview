import { describe, expect, it } from 'vitest';
import {
  MouthTimeline,
  enqueueFrame,
  parseMouthConfig,
  parseMouthFrame,
  pickDueFrame,
  type TimedFrame,
} from './mouthTimeline';

const CONFIG = {
  type: 'mouth_config',
  fps: 25,
  delay_ms: 450,
  frame: { width: 1672, height: 941 },
  patch: { x: 763, y: 281, width: 215, height: 142 },
};

function frame(time: number, index = 0): TimedFrame<string> {
  return { utterance: 0, index, time, image: `f${index}` };
}

describe('parseMouthConfig', () => {
  it('accepts the server message', () => {
    expect(parseMouthConfig(CONFIG)).toEqual({
      fps: 25,
      delaySeconds: 0.45,
      frame: { width: 1672, height: 941 },
      patch: { x: 763, y: 281, width: 215, height: 142 },
    });
  });

  it('clamps an unreasonable delay and defaults a missing one to zero', () => {
    expect(parseMouthConfig({ ...CONFIG, delay_ms: 60_000 })?.delaySeconds).toBe(2);
    expect(parseMouthConfig({ ...CONFIG, delay_ms: undefined })?.delaySeconds).toBe(0);
  });

  it.each([
    null,
    'x',
    { ...CONFIG, fps: 0 },
    { ...CONFIG, frame: undefined },
    { ...CONFIG, patch: { x: 0, y: 0, width: 0, height: 10 } },
    { ...CONFIG, patch: { x: 1600, y: 0, width: 215, height: 142 } }, // outside the frame
    { ...CONFIG, patch: { x: -1, y: 0, width: 10, height: 10 } },
  ])('rejects malformed config %#', (message) => {
    expect(parseMouthConfig(message)).toBeNull();
  });
});

describe('parseMouthFrame', () => {
  it('reads the little-endian header and returns the JPEG bytes', () => {
    const buffer = new ArrayBuffer(11);
    const view = new DataView(buffer);
    view.setUint32(0, 3, true);
    view.setUint32(4, 257, true);
    new Uint8Array(buffer).set([9, 8, 7], 8);
    const parsed = parseMouthFrame(buffer);
    expect(parsed?.utterance).toBe(3);
    expect(parsed?.index).toBe(257);
    expect(Array.from(new Uint8Array(parsed!.jpeg))).toEqual([9, 8, 7]);
  });

  it('rejects a message with no image data', () => {
    expect(parseMouthFrame(new ArrayBuffer(8))).toBeNull();
  });
});

describe('MouthTimeline', () => {
  it('places frames on the playback clock of their audio', () => {
    const timeline = new MouthTimeline(24000);
    timeline.addAudio(0, 0, 10.45); // first chunk starts after the playback delay
    timeline.addAudio(0, 2400, 10.55);
    expect(timeline.timeOfFrame(0, 0, 25)).toBeCloseTo(10.45);
    expect(timeline.timeOfFrame(0, 5, 25)).toBeCloseTo(10.65);
  });

  it('follows an audio underrun that pushed later chunks back', () => {
    const timeline = new MouthTimeline(24000);
    timeline.addAudio(0, 0, 1.0);
    timeline.addAudio(0, 24000, 2.5); // should have started at 2.0
    expect(timeline.timeOfFrame(0, 24, 25)).toBeCloseTo(1.96);
    expect(timeline.timeOfFrame(0, 25, 25)).toBeCloseTo(2.5);
    expect(timeline.timeOfFrame(0, 30, 25)).toBeCloseTo(2.7);
  });

  it('knows nothing about utterances whose audio has not arrived, and forgets old ones', () => {
    const timeline = new MouthTimeline(24000);
    expect(timeline.timeOfFrame(4, 0, 25)).toBeNull();
    for (let u = 0; u < 5; u++) timeline.addAudio(u, 0, u);
    expect(timeline.hasUtterance(1)).toBe(false);
    expect(timeline.hasUtterance(2)).toBe(true);
    timeline.clear();
    expect(timeline.hasUtterance(4)).toBe(false);
  });
});

describe('frame queue', () => {
  it('shows the newest due frame and reports the ones it skipped', () => {
    const queue = [frame(1.0, 0), frame(1.04, 1), frame(1.08, 2), frame(1.12, 3)];
    const pick = pickDueFrame(queue, 1.09);
    expect(pick.due?.index).toBe(2);
    expect(pick.skipped.map((f) => f.index)).toEqual([0, 1]);
    expect(pick.waiting.map((f) => f.index)).toEqual([3]);
  });

  it('returns nothing while every frame is still in the future', () => {
    const queue = [frame(2.0)];
    expect(pickDueFrame(queue, 1.0)).toEqual({ due: null, waiting: queue, skipped: [] });
    expect(pickDueFrame([], 1.0).due).toBeNull();
  });

  it('keeps the queue ordered when frames finish decoding out of order', () => {
    let queue: TimedFrame<string>[] = [];
    for (const f of [frame(1.08, 2), frame(1.0, 0), frame(1.12, 3), frame(1.04, 1)]) {
      queue = enqueueFrame(queue, f);
    }
    expect(queue.map((f) => f.index)).toEqual([0, 1, 2, 3]);
  });
});
