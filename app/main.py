from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app import auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    await auth.warm()
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
