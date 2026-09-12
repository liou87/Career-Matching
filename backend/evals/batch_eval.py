"""
批量并发测试：把 evals/graph_eval.py 里逐条串行调用 analyze_match_v3 的方式，
换成 services/batch_graph.py 里基于 Send API 的并发批处理（analyze_all），
测一下并发跑全部岗位相比串行能快多少、失败率有没有变化。

复用其他 evals 脚本里同样的 load_profile / _job_to_dict 逻辑（跟
baseline_eval.py、two_stage_eval.py、graph_eval.py 保持同一套约定，
本文件内自成一份，不跨文件 import，理由跟那几个文件一样——
每个 eval 脚本独立可运行，不互相依赖）。

不修改 services/graph.py、services/batch_graph.py、services/ai_service.py、
routers 或任何现有文件，只读数据库、调用现成的 analyze_all。

运行（在 backend 目录下）：
    python evals/batch_eval.py
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import models
from services.batch_graph import analyze_all

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

# 数据库里读不到真实画像时用的脱敏兜底数据（学校/公司名均为占位符）
FALLBACK_PROFILE = {
    "name": "示例候选人",
    "education": [
        {"degree": "硕士", "school": "某大学", "major": "计算机科学", "year": "2026年"},
    ],
    "skills": ["Python", "FastAPI", "React", "SQL"],
    "experiences": [
        {"title": "后端实习生", "company": "某科技公司", "duration": "2023.06-2023.09", "description": "参与后端接口开发"},
    ],
    "projects": [
        {"name": "示例项目", "description": "全栈求职分析工具", "tech_stack": ["React", "FastAPI"]},
    ],
    "target_roles": ["后端工程师"],
    "target_cities": ["上海"],
    "target_companies": ["互联网公司"],
}


def load_profile() -> dict:
    db = SessionLocal()
    try:
        profile = db.query(models.Profile).first()
    finally:
        db.close()

    if profile is None:
        return FALLBACK_PROFILE

    return {
        "name": profile.name,
        "education": profile.education,
        "skills": profile.skills,
        "experiences": profile.experiences,
        "projects": profile.projects,
        "target_roles": profile.target_roles,
        "target_cities": profile.target_cities,
        "target_companies": profile.target_companies,
    }


def _job_to_dict(job: models.Job) -> dict:
    # 跟 routers/analysis.py 里 _job_to_dict 的字段完全一致
    return {
        "title": job.title,
        "company": job.company,
        "city": job.city,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "required_skills": job.required_skills,
        "preferred_skills": job.preferred_skills,
        "experience_required": job.experience_required,
        "education_required": job.education_required,
        "responsibilities": job.responsibilities,
    }


def main():
    profile = load_profile()

    db = SessionLocal()
    try:
        jobs = (
            db.query(models.Job)
            .filter(models.Job.status == "active")
            .order_by(models.Job.id)
            .all()
        )
        # job_id 只用来认领结果归属，不混进 job dict（那会被 json.dumps 进 prompt，
        # 既是噪音又跟 graph_eval.py 的输入不一致）
        job_dicts = [{"job_id": job.id, "job": _job_to_dict(job)} for job in jobs]
    finally:
        db.close()

    start = time.time()
    results = analyze_all(profile, job_dicts, max_concurrency=5)
    elapsed = time.time() - start

    ok = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]

    for r in sorted(results, key=lambda r: r.get("job_id") or 0):
        if "error" in r:
            print(f"[job {r.get('job_id')}] ERROR: {r['error']}")
        else:
            print(f"[job {r.get('job_id')}] match_score={r.get('match_score')}")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "batch_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n结果已写入 {out_path}")
    print(f"总耗时: {elapsed:.1f}s")
    print(f"成功: {len(ok)}/{len(results)}, 失败: {len(failed)}/{len(results)}")


if __name__ == "__main__":
    main()
