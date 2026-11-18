#!/usr/bin/env bash
# Ditto (PyTorch variant) evaluation environment. Idempotent.
set -euo pipefail
ROOT=/opt/ditto
REPO=$ROOT/ditto-talkinghead
INDEX=http://mirrors.cloud.aliyuncs.com/pypi/simple/
HOST=mirrors.cloud.aliyuncs.com

echo "[1/3] python environment"
# A fresh Ubuntu image has python3 but not its venv module.
python3 -c "import ensurepip" 2>/dev/null || DEBIAN_FRONTEND=noninteractive apt-get install -y -q python3-venv
[ -x $ROOT/venv/bin/pip ] || { rm -rf $ROOT/venv; python3 -m venv $ROOT/venv; }
PIP=$ROOT/venv/bin/pip
$PIP install -q --upgrade pip -i $INDEX --trusted-host $HOST
$PIP install -q torch==2.7.1 torchvision==0.22.1 \
  -f http://mirrors.cloud.aliyuncs.com/pytorch-wheels/cu128/ -i $INDEX --trusted-host $HOST
$PIP install -q numpy==2.0.1 librosa tqdm filetype imageio imageio-ffmpeg opencv-python-headless \
  scikit-image scipy cython einops colored mediapipe onnxruntime-gpu soundfile \
  -i $INDEX --trusted-host $HOST

# What ditto_service.py itself needs to serve the WebSocket.
$PIP install -q fastapi "uvicorn[standard]" websockets -i $INDEX --trusted-host $HOST

echo "[2/3] checkpoints"
mkdir -p $REPO/checkpoints && cd $REPO/checkpoints
FILES="ditto_cfg/v0.4_hubert_cfg_pytorch.pkl ditto_cfg/v0.4_hubert_cfg_trt_online.pkl ditto_cfg/v0.4_hubert_cfg_trt.pkl
ditto_pytorch/aux_models/2d106det.onnx ditto_pytorch/aux_models/det_10g.onnx ditto_pytorch/aux_models/face_landmarker.task
ditto_pytorch/aux_models/hubert_streaming_fix_kv.onnx ditto_pytorch/aux_models/landmark203.onnx
ditto_pytorch/models/appearance_extractor.pth ditto_pytorch/models/decoder.pth ditto_pytorch/models/lmdm_v0.4_hubert.pth
ditto_pytorch/models/motion_extractor.pth ditto_pytorch/models/stitch_network.pth ditto_pytorch/models/warp_network.pth"
fetch() {
  mkdir -p "$(dirname "$1")"
  for host in https://hf-mirror.com https://huggingface.co; do
    if curl -fsSL --retry 3 --connect-timeout 15 --speed-limit 1024 --speed-time 60 -C - -o "$1" \
        "$host/digital-avatar/ditto-talkinghead/resolve/main/$1"; then echo "OK $1 $(stat -c %s "$1")"; return 0; fi
  done
  echo "FAILED $1"; return 1
}
export -f fetch
echo "$FILES" | tr " " "\n" | grep . | xargs -P 4 -I{} bash -c "fetch {}"

echo "[3/3] verify"
$ROOT/venv/bin/python - <<PY
import torch, onnxruntime, numpy
print("torch", torch.__version__, torch.cuda.is_available(), "| onnxruntime", onnxruntime.__version__, onnxruntime.get_available_providers(), "| numpy", numpy.__version__)
PY
echo "DITTO-ENV-OK"
