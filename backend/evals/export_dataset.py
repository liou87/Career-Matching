"""
从本地数据库导出固定评测集到 evals/dataset/：

- jobs.json：所有 active 岗位的结构化字段（与线上分析时传给模型的字段一致）
- profile.json：脱敏后的画像。仓库是公开的，姓名、学校、公司名替换成占位符，
  技能、项目、学历层次和求职意向保留，保证评测输入接近真实使用
- labels.json：差距标注草稿，只在文件不存在时生成，不会覆盖已经人工校对过的标注

运行（在 backend 目录下）：
    python -m evals.export_dataset
"""
import json
from pathlib import Path

from app.api.analysis import _job_to_dict, _profile_to_dict
from app.db import models
from app.db.session import SessionLocal

DATASET_DIR = Path(__file__).resolve().parent / "dataset"


def sanitize_profile(profile: dict) -> dict:
    return {
        **profile,
        "name": "候选人",
        "education": [{**e, "school": "某高校"} for e in profile.get("education") or []],
        "experiences": [{**e, "company": "某科技公司"} for e in profile.get("experiences") or []],
    }


def draft_labels(jobs: list[dict], profile: dict) -> list[dict]:
    """用规则给出「JD 必需技能里画像没覆盖的」作为标注起点，需要人工校对。

    规则很粗（字符串互相包含就算覆盖），比如 "LLM API (如OpenAI…)" 和画像里的
    "DeepSeek API" 会被误判为缺失，所以 reviewed 默认是 false，校对后再改成 true。
    """
    have = [s.lower() for s in profile.get("skills") or []]

    def covered(skill: str) -> bool:
        s = skill.lower()
        return any(s in h or h in s for h in have)

    return [
        {
            "job_id": job["job_id"],
            "title": job["title"],
            "reviewed": False,
            "jd_required": job.get("required_skills") or [],
            "jd_preferred": job.get("preferred_skills") or [],
            # 每条标注：skill 是标准名，aliases 是模型可能用到的说法，命中任意一个就算识别到
            "missing": [
                {"skill": s, "aliases": [s]} for s in job.get("required_skills") or [] if not covered(s)
            ],
        }
        for job in jobs
    ]


def main():
    db = SessionLocal()
    try:
        profile = db.query(models.Profile).first()
        jobs = db.query(models.Job).filter(models.Job.status == "active").order_by(models.Job.id).all()
        if not profile or not jobs:
            raise SystemExit("本地库里没有画像或岗位，无法导出")
        profile_dict = sanitize_profile(_profile_to_dict(profile))
        job_dicts = [{"job_id": j.id, **_job_to_dict(j)} for j in jobs]
    finally:
        db.close()

    DATASET_DIR.mkdir(exist_ok=True)
    _write(DATASET_DIR / "jobs.json", job_dicts)
    _write(DATASET_DIR / "profile.json", profile_dict)
    print(f"导出 {len(job_dicts)} 个岗位和脱敏画像")

    labels_path = DATASET_DIR / "labels.json"
    if labels_path.exists():
        print("labels.json 已存在，保留人工标注，不覆盖")
    else:
        _write(labels_path, draft_labels(job_dicts, profile_dict))
        print("已生成 labels.json 草稿，人工校对后把 reviewed 改成 true")


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
