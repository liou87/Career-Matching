"""
基线测试：对 jobs 表里所有 status='active' 的岗位跑一遍 analyze_match_v1，
检验 AI 直接返回的 match_score 是否等于用 score_breakdown 四个子分按权重
（skills*0.4 + experience*0.3 + education*0.15 + other*0.15）算出来的 expected_score。

不修改任何现有代码，只读数据库、调用现成的 analyze_match_v1。

运行（在 backend 目录下）：
    python evals/baseline_eval.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import models
from services.ai_service import analyze_match_v1 as analyze_match

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


def expected_score(breakdown: dict) -> int:
    return round(
        breakdown["skills"] * 0.4
        + breakdown["experience"] * 0.3
        + breakdown["education"] * 0.15
        + breakdown["other"] * 0.15
    )


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
        job_data = [(job.id, job.title, _job_to_dict(job)) for job in jobs]
    finally:
        db.close()

    records = []
    mismatch_count = 0

    for job_id, title, job_dict in job_data:
        try:
            result = analyze_match(profile, job_dict)
        except Exception as e:
            print(f"[job {job_id}] {title} -> ERROR: {e}")
            records.append({"job_id": job_id, "title": title, "error": str(e)})
            continue

        breakdown = result.get("score_breakdown") or {}
        match_score = result.get("match_score")
        exp_score = expected_score(breakdown) if breakdown else None
        mismatch = exp_score is not None and exp_score != match_score
        if mismatch:
            mismatch_count += 1

        flag = "MISMATCH" if mismatch else "ok"
        print(f"[job {job_id}] {title} -> match_score={match_score} expected={exp_score} [{flag}]")

        records.append({
            "job_id": job_id,
            "title": title,
            "match_score": match_score,
            "expected_score": exp_score,
            "mismatch": mismatch,
            "score_breakdown": breakdown,
            "gaps": result.get("gaps", []),
            "action_items": result.get("action_items", []),
        })

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "baseline_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    total = len(job_data)
    print(f"\n结果已写入 {out_path}")
    print(f"算错比例: {mismatch_count}/{total}")


if __name__ == "__main__":
    main()
