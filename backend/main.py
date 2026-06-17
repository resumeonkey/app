import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import get_settings
from backend.database import init_db
from backend.routers import master, adaptations, export, context, search, saved_jobs, resume_v2

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from backend.services.storage import is_remote
    if not is_remote():
        import os
        os.makedirs(settings.upload_dir, exist_ok=True)
        os.makedirs(settings.output_dir, exist_ok=True)
    init_db()
    yield


app = FastAPI(
    title="Resumonkey",
    description="Resumonkey — motor de adaptación de CV canadienses. Una app de SoyManada.",
    version="0.1.0",
    lifespan=lifespan,
)

_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global exception handler — ensures CORS headers are present on 500s ───────
# Without this, unhandled exceptions return 500 WITHOUT Access-Control-Allow-Origin,
# which the browser blocks as a CORS error ("Network Error") instead of showing
# the actual HTTP 500 status.
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.getLogger(__name__).exception("Unhandled exception: %s", exc)
    origin = request.headers.get("origin", "")
    headers = {}
    if origin:
        allowed = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
        if "*" in allowed or origin in allowed:
            headers["Access-Control-Allow-Origin"] = origin
            headers["Access-Control-Allow-Credentials"] = "true"
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers=headers,
    )

app.include_router(master.router,       prefix="/api/master",       tags=["master"])
app.include_router(adaptations.router,  prefix="/api/adaptations",  tags=["adaptations"])
app.include_router(export.router,       prefix="/api/export",       tags=["export"])
app.include_router(context.router,      prefix="/api/context",      tags=["context"])
app.include_router(search.router,       prefix="/api/search",        tags=["search"])
app.include_router(saved_jobs.router,   prefix="/api/jobs/saved",    tags=["saved_jobs"])
app.include_router(resume_v2.router,     prefix="/api/resume",        tags=["resume_v2"])


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve Next.js static export — must be mounted last so API routes take priority
_static_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "out")
if os.path.exists(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="frontend")
