import { useCallback, useEffect, useRef, useState } from 'react';
import { initialPresence, observePresence } from '../lib/welcomePresence';
import { startPersonCamera } from '../lib/personCamera';
export function useWelcomePresence(enabled: boolean) {
  const state = useRef(initialPresence());
  const stopRef = useRef<(() => void) | undefined>();
  const [playing, setPlaying] = useState(false);
  const [playKey, setPlayKey] = useState(0);
  const [played, setPlayed] = useState(false);
  const [status, setStatus] = useState('正在开启摄像头…');
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const stop = useCallback(() => { stopRef.current?.(); stopRef.current = undefined; }, []);
  const finished = useCallback(() => setPlaying(false), []);
  useEffect(() => {
    if (!enabled) { stop(); return; }
    state.current = observePresence(state.current, null, performance.now());
    stopRef.current = startPersonCamera(present => {
      const previous = state.current;
      const next = observePresence(previous, present, performance.now());
      state.current = next;
      setPlayed(next.played);
      if (next.cycle !== previous.cycle) { setPlayKey(next.cycle); setPlaying(true); }
      if (!next.played) setPlaying(false);
    }, (message, failed) => { setStatus(message); setError(failed); });
    return stop;
  }, [enabled, attempt, stop]);
  return { playing, playKey, played, status, error, stop, finished, retry: () => setAttempt(n => n + 1) };
}
