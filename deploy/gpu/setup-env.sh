#!/usr/bin/env bash
# Kunyao lip-sync renderer: base environment. Idempotent; safe to re-run.
set -euo pipefail
ROOT=/opt/kunyao-musetalk
MUSETALK_COMMIT=0a89dec45a0192b824e3cf4daf96c239440c5ed8
export DEBIAN_FRONTEND=noninteractive

echo "[1/4] system packages"
apt-get update -qq || echo "apt index partially stale; continuing"
apt-get install -y -qq ffmpeg python3.10-venv python3-pip git curl >/dev/null

echo "[2/4] MuseTalk source"
mkdir -p "$ROOT/cache"
if [ ! -d "$ROOT/MuseTalk/.git" ]; then
  echo "MuseTalk checkout missing" && exit 1
fi
# pinned commit is fetched once; no network needed on re-runs
git -C "$ROOT/MuseTalk" checkout -q "$MUSETALK_COMMIT"

echo "[3/4] python environment"
[ -d "$ROOT/venv" ] || python3 -m venv "$ROOT/venv"
PIP="$ROOT/venv/bin/pip"
INDEX=http://mirrors.cloud.aliyuncs.com/pypi/simple/
HOST=mirrors.cloud.aliyuncs.com
"$PIP" install -q --upgrade pip -i "$INDEX" --trusted-host "$HOST"
# CUDA 12.8 build: the same wheels run on the Blackwell card the service moves to later.
"$PIP" install -q torch==2.7.1 torchvision==0.22.1 \
  -f http://mirrors.cloud.aliyuncs.com/pytorch-wheels/cu128/ -i "$INDEX" --trusted-host "$HOST"
"$PIP" install -q -r /root/kunyao-gpu/requirements-runtime.txt -i "$INDEX" --trusted-host "$HOST"

echo "[4/4] verify"
"$ROOT/venv/bin/python" - <<'PY'
import torch
print("torch", torch.__version__, "cuda", torch.version.cuda, "available", torch.cuda.is_available())
print("device", torch.cuda.get_device_name(0))
PY
ffmpeg -version | head -1
echo "ENV-OK"
