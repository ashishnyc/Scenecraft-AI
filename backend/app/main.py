from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.redis import close_redis, get_redis
from app.db.postgres import engine
from app.api.auth import router as auth_router


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

app.include_router(auth_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
