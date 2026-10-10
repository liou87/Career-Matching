"""
AI 助手评测用的种子数据：把评测集写进一个独立的数据库，保证每次评测环境一致，
也不碰本地真实数据。内容包括 15 个岗位（含检索索引）、脱敏画像、v3 的单岗分析结果和技能缺口排行。
"""
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.db import models
from app.services.retrieval import index_job
from evals.run import DATASET_DIR, RESULTS_DIR

# 单岗分析取自修复规则筛选后的 v3 评测（每个岗位第 1 次运行的结果）
ANALYSIS_SOURCE = RESULTS_DIR / "eval_20261009_2140.json"


def seed(db: Session) -> None:
    profile = json.loads((DATASET_DIR / "profile.json").read_text(encoding="utf-8"))
    jobs = json.loads((DATASET_DIR / "jobs.json").read_text(encoding="utf-8"))
    ranking = json.loads((DATASET_DIR / "agent_ranking.json").read_text(encoding="utf-8"))
    records = json.loads(ANALYSIS_SOURCE.read_text(encoding="utf-8"))["records"]["v3"]

    db.add(models.Profile(**profile))
    for job in jobs:
        fields = {k: v for k, v in job.items() if k != "job_id"}
        db.add(models.Job(id=job["job_id"], raw_jd="", status="active", **fields))
    for r in records:
        if r["run"] != 0 or not r["ok"]:
            continue
        res = r["result"]
        db.add(models.Analysis(
            job_id=r["job_id"], content_hash="eval-seed",
            match_score=res["match_score"], score_breakdown=res["score_breakdown"],
            matched_skills=res["matched_skills"], missing_skills=res["missing_skills"],
            strengths=res["strengths"], gaps=res["gaps"], action_items=res["action_items"],
            summary=res["summary"],
        ))
    # 新版 search_jobs 依赖检索索引；配置了 embedding 时一并计算向量
    db.flush()
    for job in db.query(models.Job).all():
        index_job(db, job)
    db.add(models.BatchAnalysis(
        status="done", job_count=len(jobs), success_count=len(jobs), ranking=ranking,
        started_at=datetime.utcnow(), finished_at=datetime.utcnow(),
    ))
    db.commit()
