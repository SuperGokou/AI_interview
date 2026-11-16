# 坤耀云端口型渲染

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
