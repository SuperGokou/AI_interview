# 坤曜云端口型渲染

使用原面试官 `zoom-interviewer-listening.png`，仅融合嘴部附近，背景、发型与服装不变。
原始开场视频不属于此服务的处理范围。

## 组件

- MuseTalk 1.5，源代码固定于 `0a89dec45a0192b824e3cf4daf96c239440c5ed8`。
- `render_portrait.py`：固定人物裁剪、音频驱动推理、嘴部局部羽化、MP4 音画合成；当前为样片验证程序。
- `service.py`：仅监听 `127.0.0.1:8765`，Bearer 密钥鉴权，单任务并发，拒绝超出 30 秒的音频。
- `kunyao-mouth.service`：独立受限系统用户运行，通过 systemd 自动恢复。
- `download-models.py`：按上游文件名下载权重，支持续传。

目前使用独立 Python 3.12 虚拟环境；宿主机驱动已安装，无需重新安装 CUDA 驱动。
PyTorch 自带所需 CUDA 用户态运行库。容器工具链单独安装，不作为样片生成的前置条件。

## 下载加速

阿里云 ECS 使用官方 VPC 内网源：`http://mirrors.cloud.aliyuncs.com/pypi/simple/`。
该内网域名按官方文档使用 HTTP；HTTPS 证书域名不匹配，不应通过关闭 HTTPS 证书验证来处理。
公网环境使用 `https://mirrors.aliyun.com/pypi/simple/`。
参考：https://developer.aliyun.com/mirror/pypi

MuseTalk UNet 权重 SHA-256：
`7ebf6c98c181e20838e4c0054e96e944ac60d5d692cc01db42839fe11b787007`

## 验证

在项目根目录运行：

```sh
.venv/bin/python -m pytest deploy/gpu/test_service.py -q
```

云端 MuseTalk 工作目录运行：

```sh
../venv/bin/python render_portrait.py \
  --portrait zoom-interviewer-listening.png \
  --audio kunyao-test.wav --output results/kunyao-mouth-test.mp4 --repeat 2
```

第一次耗时包括首次音频特征处理，第二次更接近常驻服务速度。
必须查看生成视频并测量完整编码耗时，不能以模型宣传帧率判断端到端延迟。

生产接入前保留原网页音频口型回退。仅部署渲染服务不代表面试网页已接入。
不要公开暴露渲染端口或把密钥加入前端包；跨机调用应走受限 SSH 隧道。

## 实时口型流(已接入面试页面)

`stream_service.py` 是面试中实际使用的服务：后端把面试官的语音边生成边送进来，服务返回嘴部区域的 JPEG 小图，浏览器按音频播放时间把它叠到面试官画面上。

### 组件

- `stream_service.py`：WebSocket `/stream`，仅监听 `127.0.0.1:8765`，Bearer 密钥鉴权，`MAX_SESSIONS` 限制同时连接数。
- `stream_engine.py`：共享一套模型，每次只渲染新就绪的少量帧，多路会话轮流使用显卡。
- `stream_logic.py`：语音缓冲、帧就绪判断(向后看 3 帧)、帧的二进制格式。
- `lower_face.py`：下半脸合成(羽化、肤色匹配、局部锐化)。
- `speech_gate.py`：句内短停顿保持生成的嘴型，持续静音 0.6 秒后才淡回原图。
- `stream_probe.py`：延迟与并发实测工具。
- `kunyao-mouth-stream.service`：systemd 单元，密钥放在 `/opt/kunyao-musetalk/service.env`(权限 600)。

### 部署

```sh
# GPU 主机上，脚本可重复执行
/root/kunyao-gpu/setup-env.sh                 # 系统依赖 + PyTorch 2.7.1 (CUDA 12.8)
systemctl enable --now kunyao-mouth-stream
curl http://127.0.0.1:8765/health
```

应用服务器通过内网或 SSH 隧道访问，然后在应用的 `.env` 里配置：

```env
MOUTH_STREAM_URL=ws://127.0.0.1:18765/stream
MOUTH_STREAM_KEY=<service.env 里的 GPU_API_KEY>
MOUTH_PLAYBACK_DELAY_MS=450
```

```sh
ssh -N -L 18765:127.0.0.1:8765 <gpu-host>     # 本地调试用的隧道
```

未配置、连不上、服务繁忙或中途断开时，面试照常进行，页面自动退回按音量驱动的近似口型。

### 底图与对齐

面试页面的底图是一段连续视频(`interviewer-continuous-v1.mp4`)，它比静态人像整体暗几个色阶，位置也差约 1 像素。口型必须基于页面实际显示的那一帧来渲染，否则嘴周围会出现色差：

```sh
# 在 MuseTalk 目录下，从视频左半边(聆听画面)取第一帧
ffmpeg -i interviewer-continuous-v1.mp4 -vf "crop=1672:942:0:0" -frames:v 1 interviewer-base-frame.png
echo "PORTRAIT=interviewer-base-frame.png" >> /opt/kunyao-musetalk/service.env
systemctl restart kunyao-mouth-stream
```

模型画出的嘴相对人像原本的嘴有固定偏移(本人像实测：右 2.9、下 9.7 像素)，`lower_face.py` 里的 `GENERATED_FACE_OFFSET` 会把生成的下半脸移回原位。更换人像或取景框后需重新测量：

```sh
python measure_mouth.py interviewer-base-frame.png
```

### 实测(NVIDIA L20，25 fps，每帧约 5.6 kB)

| 场景 | 需要的播放延迟 |
|------|----------------|
| 1 路，本机回环 | 110-210 ms |
| 2 路同时说话 | 约 320 ms |
| 3 路同时说话 | 跟不上(整卡约 55 fps) |
| 1 路，经公网 SSH 隧道(往返 188 ms) | 450 ms 时每段开头约 6 帧晚到，700 ms 时无晚到 |

一张 L20 的上限是两路同时说话。晚到的帧会被跳过，那一小段显示近似口型。

### 尚未验证

- 浏览器里的实际观感(叠加位置、边缘是否可见、音画是否对齐)需要真人面试确认；自动化只验证到“每一帧在其音频播放前送达”。
- 底图是静止人像，除嘴部外没有头部动作。
