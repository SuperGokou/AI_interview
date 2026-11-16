"""坤耀面试系统 — FastAPI 入口。"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.dashboard import router as dashboard_router
from app.api.dev import router as dev_router
from app.api.health import router as health_router
from app.api.heygen import router as heygen_router
from app.api.interview_ws import router as interview_ws_router
from app.api.jobs import router as jobs_router
from app.api.questions import router as questions_router
from app.api.sessions import router as sessions_router
from app.api.supervisors import router as supervisors_router
from app.db.base import init_db
from app.security import AdminBoundaryMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # Fail startup if database initialization fails.
    yield


app = FastAPI(title="坤耀面试系统 API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(AdminBoundaryMiddleware)

app.include_router(health_router)
app.include_router(sessions_router)
app.include_router(jobs_router)
app.include_router(questions_router)
app.include_router(dashboard_router)
app.include_router(interview_ws_router)
app.include_router(heygen_router)
app.include_router(dev_router)
app.include_router(supervisors_router)


# Built frontend (Docker copies it to /app/frontend/dist; main.py is /app/backend/app/main.py)
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIR.is_dir() and (FRONTEND_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")


# Vite fingerprints everything under /assets, so it can be cached forever. Other
# public files (videos, WASM, model) keep stable names: cache for a day, then revalidate.
_IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
_STATIC_CACHE = "public, max-age=86400"
_NO_CACHE = "no-cache"


@app.middleware("http")
async def cache_fingerprinted_assets(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/assets/") and response.status_code == 200:
        response.headers["Cache-Control"] = _IMMUTABLE_CACHE
    return response


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """Serve the SPA: root-level static files (e.g. interviewer.png) else index.html."""
    if full_path:
        candidate = (FRONTEND_DIR / full_path).resolve()
        if not candidate.is_relative_to(FRONTEND_DIR.resolve()):
            raise HTTPException(404, "not found")
        if full_path.startswith(("api/", "ws/")):
            raise HTTPException(404, "not found")
        if candidate.is_file():
            return FileResponse(str(candidate), headers={"Cache-Control": _STATIC_CACHE})
    index = FRONTEND_DIR / "index.html"
    if index.is_file():
        # Always revalidate the shell so a new deploy is picked up immediately.
        return FileResponse(str(index), headers={"Cache-Control": _NO_CACHE})
    return {"status": "ok", "service": "坤耀面试系统 API"}


if __name__ == "__main__":
    import uvicorn

    # Development entry point only; production runs uvicorn from the Dockerfile.
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
