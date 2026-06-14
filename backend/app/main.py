"""菜鸟庆面试系统 — FastAPI 入口。"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.dev import router as dev_router
from app.api.health import router as health_router
from app.api.heygen import router as heygen_router
from app.api.interview_ws import router as interview_ws_router
from app.api.sessions import router as sessions_router
from app.db.base import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # 开发期建表
    yield


app = FastAPI(title="菜鸟庆面试系统 API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"https://.*\.onrender\.com",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(sessions_router)
app.include_router(interview_ws_router)
app.include_router(heygen_router)
app.include_router(dev_router)


# Built frontend (Docker copies it to /app/frontend/dist; main.py is /app/backend/app/main.py)
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIR.is_dir() and (FRONTEND_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """Serve the SPA: root-level static files (e.g. interviewer.png) else index.html."""
    if full_path:
        candidate = FRONTEND_DIR / full_path
        if candidate.is_file():
            return FileResponse(str(candidate))
    index = FRONTEND_DIR / "index.html"
    if index.is_file():
        return FileResponse(str(index))
    return {"status": "ok", "service": "菜鸟庆面试系统 API"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
