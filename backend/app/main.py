from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api.router import api_router
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.services.seed import seed_if_empty


def _ensure_oven_capacity_columns() -> bool:
    """幂等补列；返回列是否为本次新建（用于旧数据卷一次性回填）。"""
    inspector = inspect(engine)
    existing = {c["name"] for c in inspector.get_columns("ovens")}
    added = False
    with engine.begin() as conn:
        if "rack_slots" not in existing:
            conn.execute(text("ALTER TABLE ovens ADD COLUMN rack_slots INTEGER"))
            added = True
        if "chamber_trays" not in existing:
            conn.execute(text("ALTER TABLE ovens ADD COLUMN chamber_trays INTEGER"))
            added = True
    return added


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if _ensure_oven_capacity_columns():
        # 旧数据卷：按默认准备一层 1 号炉（仅在首次补列时执行）
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE ovens SET rack_slots = 2, chamber_trays = 1, "
                    "capacity_note = '醒发架2格/炉膛1盘' WHERE label = '一层 1 号炉'"
                )
            )
    if settings.seed_on_empty:
        db = SessionLocal()
        try:
            seed_if_empty(db)
        finally:
            db.close()
    yield


app = FastAPI(title="BakeOven", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api")
