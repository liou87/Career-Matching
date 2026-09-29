"""
把本地 SQLite（backend/job_helper.db）的数据整体复制到 Postgres。

用法（在 backend/ 下运行，目标库须为空）：
    python scripts/migrate_to_postgres.py "postgresql://user:pass@host/db?sslmode=require"
"""
import sys
from pathlib import Path

from sqlalchemy import create_engine, func, select, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import models  # noqa: E402  注册所有表到 Base.metadata

SQLITE_PATH = Path(__file__).resolve().parent.parent / "job_helper.db"


def to_sqlalchemy_url(url: str) -> str:
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)

    src = create_engine(f"sqlite:///{SQLITE_PATH}")
    dst = create_engine(to_sqlalchemy_url(sys.argv[1]))
    tables = models.Base.metadata.sorted_tables

    models.Base.metadata.create_all(bind=dst)

    with src.connect() as s, dst.begin() as d:
        for table in tables:
            if d.execute(select(func.count()).select_from(table)).scalar():
                sys.exit(f"目标库的 {table.name} 表不是空的，已中止，没有写入任何数据")

        for table in tables:
            rows = [dict(r._mapping) for r in s.execute(select(table))]
            if rows:
                d.execute(table.insert(), rows)
            print(f"{table.name}: {len(rows)} 行")

            # 显式插入了 id，要把自增序列推到当前最大值之后
            if dst.dialect.name == "postgresql" and "id" in table.c:
                d.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table.name}), 0) + 1, false)"
                ))

    print("迁移完成")


if __name__ == "__main__":
    main()
