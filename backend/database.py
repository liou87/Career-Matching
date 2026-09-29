import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


def _database_url() -> str:
    # 线上（Vercel）通过 DATABASE_URL 连 Postgres；本地没配就用 backend/ 下的 SQLite
    url = os.getenv("DATABASE_URL")
    if not url:
        return f"sqlite:///{Path(__file__).resolve().parent / 'job_helper.db'}"
    # Neon 等给的是 postgres:// 或 postgresql://，SQLAlchemy 要显式指定 psycopg 驱动
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = _database_url()

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # Serverless 实例可能闲置很久，连接会被 Neon 断开，用前先 ping 一下
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
