import { useCallback, useEffect, useRef, useState } from 'react';
import { arrayBufferToBase64, base64ToArrayBuffer } from '../audio/base64';
import { floatTo16BitPCM } from '../audio/pcm';
import { createPlayer, type PcmPlayer } from '../audio/playback';
import { interviewWsUrl } from '../lib/api';
import type { AvatarStateCommand } from '../lib/avatarStateController';
import type { IntegrityLevel } from '../types';

const INPUT_SAMPLE_RATE = 16000;
const OUTPUT_SAMPLE_RATE = 24000;
const VISION_FPS = 1.5;
const JPEG_QUALITY = 0.6;
// Served from public/ rather than bundled: Vite would inline a file this small
// as a data: URL, which a strict script-src 'self' policy refuses to load.
const WORKLET_URL = '/audio/pcm-worklet.js';
// Camera frames are only used for the model's visual context; 640px wide is
// plenty and is several times smaller than a raw 720p/1080p frame.
const MAX_FRAME_WIDTH = 640;
// Skip a camera frame when the socket is backed up, so audio is never queued behind video.
const MAX_BUFFERED_BYTES = 512 * 1024;

export interface UseInterviewSessionResult {
  start: (token: string, preStream?: MediaStream) => Promise<void>;
  stop: () => void;
  active: boolean;
  videoRef: React.MutableRefObject<HTMLVideoElement | null>;
  micEnabled: boolean;
  cameraEnabled: boolean;
  setMicEnabled: (enabled: boolean) => void;
  setCameraEnabled: (enabled: boolean) => void;
  interviewerText: string;
  candidateText: string;
  integrity: IntegrityLevel;
  speaking: boolean;
  mouthOpeningRef: React.MutableRefObject<number>;
  error: string;
}

export interface UseInterviewSessionOptions {
  playAudio?: boolean;
  onInterviewerFinalText?: (text: string) => void;
  onInterviewerAudioStart?: () => void;
  onInterviewerAudioEnd?: () => void;
  onUserTranscript?: (text: string) => void;
  onAvatarStateCommand?: (command: AvatarStateCommand) => void;
  showInterviewerDeltas?: boolean;
}

/**
 * Wire webcam + mic to /ws/interview and handle all downlink frames.
 *
 * - Mic Float32 to PCM16 16kHz to upstream {type:"audio"}.
 * - Camera ~1.5fps JPEG to upstream {type:"image"}.
 * - Downlink audio (PCM16 24kHz) to Web Audio playback + speaking flag.
 * - Downlink transcript/user_transcript to interviewerText / candidateText.
 * - Downlink integrity to integrity level.
 * - Full cleanup on stop() / unmount, with no leaked tracks, WS, or AudioContexts.
 */
export function useInterviewSession(
  options: UseInterviewSessionOptions = {}
): UseInterviewSessionResult {
  const [active, setActive] = useState(false);
  const [interviewerText, setInterviewerText] = useState('');
  const [candidateText, setCandidateText] = useState('');
  const [integrity, setIntegrity] = useState<IntegrityLevel>('green');
  const [speaking, setSpeaking] = useState(false);
  const mouthOpeningRef = useRef(0);
  const [error, setError] = useState('');
  const [micEnabled, setMicEnabledState] = useState(true);
  const [cameraEnabled, setCameraEnabledState] = useState(true);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const optionsRef = useRef(options);

  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

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
  const micEnabledRef = useRef(true);
  const cameraEnabledRef = useRef(true);

  useEffect(() => {
    if (options.playAudio !== false) return;

    playerRef.current?.reset();
    if (speakTimerRef.current !== null) {
      clearTimeout(speakTimerRef.current);
      speakTimerRef.current = null;
    }
    setSpeaking(false);
  }, [options.playAudio]);

  useEffect(() => {
    if (!active) { mouthOpeningRef.current = 0; return; }
    let frame = 0, wasPlaying = false;
    const tick = () => {
      const sample = playerRef.current?.sample() ?? { opening: 0, playing: false };
      mouthOpeningRef.current = sample.opening;
      if (sample.playing !== wasPlaying) {
        wasPlaying = sample.playing;
        setSpeaking(sample.playing);
        if (sample.playing) optionsRef.current.onInterviewerAudioStart?.();
        else optionsRef.current.onInterviewerAudioEnd?.();
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(frame); mouthOpeningRef.current = 0; };
  }, [active]);

  const setMicEnabled = useCallback((enabled: boolean) => {
    micEnabledRef.current = enabled;
    setMicEnabledState(enabled);
    streamRef.current?.getAudioTracks().forEach((track) => {
      track.enabled = enabled;
    });
  }, []);

  const setCameraEnabled = useCallback((enabled: boolean) => {
    cameraEnabledRef.current = enabled;
    setCameraEnabledState(enabled);
    streamRef.current?.getVideoTracks().forEach((track) => {
      track.enabled = enabled;
    });
  }, []);

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
    micEnabledRef.current = true;
    cameraEnabledRef.current = true;
    setMicEnabledState(true);
    setCameraEnabledState(true);
    setInterviewerText('');
    setCandidateText('');
    setError('');
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
            '当前环境无法访问摄像头/麦克风：请使用 http://localhost:5173 打开，不要使用局域网 IP 或非 https 地址。'
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
              '（权限被拒绝：请在地址栏左侧允许摄像头与麦克风，或检查 Windows 设置 -> 隐私 -> 摄像头/麦克风。）';
          else if (name === 'NotFoundError')
            hint = '（未找到摄像头/麦克风设备。）';
          else if (name === 'NotReadableError')
            hint =
              '（设备被其他程序占用：请关闭正在使用摄像头的其他应用，或检查 Windows 隐私设置。）';
          setError(`摄像头/麦克风访问失败 [${name || 'Error'}]: ${msg} ${hint}`);
          startingRef.current = false;
          return;
        }
      }

      const hasAudioTrack = stream.getAudioTracks().length > 0;
      const hasVideoTrack = stream.getVideoTracks().length > 0;

      streamRef.current = stream;
      stream.getAudioTracks().forEach((track) => {
        track.enabled = micEnabledRef.current;
      });
      stream.getVideoTracks().forEach((track) => {
        track.enabled = cameraEnabledRef.current;
      });
      if (!hasAudioTrack) {
        micEnabledRef.current = false;
        setMicEnabledState(false);
      }
      if (!hasVideoTrack) {
        cameraEnabledRef.current = false;
        setCameraEnabledState(false);
      }
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }

      // Prepare playback before opening the websocket so early audio frames
      // from the proactive opener are never dropped.
      const earlyPlaybackCtx = new AudioContext({ sampleRate: OUTPUT_SAMPLE_RATE });
      playbackCtxRef.current = earlyPlaybackCtx;
      playerRef.current = createPlayer(earlyPlaybackCtx);
      if (earlyPlaybackCtx.state === 'suspended') {
        void earlyPlaybackCtx.resume();
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
          state?: string;
          intent?: string;
          tone?: string;
          audioUrl?: string;
          videoUrl?: string;
        };
        try {
          msg = JSON.parse(event.data as string) as typeof msg;
        } catch {
          return;
        }

        if (msg.type === 'audio' && typeof msg.data === 'string') {
          if (optionsRef.current.playAudio === false) return;

          // Decode and play
          if (playbackCtxRef.current?.state === 'suspended') {
            void playbackCtxRef.current.resume();
          }
          const pcm = base64ToArrayBuffer(msg.data);
          playerRef.current?.playPcm(pcm, OUTPUT_SAMPLE_RATE);

        } else if (
          msg.type === 'transcript_delta' &&
          typeof msg.text === 'string' &&
          optionsRef.current.showInterviewerDeltas === true
        ) {
          if (newInterviewerTurnRef.current) {
            setInterviewerText(msg.text);
            newInterviewerTurnRef.current = false;
          } else {
            setInterviewerText((prev) => prev + msg.text);
          }
        } else if (msg.type === 'transcript' && typeof msg.text === 'string') {
          setInterviewerText(msg.text);
          optionsRef.current.onInterviewerFinalText?.(msg.text);
          newInterviewerTurnRef.current = true;
        } else if (msg.type === 'user_transcript' && typeof msg.text === 'string') {
          setCandidateText(msg.text);
          optionsRef.current.onUserTranscript?.(msg.text);
        } else if (msg.type === 'avatar_state' && typeof msg.state === 'string') {
          if (
            msg.state === 'idle' ||
            msg.state === 'greeting' ||
            msg.state === 'listening' ||
            msg.state === 'speaking' ||
            msg.state === 'thinking'
          ) {
            optionsRef.current.onAvatarStateCommand?.({
              state: msg.state,
              text: typeof msg.text === 'string' ? msg.text : undefined,
              intent: typeof msg.intent === 'string' ? msg.intent : undefined,
              tone: typeof msg.tone === 'string' ? msg.tone : undefined,
              audioUrl: typeof msg.audioUrl === 'string' ? msg.audioUrl : undefined,
              videoUrl: typeof msg.videoUrl === 'string' ? msg.videoUrl : undefined,
            });
          }
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

      // Mic capture context (16kHz, which Qwen-Omni expects).
      if (hasAudioTrack) {
        const captureCtx = new AudioContext({ sampleRate: INPUT_SAMPLE_RATE });
        captureCtxRef.current = captureCtx;

        try {
          await captureCtx.audioWorklet.addModule(WORKLET_URL);
        } catch (e) {
          const msg = e instanceof Error ? e.message : String(e);
          setError(`音频管线初始化失败：${msg}`);
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
          if (
            micEnabledRef.current &&
            wsRef.current?.readyState === WebSocket.OPEN
          ) {
            const pcm = floatTo16BitPCM(e.data as Float32Array);
            wsRef.current.send(
              JSON.stringify({ type: 'audio', data: arrayBufferToBase64(pcm) })
            );
          }
        };
        source.connect(workletNode);
      }

      // ~1.5fps camera frame capture; only starts once video is playing.
      let frameTimerStarted = false;
      const canvas = document.createElement('canvas'); // reused for every frame
      const startFrameCapture = () => {
        if (frameTimerStarted) return;
        frameTimerStarted = true;
        frameTimerRef.current = setInterval(() => {
          if (!hasVideoTrack || !cameraEnabledRef.current) return;
          const video = videoRef.current;
          if (!video || !video.videoWidth) return;
          const ws = wsRef.current;
          if (!ws || ws.readyState !== WebSocket.OPEN) return;
          if (ws.bufferedAmount > MAX_BUFFERED_BYTES) return;
          const scale = Math.min(1, MAX_FRAME_WIDTH / video.videoWidth);
          const width = Math.round(video.videoWidth * scale);
          const height = Math.round(video.videoHeight * scale);
          if (canvas.width !== width || canvas.height !== height) {
            canvas.width = width;
            canvas.height = height;
          }
          const ctx2d = canvas.getContext('2d');
          if (!ctx2d) return;
          ctx2d.drawImage(video, 0, 0, width, height);
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
    micEnabled,
    cameraEnabled,
    setMicEnabled,
    setCameraEnabled,
    interviewerText,
    candidateText,
    integrity,
    speaking,
    mouthOpeningRef,
    error,
  };
}
