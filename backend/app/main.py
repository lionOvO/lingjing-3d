from contextlib import asynccontextmanager, suppress
import asyncio
import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .config import settings
from .database import close_database, create_schema
from .exceptions import database_handler, integrity_handler, not_found_handler, unexpected_handler, validation_handler, NotFoundError
from .routers import router
from .studio import router as studio_router
from .sms_auth import router as sms_auth_router
from .account import router as account_router
from .creation_tools import router as creation_tools_router
from .failure_diagnosis import router as failure_diagnosis_router
from .schemas import HealthResponse
from .milvus_schema import ensure_collections

logger = logging.getLogger("digital_human.api")


async def _initialize_milvus_with_retry() -> None:
    """Warm Milvus without delaying the API listener during first startup."""
    delay = 2
    while True:
        try:
            await asyncio.to_thread(ensure_collections)
            logger.info("Milvus collection initialization completed")
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Milvus is not ready yet; retrying in %ss", delay, exc_info=True)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Initializing database schema")
    try:
        await create_schema()
    except Exception:
        logger.exception("Database schema initialization failed")
        raise
    milvus_task = asyncio.create_task(_initialize_milvus_with_retry())
    yield
    milvus_task.cancel()
    with suppress(asyncio.CancelledError):
        await milvus_task
    await close_database()


app = FastAPI(title="AI 3D Digital Human API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(NotFoundError, not_found_handler)
app.add_exception_handler(RequestValidationError, validation_handler)
app.add_exception_handler(IntegrityError, integrity_handler)
app.add_exception_handler(SQLAlchemyError, database_handler)
app.add_exception_handler(Exception, unexpected_handler)
app.include_router(router)
app.include_router(studio_router)
app.include_router(sms_auth_router)
app.include_router(account_router)
app.include_router(creation_tools_router)
app.include_router(failure_diagnosis_router)


@app.get("/healthz", response_model=HealthResponse)
async def healthz():
    return {"status": "ok"}
