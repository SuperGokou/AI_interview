// MediaPipe 0.10.32 is served locally. No camera data leaves this worker/browser.
self.exports = {};
importScripts('/vendor/presence/vision_bundle.js');
let detector;
self.onmessage = async ({ data }) => {
  try {
    if (data.type === 'init') {
      const vision = await self.exports.FilesetResolver.forVisionTasks('/vendor/presence/wasm');
      detector = await self.exports.ObjectDetector.createFromOptions(vision, {
        baseOptions: { modelAssetPath: '/vendor/presence/person.tflite', delegate: 'CPU' },
        runningMode: 'VIDEO', categoryAllowlist: ['person'], scoreThreshold: 0.55, maxResults: 5,
      });
      self.postMessage({ type: 'ready' });
    } else if (data.type === 'frame') {
      try {
        const result = detector.detectForVideo(data.bitmap, data.timestamp);
        self.postMessage({ type: 'result', present: result.detections.length > 0 });
      } finally { data.bitmap.close(); }
    }
  } catch { self.postMessage({ type: 'error' }); }
};
