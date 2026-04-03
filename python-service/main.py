import logging
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GO_BASE = "http://localhost:8080"
TIMEOUT = httpx.Timeout(5.0)

# ---------------------------------------------------------------------------
# Shared async HTTP client
# ---------------------------------------------------------------------------

http_client: httpx.AsyncClient | None = None


# ---------------------------------------------------------------------------
# Lifespan (startup + shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(base_url=GO_BASE, timeout=TIMEOUT)

    # Startup connectivity check
    try:
        r = await http_client.get("/ping")
        r.raise_for_status()
        logger.info("Go service reachable at %s", GO_BASE)
    except Exception as exc:
        logger.warning("Go service unreachable at startup: %s", exc)

    yield

    await http_client.aclose()
    logger.info("HTTP client closed — shutdown complete")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="FastAPI Proxy Service", lifespan=lifespan)

# ---------------------------------------------------------------------------
# Middleware — request logging
# ---------------------------------------------------------------------------

@app.middleware("http")
async def logging_middleware(request: Request, call_next) -> Response:
    start = time.perf_counter()
    response: Response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "method=%s path=%s status=%d duration=%.2fms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unavailable(detail: str = "go-service unavailable") -> JSONResponse:
    return JSONResponse(status_code=503, content={"error": detail})


async def _request(method: str, path: str, **kwargs) -> httpx.Response:
    """Forward a request to the Go service; raise _GoUnavailable on transport errors."""
    try:
        return await http_client.request(method, path, **kwargs)
    except httpx.TransportError as exc:
        logger.error("Transport error calling %s %s: %s", method, path, exc)
        raise _GoUnavailable() from exc


async def _get(path: str) -> httpx.Response:
    return await _request("GET", path)


async def _post(path: str, payload: dict) -> httpx.Response:
    return await _request("POST", path, json=payload)


class _GoUnavailable(Exception):
    """Sentinel raised when the Go service cannot be reached."""


# ---------------------------------------------------------------------------
# Exception handler for _GoUnavailable
# ---------------------------------------------------------------------------

@app.exception_handler(_GoUnavailable)
async def go_unavailable_handler(request: Request, exc: _GoUnavailable):
    return _unavailable()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class EchoRequest(BaseModel):
    text: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "fastapi"}


@app.get("/ping")
async def ping():
    resp = await _get("/ping")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    data: dict = resp.json()
    data["source"] = "go-service"
    return data


@app.get("/users")
async def users():
    resp = await _get("/users")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    user_list: list = resp.json()
    for user in user_list:
        user["proxied_by"] = "fastapi"
    return user_list


@app.post("/echo")
async def echo(body: EchoRequest):
    resp = await _post("/echo", {"text": body.text})
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    data: dict = resp.json()
    data["original_text"] = body.text
    return data


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        log_config=None,   # use our own logging config
    )
