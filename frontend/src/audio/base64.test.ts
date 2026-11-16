import { describe, expect, it } from 'vitest';
import { arrayBufferToBase64, base64ToArrayBuffer } from './base64';

describe('base64 helpers', () => {
  it('round-trips data larger than one encoding chunk', () => {
    const source = new Uint8Array(100_000);
    for (let i = 0; i < source.length; i++) source[i] = (i * 31) % 256;
    const decoded = new Uint8Array(base64ToArrayBuffer(arrayBufferToBase64(source.buffer)));
    expect(decoded.length).toBe(source.length);
    expect(decoded.every((value, i) => value === source[i])).toBe(true);
  });

  it('matches the platform encoder', () => {
    const bytes = new TextEncoder().encode('kunyao');
    expect(arrayBufferToBase64(bytes.buffer)).toBe(btoa('kunyao'));
  });

  it('encodes empty input as an empty string', () => {
    expect(arrayBufferToBase64(new ArrayBuffer(0))).toBe('');
  });
});
