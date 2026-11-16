# 坤耀面试系统

React + FastAPI 的独立面试系统，支持职位与题库管理、候选人邀请、实时语音面试、转写、报告、监督员链接和摄像头迎宾。

## 生产部署

推荐使用 `deploy/compose.yml`，前后端同域，Caddy 自动配置公网域名 HTTPS，数据库使用持久化卷。详见 [部署说明](deploy/README.md)。

```sh
cp deploy/.env.example deploy/.env
# 编辑 deploy/.env：域名、管理员密码和自己的模型 API 配置
chmod 600 deploy/.env
cd deploy
docker compose --env-file .env up -d --build
```

- 迎宾页面：`https://你的域名/interview`
- 管理后台：`https://你的域名/admin/jobs`
- 创建职位、题目和候选人后，分发含 token 的面试邀请链接。
- 摄像头需 HTTPS 与用户授权；有声自动播放可能需要浏览器交互或专用终端策略。
- 后端管理接口有 Basic Auth，必须配置 `ADMIN_PASSWORD`，未配置时拒绝管理请求。
- 候选人和监督员链接是访问凭证，请勿公开转发。
- 默认关闭演示会话接口；开发时才显式设置 `DEV_ENDPOINTS=true`。

## 本地开发与检查

使用 Python 3.12、Node.js 24。

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cp .env.example .env
# 填写 ADMIN_PASSWORD 和模型配置
cd frontend
npm ci
npm test
npm run build
cd ..
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest backend/tests -q
./scripts/start-local.sh
```

本地打开 `http://127.0.0.1:8010/interview`。Docker 本地模式使用根目录 compose，端口仅绑定本机。

## 行为与范围

迎宾：连续检测到人员约 500ms 播放一次，人员持续在场不重复；连续无人 10 秒后重置。检测在浏览器本地执行，检测画面不上传。正式面试按授权流程使用音视频服务。

当前数字人使用预生成连续素材，由实时语音驱动近似口型，**并非实时逐字精准口型生成**。可选 GPU 实验工具位于 `deploy/gpu/`，不是基础部署必需项。

单组织部署，现阶段使用管理员共享凭据，不具备完整租户隔离、SSO、细粒度角色、管理员审计和自动数据保留策略。报告为模型辅助输出，需要人工复核。

## 商业交付

参阅 [第三方与交付边界](THIRD_PARTY_NOTICES.md) 和 [发布检查记录](docs/RELEASE_REVIEW.md)。本仓库不包含客户数据库、真实 API 密钥或服务器私钥。所有第三方权利不因代码推送而自动转让；交付前需落实授权。
