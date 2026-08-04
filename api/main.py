from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.routers import ai, damage, pricing
from core.db import close_pool, init_pool
from core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await init_pool()
    yield
    await close_pool()


app = FastAPI(title="DeepAuto API", version="2.0", lifespan=lifespan)

app.include_router(pricing.router)
app.include_router(damage.router)
app.include_router(ai.router)
