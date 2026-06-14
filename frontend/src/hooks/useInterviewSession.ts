import { useCallback, useEffect, useRef, useState } from 'react';
import { floatTo16BitPCM } from '../audio/pcm';
import { createPlayer, type PcmPlayer } from '../audio/playback';
import { interviewWsUrl } from '../lib/api';
import type { IntegrityLevel } from '../types';

const INPUT_SAMPLE_RATE = 16000;
const OUTPUT_SAMPLE_RATE = 24000;
const VISION_FPS = 1.5;
const JPEG_QUALITY = 0.6;
const WORKLET_URL = new URL('../audio/pcm-worklet.js', import.meta.url);

// Debounce duration (ms) for resetting speaking→false after last audio frame.
const SPEAKING_DEBOUNCE_MS = 350;

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  let binary = '';
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function base64ToArrayBuffer(b64: string): ArrayBuffer {
  const binary = atob(b64);
  const buffer = new ArrayBuffer(binary.length);
  const view = new Uint8Array(buffer);
  for (let i = 0; i < binary.length; i++) {
    view[i] = binary.charCodeAt(i);
  }
  return buffer;
}

export interface UseInterviewSessionResult {
  start: (token: string, preStream?: MediaStream) => Promise<void>;
  stop: () => void;
  active: boolean;
  videoRef: React.MutableRefObject<HTMLVideoElement | null>;
  interviewerText: string;
  candidateText: string;
  integrity: IntegrityLevel;
  speaking: boolean;
  error: string;
}

/**
 * Wire webcam + mic → /ws/interview and handle all downlink frames.
 *
 * - Mic Float32 → PCM16 16kHz → upstream {type:"audio"}
 * - Camera ~1.5fps JPEG → upstream {type:"image"}
 * - Downlink audio (PCM16 24kHz) → Web Audio playback + speaking flag
 * - Downlink transcript/user_transcript → interviewerText / candidateText
 * - Downlink integrity → integrity level
 * - Full cleanup on stop() / unmount — no leaked tracks, WS, or AudioContexts
 */
export function useInterviewSession(): UseInterviewSessionResult {
  const [active, setActive] = useState(false);
  const [interviewerText, setInterviewerText] = useState('');
  const [candidateText, setCandidateText] = useState('');
  const [integrity, setIntegrity] = useState<IntegrityLevel>('green');
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState('');

  const videoRef = useRef<HTMLVideoElement | null>(null);

  // All mutable session resources live in refs so cleanup closures always
  // reference the current values without stale captures.
  const streamRef = useRef<MediaStream | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const captureCtxRef = useRef<AudioContext | null>(null);
  const playbackCtxRef = useRef<AudioContext | null>(null);
  const playerRef = useRef<PcmPlayer | null>(null);
  const frameTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const speakTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startingRef = useRef(false); // guard against double-start
  const newInterviewerTurnRef = useRef(true); // true = next delta starts a fresh subtitle line

  const stop = useCallback(() => {
    // Stop all camera/mic tracks
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;

    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }

    // Close WebSocket
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    // Clear frame capture timer
    if (frameTimerRef.current !== null) {
      clearInterval(frameTimerRef.current);
      frameTimerRef.current = null;
    }

    // Clear speaking debounce timer
    if (speakTimerRef.current !== null) {
      clearTimeout(speakTimerRef.current);
      speakTimerRef.current = null;
    }

    // Close audio contexts
    if (captureCtxRef.current && captureCtxRef.current.state !== 'closed') {
      void captureCtxRef.current.close();
    }
    captureCtxRef.current = null;

    playerRef.current?.reset();
    playerRef.current = null;

    if (playbackCtxRef.current && playbackCtxRef.current.state !== 'closed') {
      void playbackCtxRef.current.close();
    }
    playbackCtxRef.current = null;

    startingRef.current = false;
    newInterviewerTurnRef.current = true;
    setActive(false);
    setSpeaking(false);
  }, []);

  // Cleanup on unmount
  useEffect(() => stop, [stop]);

  const start = useCallback(
    async (token: string, preStream?: MediaStream) => {
      // Guard: don't allow double-start
      if (startingRef.current || active) {
        return;
      }
      startingRef.current = true;
      setError('');

      let stream: MediaStream;
      if (preStream) {
        stream = preStream;
      } else {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          setError(
            '当前环境无法访问摄像头/麦克风:请用 http://localhost:5173 打开(不要用局域网 IP 或非 https 地址)。'
          );
          startingRef.current = false;
          return;
        }
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            video: true,
            audio: { echoCancellation: true, noiseSuppression: true },
          });
        } catch (e) {
          const name = e instanceof DOMException ? e.name : '';
          const msg = e instanceof Error ? e.message : String(e);
          let hint = '';
          if (name === 'NotAllowedError')
            hint =
              '(权限被拒绝:请在地址栏左侧允许摄像头与麦克风,或检查 Windows 设置→隐私→摄像头/麦克风)';
          else if (name === 'NotFoundError')
            hint = '(未找到摄像头/麦克风设备)';
          else if (name === 'NotReadableError')
            hint =
              '(设备被其他程序占用:请关闭正在使用摄像头的其他应用,或检查 Windows 隐私设置)';
          setError(`摄像头/麦克风访问失败 [${name || 'Error'}]: ${msg} ${hint}`);
          startingRef.current = false;
          return;
        }
      }

      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }

      // Open WebSocket
      const ws = new WebSocket(interviewWsUrl(token));
      wsRef.current = ws;

      ws.onerror = () => {
        setError('WebSocket 连接失败');
        stop();
      };

      ws.onclose = () => {
        // If this was the current ws and we're still "active", treat as a
        // disconnect (not triggered by stop()).
        if (wsRef.current === ws) {
          wsRef.current = null;
          stop();
        }
      };

      ws.onmessage = (event: MessageEvent) => {
        let msg: {
          type?: string;
          data?: string;
          text?: string;
          level?: string;
          message?: string;
        };
        try {
          msg = JSON.parse(event.data as string) as typeof msg;
        } catch {
          return;
        }

        if (msg.type === 'audio' && typeof msg.data === 'string') {
          // Decode and play
          const pcm = base64ToArrayBuffer(msg.data);
          playerRef.current?.playPcm(pcm, OUTPUT_SAMPLE_RATE);

          // Drive avatar mouth: set speaking=true, debounce reset to false
          setSpeaking(true);
          if (speakTimerRef.current !== null) {
            clearTimeout(speakTimerRef.current);
          }
          speakTimerRef.current = setTimeout(() => {
            setSpeaking(false);
            speakTimerRef.current = null;
          }, SPEAKING_DEBOUNCE_MS);
        } else if (msg.type === 'transcript_delta' && typeof msg.text === 'string') {
          if (newInterviewerTurnRef.current) {
            setInterviewerText(msg.text);
            newInterviewerTurnRef.current = false;
          } else {
            setInterviewerText((prev) => prev + msg.text);
          }
        } else if (msg.type === 'transcript' && typeof msg.text === 'string') {
          setInterviewerText(msg.text);
          newInterviewerTurnRef.current = true;
        } else if (msg.type === 'user_transcript' && typeof msg.text === 'string') {
          setCandidateText(msg.text);
        } else if (msg.type === 'integrity' && typeof msg.level === 'string') {
          const lvl = msg.level as IntegrityLevel;
          if (lvl === 'green' || lvl === 'yellow' || lvl === 'red') {
            setIntegrity(lvl);
          }
        } else if (msg.type === 'error' && typeof msg.message === 'string') {
          setError(msg.message);
        }
      };

      // Wait for WS to open before building audio pipeline
      await new Promise<void>((resolve, reject) => {
        const onOpen = () => {
          ws.removeEventListener('open', onOpen);
          ws.removeEventListener('error', onErr);
          resolve();
        };
        const onErr = () => {
          ws.removeEventListener('open', onOpen);
          ws.removeEventListener('error', onErr);
          reject(new Error('WebSocket failed to open'));
        };
        if (ws.readyState === WebSocket.OPEN) {
          resolve();
        } else {
          ws.addEventListener('open', onOpen);
          ws.addEventListener('error', onErr);
        }
      }).catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : String(e);
        setError(msg);
        stop();
        throw e;
      });

      // Playback context (24kHz — matches backend PCM16 24kHz output)
      const playbackCtx = new AudioContext({ sampleRate: OUTPUT_SAMPLE_RATE });
      playbackCtxRef.current = playbackCtx;
      playerRef.current = createPlayer(playbackCtx);

      // Mic capture context (16kHz — what Qwen-Omni expects)
      const captureCtx = new AudioContext({ sampleRate: INPUT_SAMPLE_RATE });
      captureCtxRef.current = captureCtx;

      try {
        await captureCtx.audioWorklet.addModule(WORKLET_URL);
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setError(`音频管线初始化失败: ${msg}`);
        stop();
        return;
      }

      // Check we weren't cancelled while loading the worklet
      if (wsRef.current !== ws) {
        return;
      }

      const source = captureCtx.createMediaStreamSource(stream);
      const workletNode = new AudioWorkletNode(captureCtx, 'pcm-worklet');
      workletNode.port.onmessage = (e: MessageEvent) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          const pcm = floatTo16BitPCM(e.data as Float32Array);
          wsRef.current.send(
            JSON.stringify({ type: 'audio', data: arrayBufferToBase64(pcm) })
          );
        }
      };
      source.connect(workletNode);

      // ~1.5fps camera frame capture — only starts once video is playing
      let frameTimerStarted = false;
      const startFrameCapture = () => {
        if (frameTimerStarted) return;
        frameTimerStarted = true;
        frameTimerRef.current = setInterval(() => {
          const video = videoRef.current;
          if (!video || !video.videoWidth) return;
          const canvas = document.createElement('canvas');
          canvas.width = video.videoWidth;
          canvas.height = video.videoHeight;
          const ctx2d = canvas.getContext('2d');
          if (!ctx2d) return;
          ctx2d.drawImage(video, 0, 0);
          canvas.toBlob(
            (blob) => {
              if (!blob) return;
              void blob.arrayBuffer().then((buf) => {
                if (wsRef.current?.readyState === WebSocket.OPEN) {
                  wsRef.current.send(
                    JSON.stringify({
                      type: 'image',
                      data: arrayBufferToBase64(buf),
                    })
                  );
                }
              });
            },
            'image/jpeg',
            JPEG_QUALITY
          );
        }, 1000 / VISION_FPS);
      };

      const vid = videoRef.current;
      if (vid) {
        if (vid.readyState >= 2) {
          // Already have metadata/data
          startFrameCapture();
        } else {
          vid.addEventListener('loadeddata', startFrameCapture, { once: true });
        }
      }

      setActive(true);
      startingRef.current = false;
    },
    [active, stop]
  );

  return {
    start,
    stop,
    active,
    videoRef,
    interviewerText,
    candidateText,
    integrity,
    speaking,
    error,
  };
}
