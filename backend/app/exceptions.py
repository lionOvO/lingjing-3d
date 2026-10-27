"""Application errors with a stable JSON response envelope."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .logging_config import logger


class NotFoundError(Exception):
    def __init__(self, resource: str, resource_id: int) -> None:
        self.resource = resource
        self.resource_id = resource_id


async def not_found_handler(_: Request, exc: NotFoundError) -> JSONResponse:
    logger.info("Resource not found: %s id=%s", exc.resource, exc.resource_id)
    return JSONResponse(status_code=404, content={"detail": f"{exc.resource} {exc.resource_id} was not found"})


async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.warning("Validation failed for %s: %s", request.url.path, exc.errors())
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})


async def integrity_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    logger.warning("Integrity constraint failed for %s: %s", request.url.path, exc.orig)
    return JSONResponse(status_code=409, content={"detail": "The request conflicts with existing data"})


async def database_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.exception("Database failure for %s", request.url.path, exc_info=exc)
    return JSONResponse(status_code=503, content={"detail": "Database service is temporarily unavailable"})


async def unexpected_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled application error for %s", request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
