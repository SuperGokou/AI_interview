/** How long the camera may stay silent before the page explains what it is waiting for. */
const SLOW_CAMERA_MS = 4000;

/** Why is the camera still not open? Ask the browser, when it can tell us. */
async function describeCameraWait(): Promise<string> {
  try {
    const result = await navigator.permissions.query({ name: 'camera' as PermissionName });
    if (result.state === 'prompt') return '等待摄像头授权：请在浏览器地址栏左侧的弹窗里点“允许”。';
    if (result.state === 'granted') return '摄像头没有响应：请关闭正在使用摄像头的其他程序，或检查摄像头是否被禁用。';
    if (result.state === 'denied') return '摄像头权限已被拒绝：请点击地址栏左侧的图标，把摄像头改为“允许”后刷新页面。';
  } catch {
    // Some browsers cannot report camera permission; fall through to the generic hint.
  }
  return '仍在等待摄像头：请允许摄像头权限，并确认没有其他程序占用。';
}

export function startPersonCamera(onSample: (present: boolean | null) => void, onStatus: (status: string, error: boolean) => void): () => void {
  let disposed = false, stream: MediaStream | undefined, worker: Worker | undefined;
  let timer = 0, watchdog = 0, slowHint = 0, busy = false, lastTime = -1;
  const video = document.createElement('video');
  video.muted = true; video.playsInline = true;
  const stop = () => {
    disposed = true; window.clearTimeout(timer); window.clearTimeout(watchdog); window.clearTimeout(slowHint);
    worker?.terminate(); video.pause(); video.srcObject = null;
    stream?.getTracks().forEach(t => { t.onended = null; t.onmute = null; t.onunmute = null; t.stop(); });
    document.removeEventListener('visibilitychange', visibility);
  };
  const fail = (message: string) => { if (disposed) return; onSample(null); onStatus(message, true); stop(); };
  const visibility = () => { onSample(null); lastTime = -1; };
  const schedule = () => { if (!disposed) timer = window.setTimeout(() => void capture(), 250); };
  const capture = async () => {
    if (disposed || busy) return;
    const track = stream?.getVideoTracks()[0];
    if (!track || track.readyState === 'ended') { fail('摄像头已断开，请重新连接。'); return; }
    if (document.hidden || track.muted || video.readyState < 2 || video.currentTime === lastTime) {
      onSample(null); schedule(); return;
    }
    busy = true; lastTime = video.currentTime;
    watchdog = window.setTimeout(() => fail('摄像头检测超时，请重新连接摄像头。'), 5000);
    try {
      const bitmap = await createImageBitmap(video, { resizeWidth: 320, resizeHeight: 240 });
      if (disposed) { bitmap.close(); return; }
      worker!.postMessage({ type: 'frame', bitmap, timestamp: performance.now() }, [bitmap]);
    } catch { fail('无法读取摄像头画面，请检查设备。'); }
  };
  document.addEventListener('visibilitychange', visibility);
  onStatus('正在开启摄像头…', false);
  // Opening the camera can wait indefinitely on an unanswered permission prompt or
  // a device another program holds. Say so instead of looking frozen.
  slowHint = window.setTimeout(() => {
    void describeCameraWait().then(message => { if (!disposed && !worker) onStatus(message, false); });
  }, SLOW_CAMERA_MS);
  void (async () => {
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('unsupported');
      stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }, audio: false });
      if (disposed) { stream.getTracks().forEach(t => t.stop()); return; }
      const track = stream.getVideoTracks()[0];
      track.onended = () => fail('摄像头已断开，请重新连接。');
      track.onmute = () => { onSample(null); onStatus('摄像头暂不可用，人员检测已暂停。', false); };
      track.onunmute = () => { onSample(null); };
      video.srcObject = stream; await video.play();
      window.clearTimeout(slowHint);
      if (disposed) return;
      onStatus('正在加载人员检测…', false);
      worker = new Worker('/vendor/presence/person-worker.js');
      watchdog = window.setTimeout(() => fail('人员检测加载超时，请重试。'), 30000);
      worker.onerror = () => fail('人员检测加载失败，请重试。');
      worker.onmessage = ({ data }) => {
        if (disposed) return;
        window.clearTimeout(watchdog);
        if (data.type === 'ready') { onStatus('摄像头已开启，等待来人', false); schedule(); }
        else if (data.type === 'result') {
          if (track.readyState === 'ended') { fail('摄像头已断开，请重新连接。'); return; }
          busy = false;
          onSample(document.hidden || track.muted ? null : Boolean(data.present));
          onStatus('摄像头已开启', false); schedule();
        } else fail('人员检测异常，请重新连接摄像头。');
      };
      worker.postMessage({ type: 'init' });
    } catch { fail('无法开启摄像头，请允许摄像头权限并确认设备可用。'); }
  })();
  return stop;
}
