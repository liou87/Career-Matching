"""
对话和长期记忆的存储：LangGraph 官方的 checkpointer（按 thread_id 保存对话状态，
包括等待确认的中断）和 Store（保存长期偏好）。

线上用 Postgres，本地用 SQLite，和业务数据在同一个库里。这些表由 LangGraph 自己
建和迁移（setup()），不在 Alembic 管理范围内，migrations/env.py 会忽略它们。

Serverless 下每个请求单独开一个连接，流式响应结束时关闭。
"""
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.postgres import PostgresStore
from langgraph.store.sqlite import SqliteStore
from psycopg.rows import dict_row

from app.db.session import engine

_setup_done = False
_setup_lock = threading.Lock()


def _setup_once(saver, store) -> None:
    """建表只需要做一次；setup() 本身是幂等的，这里只是省掉每个请求的检查开销。"""
    global _setup_done
    if _setup_done:
        return
    with _setup_lock:
        if not _setup_done:
            saver.setup()
            store.setup()
            _setup_done = True


@contextmanager
def open_persistence() -> Iterator[tuple]:
    """打开 (checkpointer, store)，用完关闭连接。"""
    # checkpointer 和 store 各用一个连接：agent 运行时两者会交替读写，
    # 共用一个连接会出现事务嵌套（SQLite 直接报错）
    url = engine.url
    if url.get_backend_name() == "postgresql":
        dsn = url.set(drivername="postgresql").render_as_string(hide_password=False)
        # LangGraph 文档要求的连接参数：自动提交、字典行
        kwargs = {"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}
        with psycopg.connect(dsn, **kwargs) as c1, psycopg.connect(dsn, **kwargs) as c2:
            saver, store = PostgresSaver(c1), PostgresStore(c2)
            _setup_once(saver, store)
            yield saver, store
    else:
        c1 = sqlite3.connect(url.database, check_same_thread=False, timeout=30)
        # SqliteStore 自己显式 BEGIN/COMMIT，要求连接处于自动提交模式（与它自带的 from_conn_string 一致）
        c2 = sqlite3.connect(url.database, check_same_thread=False, timeout=30, isolation_level=None)
        try:
            saver, store = SqliteSaver(c1), SqliteStore(c2)
            _setup_once(saver, store)
            yield saver, store
        finally:
            c1.close()
            c2.close()
