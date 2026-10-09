"""
Alembic 迁移入口。数据库地址和表定义都直接复用应用本身的配置，
不在 alembic.ini 里重复写连接串：

    alembic upgrade head                         # 本地 SQLite
    DATABASE_URL="postgresql://..." alembic upgrade head   # 线上 Neon
"""
from logging.config import fileConfig

from alembic import context

from app.db import models  # noqa: F401  导入后所有表才会注册到 Base.metadata
from app.db.session import Base, engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=engine.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite 不支持大部分 ALTER TABLE，用 batch 模式（建新表再拷数据）
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
