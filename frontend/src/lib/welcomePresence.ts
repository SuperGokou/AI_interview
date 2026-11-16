export interface PresenceState {
  played: boolean;
  cycle: number;
  presentSince: number | null;
  absentSince: number | null;
  lastSample: number | null;
}
export const initialPresence = (): PresenceState => ({ played: false, cycle: 0, presentSince: null, absentSince: null, lastSample: null });
/** Only consecutive, healthy observations count. Unknown/stalled cameras never rearm. */
export function observePresence(previous: PresenceState, present: boolean | null, now: number): PresenceState {
  const s = { ...previous };
  if (present === null || (s.lastSample !== null && (now - s.lastSample > 1500 || now < s.lastSample))) {
    s.presentSince = s.absentSince = null;
  }
  s.lastSample = now;
  if (present === null) return s;
  if (present) {
    s.absentSince = null;
    s.presentSince ??= now;
    if (!s.played && now - s.presentSince >= 500) { s.played = true; s.cycle++; }
  } else {
    s.presentSince = null;
    s.absentSince ??= now;
    if (s.played && now - s.absentSince >= 10000) s.played = false;
  }
  return s;
}
