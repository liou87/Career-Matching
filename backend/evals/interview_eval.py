"""
面试题评测：对评测集的 15 个岗位各生成一套面试题，检查题目是否真的从 JD 出发、
覆盖了多少必需技能、有没有通用空话题、答题要点有没有替候选人编造经历。

除编造率外都是规则计算，不依赖裁判：
- JD 依据率：题目摘录的「考察的 JD 要求」能在 JD 原文里找到的比例
- 必需技能覆盖率：JD 必需技能里被至少一道题考到的比例
- 通用题比例：命中「自我介绍」「优缺点」这类短语的题目比例
- 优势和差距兼顾率：同时出了优势题和差距题的岗位比例
- 编造率：裁判（已校验过的编造检测）判断答题要点有没有把画像里没有的经历说成已有

运行（在 backend 目录下）：
    python -m evals.interview_eval
"""
import os
import tempfile
from pathlib import Path

# 必须在 import app 之前设置：在临时评测库里生成，评测流量不进线上指标
_TMP_DB = Path(tempfile.mkdtemp(prefix="careermatch-interview-eval-")) / "interview_eval.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ["RECORD_LLM_CALLS"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

import json  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from datetime import datetime  # noqa: E402

from langchain_core.callbacks import get_usage_metadata_callback  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db import models  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.services import interview  # noqa: E402
from app.services.analysis import profile_to_dict  # noqa: E402
from evals import agent_seed  # noqa: E402
from evals import judge as judge_mod  # noqa: E402
from evals.run import RESULTS_DIR, _sum_usage  # noqa: E402

GENERIC = ["自我介绍", "介绍一下你自己", "优缺点", "职业规划", "为什么选择", "为什么想来", "你的缺点"]
_NON_WORD = re.compile(r"[\s\W_]+", re.UNICODE)
_SPLIT = re.compile(r"[、，,；;/]")


def norm(text: str) -> str:
    return _NON_WORD.sub("", (text or "").lower())


def jd_text(job: models.Job) -> str:
    return norm(" ".join((job.required_skills or []) + (job.preferred_skills or []) + (job.responsibilities or [])
                         + [job.title or "", job.experience_required or "", job.education_required or ""]))


def grounded(requirement: str, jd: str) -> bool:
    """整句能在 JD 里找到，或者按顿号、斜杠拆开后每一段都能找到（模型常把两项要求合在一起摘录）。"""
    if norm(requirement) and norm(requirement) in jd:
        return True
    parts = [norm(p) for p in _SPLIT.split(requirement) if norm(p)]
    return bool(parts) and all(p in jd for p in parts)


def coverage(job: models.Job, questions: list[dict]) -> float | None:
    required = [norm(s) for s in job.required_skills or [] if norm(s)]
    if not required:
        return None
    reqs = [norm(q["jd_requirement"]) for q in questions]
    return sum(any(r in q or q in r for q in reqs if q) for r in required) / len(required)


def run_one(job_id: int) -> dict:
    start = time.perf_counter()
    with get_usage_metadata_callback() as cb, SessionLocal() as db:
        try:
            record, error = interview.generate(db, job_id, force=True), None
            questions = record.questions
        except Exception as e:  # noqa: BLE001
            questions, error = [], f"{type(e).__name__}: {e}"
        job = db.get(models.Job, job_id)
        jd = jd_text(job)
        cov = coverage(job, questions)
    _, cost = _sum_usage(cb.usage_metadata)
    return {
        "job_id": job_id, "error": error, "questions": questions, "cost_usd": cost,
        "latency_ms": round((time.perf_counter() - start) * 1000),
        "grounded": [grounded(q["jd_requirement"], jd) for q in questions],
        "coverage": cov,
        "generic": [any(g in q["question"] for g in GENERIC) for q in questions],
        "relations": [q["relation"] for q in questions],
    }


def main():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        agent_seed.seed(db)
        job_ids = [j.id for j in db.query(models.Job).order_by(models.Job.id)]
        profile = profile_to_dict(db.query(models.Profile).first())
    print(f"面试题评测：{len(job_ids)} 个岗位，模型 {settings.model_interview}")

    with ThreadPoolExecutor(5) as pool:
        results = list(pool.map(run_one, job_ids))

    def judge_points(r):
        items = [{"item": p} for q in r["questions"] for p in q["answer_points"]]
        try:
            return judge_mod.judge(profile, {"action_items": items, "gaps": []}) if items else []
        except Exception:  # noqa: BLE001
            return None

    with ThreadPoolExecutor(5) as pool:
        verdicts = list(pool.map(judge_points, results))
    for r, v in zip(results, verdicts):
        r["fabrication"] = v

    ok = [r for r in results if not r["error"]]
    qs = [g for r in ok for g in r["grounded"]]
    covs = [r["coverage"] for r in ok if r["coverage"] is not None]
    judged = [v for r in ok if r["fabrication"] for v in r["fabrication"]]
    summary = {
        "jobs": len(results), "failed": len(results) - len(ok),
        "questions": len(qs),
        "avg_questions": round(len(qs) / len(ok), 1) if ok else None,
        "jd_grounded_rate": round(sum(qs) / len(qs), 3) if qs else None,
        "required_coverage": round(sum(covs) / len(covs), 3) if covs else None,
        "generic_rate": round(sum(g for r in ok for g in r["generic"]) / len(qs), 3) if qs else None,
        "both_strength_and_gap": round(sum({"strength", "gap"} <= set(r["relations"]) for r in ok) / len(ok), 3)
        if ok else None,
        "answer_points_judged": len(judged),
        "fabrication_rate": round(sum(v["fabricated"] for v in judged) / len(judged), 3) if judged else None,
        "avg_cost_usd": round(sum(r["cost_usd"] for r in ok if r["cost_usd"]) / len(ok), 5) if ok else None,
        "latency_ms_p50": sorted(r["latency_ms"] for r in ok)[len(ok) // 2] if ok else None,
    }

    meta = {"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "model": settings.model_interview,
            "judge": settings.model_judge}
    RESULTS_DIR.mkdir(exist_ok=True)
    stem = RESULTS_DIR / f"interview_eval_{datetime.now():%Y%m%d_%H%M}"
    stem.with_suffix(".json").write_text(
        json.dumps({"meta": meta, "summary": summary, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    labels = [("岗位数 / 失败", f"{summary['jobs']} / {summary['failed']}"),
              ("平均每岗位题数", summary["avg_questions"]),
              ("JD 依据率", summary["jd_grounded_rate"]),
              ("必需技能覆盖率", summary["required_coverage"]),
              ("通用题比例", summary["generic_rate"]),
              ("优势和差距兼顾率", summary["both_strength_and_gap"]),
              ("答题要点编造率", f"{summary['fabrication_rate']}（{summary['answer_points_judged']} 条）"),
              ("每岗位成本（美元）", summary["avg_cost_usd"]),
              ("耗时 P50（ms）", summary["latency_ms_p50"])]
    report = "\n".join([f"评测时间 {meta['date']}，模型 {meta['model']}。", "", "| 指标 | 数值 |", "| --- | --- |",
                        *[f"| {k} | {v} |" for k, v in labels]]) + "\n"
    stem.with_suffix(".md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"原始记录：{stem.with_suffix('.json')}")


if __name__ == "__main__":
    main()
