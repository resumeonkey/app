import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import get_settings
from backend.database import init_db
from backend.routers import master, adaptations, export, context

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
    title="Resume Adapter",
    description="Canadian resume adaptation engine — one master, unlimited tailored versions.",
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

app.include_router(master.router,       prefix="/api/master",       tags=["master"])
app.include_router(adaptations.router,  prefix="/api/adaptations",  tags=["adaptations"])
app.include_router(export.router,       prefix="/api/export",       tags=["export"])
app.include_router(context.router,      prefix="/api/context",      tags=["context"])


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve Next.js static export — must be mounted last so API routes take priority
_static_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "out")
if os.path.exists(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="frontend")
