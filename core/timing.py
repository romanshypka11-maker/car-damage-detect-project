import functools
import logging
import time
import uuid
from contextvars import ContextVar
from contextlib import asynccontextmanager

logger = logging.getLogger("timing")
_request_id: ContextVar[str] = ContextVar("request_id", default="-")

@asynccontextmanager
async def log_duration(label: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        logger.info("[%s] %s took %.0fms", get_request_id(), label,
                     (time.perf_counter() - start) * 1000)

def new_request_id() -> str:
    rid = uuid.uuid4().hex[:8]
    _request_id.set(rid)
    return rid


def get_request_id() -> str:
    return _request_id.get()


def log_duration_async(label: str):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                logger.info("[%s] %s took %.0fms", get_request_id(), label,
                            (time.perf_counter() - start) * 1000)
        return wrapper
    return decorator


def log_duration_sync(label: str):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                logger.info("[%s] %s took %.0fms", get_request_id(), label,
                            (time.perf_counter() - start) * 1000)
        return wrapper
    return decorator