from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db.redis import close_redis, get_redis
from app.db.postgres import engine

settings = get_settings()
import app.models  # noqa: F401 — registers all ORM models with SQLAlchemy
from app.api.auth import router as auth_router
from app.api.workspaces import router as workspaces_router
from app.api.projects import router as projects_router
from app.api.tasks import router as tasks_router
from app.api.subtasks import router as subtasks_router
from app.api.ws import router as ws_router
from app.api.characters import router as characters_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: verify connections
    get_redis()  # initialises the Redis client
    yield
    # Shutdown: close connections
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title="Scenecraft AI",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(workspaces_router)
app.include_router(projects_router)
app.include_router(tasks_router)
app.include_router(subtasks_router)
app.include_router(ws_router)
app.include_router(characters_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
