from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def ensure_schema() -> None:
    """create_all + 补齐旧库缺失的列（无迁移框架下的幂等升级）。"""
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if "ovens" not in tables:
        return
    columns = {c["name"] for c in inspector.get_columns("ovens")}
    with engine.begin() as conn:
        if "rack_slots" not in columns:
            conn.execute(text("ALTER TABLE ovens ADD COLUMN rack_slots INTEGER"))
        if "hearth_slots" not in columns:
            conn.execute(text("ALTER TABLE ovens ADD COLUMN hearth_slots INTEGER"))
        # 旧库一次性兜底：一层 1 号炉按 醒发架2 / 炉膛1 准备（用户已改过则不动）
        conn.execute(
            text(
                "UPDATE ovens SET rack_slots = 2, hearth_slots = 1 "
                "WHERE label = '一层 1 号炉' AND rack_slots IS NULL AND hearth_slots IS NULL"
            )
        )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
