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
from app.api.competitor import router as competitor_router
from app.api.trends import router as trends_router
from app.api.pitches import router as pitches_router
from app.api.audio import router as audio_router
from app.api.video import router as video_router
from app.services.scheduler import start_scheduler, stop_scheduler
from app.core.security import add_security_headers, validate_secrets_at_startup


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    validate_secrets_at_startup()
    get_redis()
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title="Scenecraft AI",
    version="1.0.0",
    description="""
## Scenecraft AI API

End-to-end AI video production platform. Turns content ideas into published YouTube videos.

### Pipeline overview

1. **Content Intelligence** — trend detection, pitch generation, originality check
2. **Script Pipeline** — outline → scene expansion → consistency check → copyright scan
3. **Audio Pipeline** — voice routing → synthesis (ElevenLabs/Fish Audio) → assembly
4. **Video Pipeline** — shot planning → clip generation (Kling) → music (Suno) → assembly → QC
5. **Publish Pipeline** — HLS preview → video review → thumbnail → metadata → YouTube upload

### Authentication

All endpoints (except `/auth/*` and `/health`) require a Bearer JWT obtained from `/auth/token`.

### Rate limits

- Standard endpoints: 120 requests / minute per IP
- Auth endpoints: 20 requests / minute per IP
""",
    openapi_tags=[
        {"name": "auth", "description": "Google OAuth2 login and JWT token management"},
        {"name": "workspaces", "description": "Workspace CRUD — top-level organisational unit"},
        {"name": "projects", "description": "Project CRUD — content series within a workspace"},
        {"name": "tasks", "description": "Task lifecycle — from idea to published video"},
        {"name": "subtasks", "description": "Subtask dependency management"},
        {"name": "characters", "description": "Character/talent roster management"},
        {"name": "audio", "description": "Audio streaming endpoints"},
        {"name": "video", "description": "Video preview, review, thumbnail, metadata, analytics"},
        {"name": "competitor", "description": "Competitor channel intelligence"},
        {"name": "trends", "description": "Trending topic detection"},
        {"name": "pitches", "description": "AI pitch generation and inbox"},
    ],
    lifespan=lifespan,
)

app.middleware("http")(add_security_headers)

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
app.include_router(competitor_router)
app.include_router(trends_router)
app.include_router(pitches_router)
app.include_router(audio_router)
app.include_router(video_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
