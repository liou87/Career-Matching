"""
对比测试：结构跟 evals/two_stage_eval.py 完全一致（同样的画像来源、同样的
_job_to_dict、同样的岗位查询、同样的统计口径），唯一区别是调用
services.graph 里的 analyze_match_v3（LangGraph StateGraph 版本：同样是
节点1客观打分识别差距 -> 节点2基于候选人已有项目生成建议，只是编排方式从
两条链的顺序调用换成了显式的状态图节点）。

直接从 services.graph 导入 analyze_match_v3（线上真实逻辑），不修改
ai_service.py、routers 或任何现有文件。

不修改任何现有代码，只读数据库、调用现成的 analyze_match_v3。

运行（在 backend 目录下）：
    python evals/graph_eval.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import models
from services.graph import analyze_match_v3

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

# item 字段命中这些短语，视为"通用建议"（跟 SUGGESTION_PROMPT 明确要求禁止的措辞对应）
GENERIC_PHRASES = ["系统学习", "学习LangChain", "争取实习", "开源到GitHub", "刷LeetCode"]


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
    # 跟 analyze_match_v3 自己算 match_score 用的是同一种四舍五入
    # （int(exact + 0.5)，不是内置 round() 的银行家舍入），保持一致，
    # 否则会因为舍入规则不同而产生"假的"不一致。
    exact = (
        breakdown["skills"] * 0.4
        + breakdown["experience"] * 0.3
        + breakdown["education"] * 0.15
        + breakdown["other"] * 0.15
    )
    return int(exact + 0.5)


def is_generic(item_text: str) -> bool:
    return any(phrase in item_text for phrase in GENERIC_PHRASES)


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
    total_action_items = 0
    generic_action_items = 0
    ok_count = 0

    for job_id, title, job_dict in job_data:
        try:
            result = analyze_match_v3(profile, job_dict)
        except Exception as e:
            print(f"[job {job_id}] {title} -> ERROR: {e}")
            records.append({"job_id": job_id, "title": title, "error": str(e)})
            continue

        ok_count += 1
        breakdown = result.get("score_breakdown") or {}
        match_score = result.get("match_score")
        exp_score = expected_score(breakdown) if breakdown else None
        mismatch = exp_score is not None and exp_score != match_score
        if mismatch:
            mismatch_count += 1

        action_items = result.get("action_items", [])
        total_action_items += len(action_items)
        generic_here = [a for a in action_items if is_generic(a.get("item", ""))]
        generic_action_items += len(generic_here)

        flag = "MISMATCH" if mismatch else "ok"
        print(f"[job {job_id}] {title} -> match_score={match_score} expected={exp_score} [{flag}] "
              f"action_items={len(action_items)} generic={len(generic_here)}")

        records.append({
            "job_id": job_id,
            "title": title,
            "match_score": match_score,
            "expected_score": exp_score,
            "mismatch": mismatch,
            "score_breakdown": breakdown,
            "gaps": result.get("gaps", []),
            "action_items": action_items,
        })

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "graph_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    total = len(job_data)
    avg_action_items = total_action_items / ok_count if ok_count else 0

    print(f"\n结果已写入 {out_path}")
    print(f"1. match_score 与精确加权值不一致: {mismatch_count}/{ok_count}")
    print(f"2. action_items 总条数: {total_action_items}，平均条数: {avg_action_items:.2f}（基于 {ok_count} 条成功结果）")
    print(f"3. action_items 命中通用建议短语({'/'.join(GENERIC_PHRASES)})的条数: {generic_action_items}/{total_action_items}")


if __name__ == "__main__":
    main()
