import importlib.util
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from galvanise.config import settings
from galvanise.database import Base, engine
from galvanise.routes import auth, projects, records, sources
from galvanise.security import check_origin
from galvanise.services.ingestion import run_worker


@asynccontextmanager
async def lifespan(app):
    if settings.auto_create_tables:
        Base.metadata.create_all(engine)
    stop = threading.Event()
    thread = None
    if settings.app_env != "test":
        thread = threading.Thread(target=run_worker, args=(stop,), daemon=True)
        thread.start()
    yield
    stop.set()
    if thread:
        thread.join(timeout=5)


app = FastAPI(title="Galvanise API", lifespan=lifespan)


@app.middleware("http")
async def origin_guard(request: Request, call_next):
    try:
        check_origin(request)
    except Exception as error:
        if hasattr(error, "status_code"):
            return JSONResponse({"detail": error.detail}, status_code=error.status_code)
        raise
    return await call_next(request)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "ai_configured": bool(settings.openai_api_key),
        "github_configured": bool(
            settings.github_client_id and settings.github_client_secret
        ),
    }


if importlib.util.find_spec("galvanise.routes.intelligence") is not None:
    from galvanise.routes.intelligence import router

    app.include_router(router, prefix="/api")
for router in (auth.router, projects.router, sources.router, records.router):
    app.include_router(router)
