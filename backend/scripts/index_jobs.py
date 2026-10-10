"""
给已有的岗位建检索索引（片段 + 向量）。新入库的岗位会自动建索引，这个脚本用于
第一次上线检索功能、或者更换 embedding 模型之后补算。

运行（在 backend 目录下）：
    python scripts/index_jobs.py              # 只补没有索引、或缺向量的岗位
    python scripts/index_jobs.py --all        # 全部重建
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import models  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.llm import embeddings  # noqa: E402
from app.services.retrieval import index_job  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--all", action="store_true", help="全部重建")
    args = p.parse_args()

    with SessionLocal() as db:
        jobs = db.query(models.Job).filter(models.Job.status == "active").order_by(models.Job.id).all()
        done = 0
        for job in jobs:
            chunks = db.query(models.JobChunk).filter(models.JobChunk.job_id == job.id).all()
            missing_vectors = embeddings.enabled() and any(c.embedding is None for c in chunks)
            if args.all or not chunks or missing_vectors:
                n = index_job(db, job)
                done += 1
                print(f"岗位 {job.id} {job.title}: {n} 个片段")
        print(f"完成，重建 {done} 个岗位的索引；向量：{'已启用' if embeddings.enabled() else '未配置 embedding，只建关键词索引'}")


if __name__ == "__main__":
    main()
