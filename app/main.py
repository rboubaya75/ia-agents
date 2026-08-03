import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app import auth

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Best effort. A JWKS endpoint unreachable at boot must not crash-loop the task:
    # /health — the ALB health check of §11.2 — stays green so that an upstream Cognito
    # outage degrades authentication instead of draining the whole fleet, while /ready
    # reports the degraded state for operators and deployment tooling.
    try:
        await auth.warm()
    except Exception:
        logger.warning("JWKS warmup failed, starting degraded", exc_info=True)
    yield
    # shutdown: uvicorn --timeout-graceful-shutdown drains in-flight requests;
    # no signal handler — SIGTERM is handled exclusively by uvicorn.


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/ready")
async def ready() -> JSONResponse:
    if await auth.is_ready():
        return JSONResponse({"status": "ready"})
    return JSONResponse({"status": "not_ready"}, status_code=503)
