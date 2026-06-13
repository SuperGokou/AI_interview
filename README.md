# 菜鸟庆面试系统

AI 自动面试官 + HR 管理后台。借鉴 yzbot 实时音视频管线,核心为 DeepSeek + Qwen 双模型。

## 本地开发
后端:
    cd backend
    python -m venv .venv && .venv\Scripts\activate
    pip install -r requirements.txt
    python -m uvicorn app.main:app --reload --port 8000

前端:
    cd frontend
    npm install
    npm run dev   # http://localhost:5173

## 测试
    cd backend && python -m pytest
    cd frontend && npm run test

## 配置
根目录 `.env`(已 gitignore):`QWEN_API_KEY`、`DEEPSEEK_API_KEY`。
