"""HeyGen 流式数字人:服务端用 API key 换取浏览器用的短时会话 token。"""

import httpx
from fastapi import APIRouter, HTTPException

import app.config as _config

router = APIRouter(prefix="/api/heygen")

# 模块级,便于测试注入 fake transport。
def _client() -> httpx.Client:
    return httpx.Client(timeout=15.0)


@router.post("/token")
def create_token() -> dict:
    settings = _config.get_settings()
    if not settings.heygen_api_key:
        raise HTTPException(status_code=503, detail="HEYGEN_API_KEY 未配置")
    try:
        with _client() as client:
            resp = client.post(
                f"{settings.heygen_base_url}/v1/streaming.create_token",
                headers={"x-api-key": settings.heygen_api_key},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # 网络/上游错误 → 502
        raise HTTPException(status_code=502, detail=f"HeyGen token 获取失败: {exc}")
    token = (data.get("data") or {}).get("token")
    if not token:
        raise HTTPException(status_code=502, detail="HeyGen 返回无 token")
    return {"token": token, "avatar_id": settings.heygen_avatar_id}
