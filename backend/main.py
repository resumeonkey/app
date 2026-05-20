import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.database import init_db
from backend.routers import master, adaptations, export

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(master.router,       prefix="/api/master",       tags=["master"])
app.include_router(adaptations.router,  prefix="/api/adaptations",  tags=["adaptations"])
app.include_router(export.router,       prefix="/api/export",       tags=["export"])


@app.get("/api/health")
def health():
    return {"status": "ok"}
