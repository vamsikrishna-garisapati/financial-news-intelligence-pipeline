"""FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.routes import api_router
from app.config import get_settings
from app.security.redact import RedactingFilter
from app.services.job_worker import job_worker_loop


def _configure_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        logging.basicConfig(level=level)
    redactor = RedactingFilter()
    for handler in root.handlers:
        handler.addFilter(redactor)
        handler.setLevel(level)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    stop_event = asyncio.Event()
    worker_task: asyncio.Task[None] | None = None
    if settings.job_worker_enabled:
        worker_task = asyncio.create_task(
            job_worker_loop(stop_event, settings=settings),
            name="collection-job-worker",
        )
    try:
        yield
    finally:
        stop_event.set()
        if worker_task is not None:
            try:
                await asyncio.wait_for(worker_task, timeout=settings.job_poll_interval_secs + 5)
            except TimeoutError:
                worker_task.cancel()
                try:
                    await worker_task
                except asyncio.CancelledError:
                    pass


def create_app() -> FastAPI:
    settings = get_settings()
    _configure_logging(settings.log_level)

    app = FastAPI(
        title="Financial News Intelligence Pipeline",
        version=__version__,
        description=(
            "Collect financial news via Apify, normalize and deduplicate articles, "
            "store them in PostgreSQL, and expose search/analytics APIs. "
            "Sentiment and categories are best-effort labels, not investment advice. "
            "Self-hosted MVP: no user accounts; if you expose this API publicly you must "
            "add authentication, rate limiting, HTTPS, and access controls yourself."
        ),
        lifespan=lifespan,
    )

    origins = settings.cors_origin_list
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Accept"],
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": jsonable_encoder(
                    exc.errors(),
                    custom_encoder={Exception: str},
                )
            },
        )

    app.include_router(api_router)
    return app


app = create_app()


def run() -> None:
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run()
