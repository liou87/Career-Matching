"""
统一的离线评测入口：在固定评测集上跑匹配分析的各个版本，输出可对比的指标。

运行（在 backend 目录下）：
    python -m evals.run                                   # v1/v2/v3 各跑 3 遍，带编造检测
    python -m evals.run --versions v3 --runs 1 --jobs 3 --no-judge   # 快速冒烟
    python -m evals.run --langsmith                       # 同时作为实验上传到 LangSmith

结果写到 evals/results/eval_<时间>.json（全部原始记录）和同名 .md（汇总表）。
指标定义见 docs/evals.md。
"""
import os
import sys

# 必须在 import app 之前设置：评测流量不写进线上指标表；
# 不上传 LangSmith 时关掉追踪，免得几百条评测 trace 混进线上项目
os.environ["RECORD_LLM_CALLS"] = "false"
if "--langsmith" not in sys.argv:
    os.environ["LANGSMITH_TRACING"] = "false"

import argparse  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402
from collections import Counter  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402

from langchain_core.callbacks import get_usage_metadata_callback  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.graphs.match import analyze_match_v3  # noqa: E402
from app.llm.legacy import analyze_match_v1, analyze_match_v2  # noqa: E402
from app.services.metrics import estimate_cost  # noqa: E402
from evals import judge as judge_mod  # noqa: E402
from evals.metrics import generic_action_count, score_mismatch, summarize_version  # noqa: E402

EVALS_DIR = Path(__file__).resolve().parent
DATASET_DIR = EVALS_DIR / "dataset"
RESULTS_DIR = EVALS_DIR / "results"

VERSIONS = {"v1": analyze_match_v1, "v2": analyze_match_v2, "v3": analyze_match_v3}


def parse_args():
    p = argparse.ArgumentParser(description="CareerMatch 匹配分析离线评测")
    p.add_argument("--versions", nargs="+", default=list(VERSIONS), choices=list(VERSIONS))
    p.add_argument("--runs", type=int, default=3, help="每个岗位跑几遍，用于衡量稳定性")
    p.add_argument("--jobs", type=int, default=None, help="只取前 N 个岗位，快速冒烟用")
    p.add_argument("--concurrency", type=int, default=5)
    p.add_argument("--no-judge", action="store_true", help="跳过编造检测（省掉裁判模型的调用）")
    p.add_argument("--langsmith", action="store_true", help="作为实验上传到 LangSmith")
    p.add_argument("--profile-from-db", action="store_true",
                   help="用本地库里的真实画像代替脱敏画像（结果含个人信息，不要提交）")
    return p.parse_args()


# ---------- 数据 ----------

def load_dataset(limit: int | None, profile_from_db: bool):
    jobs = _all_jobs()[:limit]
    if profile_from_db:
        from app.api.analysis import _profile_to_dict
        from app.db import models
        from app.db.session import SessionLocal

        with SessionLocal() as db:
            profile = _profile_to_dict(db.query(models.Profile).first())
    else:
        profile = json.loads((DATASET_DIR / "profile.json").read_text(encoding="utf-8"))
    labels_path = DATASET_DIR / "labels.json"
    all_labels = json.loads(labels_path.read_text(encoding="utf-8")) if labels_path.exists() else []
    # 只用人工校对过的标注，草稿不参与计算
    labels = {lab["job_id"]: lab for lab in all_labels if lab.get("reviewed")}
    return jobs, profile, labels


# ---------- 执行 ----------

def make_target(fn, profile: dict):
    """把一个分析版本包装成「输入一个岗位、输出一条评测记录」的函数，失败不抛异常。"""

    def target(inputs: dict) -> dict:
        start = time.perf_counter()
        with get_usage_metadata_callback() as cb:
            try:
                result, error = fn(profile, inputs["job"]), None
            except Exception as e:  # noqa: BLE001  评测要记录失败而不是中断
                result, error = None, f"{type(e).__name__}: {e}"
        usage, cost = _sum_usage(cb.usage_metadata)
        return {
            "job_id": inputs["job_id"],
            "ok": error is None,
            "error": error,
            "latency_ms": round((time.perf_counter() - start) * 1000),
            "usage": usage,
            "cost_usd": cost,
            "result": result,
        }

    return target


def _sum_usage(by_model: dict) -> tuple[dict, float | None]:
    usage = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
    cost = 0.0
    for model, u in by_model.items():
        cached = (u.get("input_token_details") or {}).get("cache_read") or 0
        usage["input_tokens"] += u.get("input_tokens", 0)
        usage["cached_input_tokens"] += cached
        usage["output_tokens"] += u.get("output_tokens", 0)
        c = estimate_cost(model, u.get("input_tokens"), cached, u.get("output_tokens"))
        cost = None if c is None or cost is None else cost + c
    return usage, (round(cost, 6) if cost is not None else None)


def run_local(target, jobs, runs, concurrency) -> list[dict]:
    tasks = [(job, i) for i in range(runs) for job in jobs]

    def one(task):
        job, run = task
        return {**target({"job_id": job["job_id"], "job": _job_input(job)}), "run": run}

    with ThreadPoolExecutor(concurrency) as pool:
        return list(pool.map(one, tasks))


def run_langsmith(version, target, jobs, runs, concurrency) -> list[dict]:
    """用 LangSmith evaluate 执行，同一份记录同时上传成实验，可在界面里对比各版本。"""
    from langsmith import Client, evaluate

    client = Client()
    name = "careermatch-jobs"
    if client.has_dataset(dataset_name=name):
        ds = client.read_dataset(dataset_name=name)
    else:
        ds = client.create_dataset(name, description="CareerMatch 匹配分析固定评测集")
    # 按岗位 id 同步：评测集新增了岗位就补上，用 --jobs 跑子集时也不会把数据集建残
    existing = {ex.inputs["job_id"] for ex in client.list_examples(dataset_id=ds.id)}
    missing = [j for j in _all_jobs() if j["job_id"] not in existing]
    if missing:
        client.create_examples(
            dataset_id=ds.id,
            inputs=[{"job_id": j["job_id"], "job": _job_input(j)} for j in missing],
        )
    wanted = {j["job_id"] for j in jobs}
    examples = [ex for ex in client.list_examples(dataset_id=ds.id) if ex.inputs["job_id"] in wanted]

    def generic_actions(outputs: dict) -> dict:
        return {"key": "generic_actions",
                "score": generic_action_count(outputs["result"]) if outputs["ok"] else None}

    def score_mismatched(outputs: dict) -> dict:
        return {"key": "score_mismatch",
                "score": int(score_mismatch(outputs["result"])) if outputs["ok"] else None}

    results = evaluate(
        target,
        data=examples,
        evaluators=[generic_actions, score_mismatched],
        experiment_prefix=f"careermatch-{version}",
        num_repetitions=runs,
        max_concurrency=concurrency,
        metadata={"version": version, "model": settings.model_analysis},
    )
    seen = Counter()
    records = []
    for row in results:
        out = row["run"].outputs
        records.append({**out, "run": seen[out["job_id"]]})
        seen[out["job_id"]] += 1
    return records


def _all_jobs() -> list[dict]:
    return json.loads((DATASET_DIR / "jobs.json").read_text(encoding="utf-8"))


def _job_input(job: dict) -> dict:
    return {k: v for k, v in job.items() if k != "job_id"}


# ---------- 编造检测 ----------

def run_judge(profile, records, concurrency) -> tuple[list[dict], int]:
    """每个岗位只检查第一次成功的结果，控制裁判模型的调用量。"""
    first_ok = {}
    for r in sorted(records, key=lambda r: r["run"]):
        if r["ok"] and r["job_id"] not in first_ok:
            first_ok[r["job_id"]] = r

    def one(r):
        try:
            return [{**v, "job_id": r["job_id"]} for v in judge_mod.judge(profile, r["result"])], 0
        except Exception:  # noqa: BLE001
            return [], 1

    with ThreadPoolExecutor(concurrency) as pool:
        outs = list(pool.map(one, first_ok.values()))
    return [v for verdicts, _ in outs for v in verdicts], sum(err for _, err in outs)


# ---------- 报告 ----------

ROWS = [
    ("成功率", "success_rate"),
    ("耗时 P50（ms）", "latency_ms_p50"),
    ("耗时 P95（ms）", "latency_ms_p95"),
    ("平均输入 token", "avg_input_tokens"),
    ("平均输出 token", "avg_output_tokens"),
    ("单次成本（美元）", "avg_cost_usd"),
    ("分数算错次数", "score_mismatch"),
    ("空泛建议 / 建议总数", None),
    ("分数标准差（同岗位多次）", "stability.mean_std"),
    ("分数最大极差", "stability.max_range"),
    ("多次分数完全一致的岗位比例", "stability.identical_ratio"),
    ("差距识别准确率", "gap_precision"),
    ("差距识别召回率", "gap_recall"),
    ("编造率", "fabrication_rate"),
]


def to_markdown(meta: dict, summary: dict) -> str:
    versions = list(summary)
    lines = [
        f"评测时间 {meta['date']}，模型 {meta['models']['analysis']}，"
        f"{meta['jobs']} 个岗位 × {meta['runs']} 次，人工标注岗位 {meta['labeled_jobs']} 个。",
        "",
        "| 指标 | " + " | ".join(versions) + " |",
        "| --- | " + " | ".join("---" for _ in versions) + " |",
    ]
    for title, key in ROWS:
        cells = []
        for v in versions:
            s = summary[v]
            if key is None:
                cells.append(f"{s['generic_actions']} / {s['action_items']}")
            else:
                val = s
                for part in key.split("."):
                    val = val.get(part) if isinstance(val, dict) else None
                cells.append("-" if val is None else str(val))
        lines.append(f"| {title} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main():
    args = parse_args()
    jobs, profile, labels = load_dataset(args.jobs, args.profile_from_db)
    print(f"评测集：{len(jobs)} 个岗位，人工标注 {len(labels)} 个，版本 {args.versions}，每岗位 {args.runs} 次")

    all_records, all_verdicts, summary = {}, {}, {}
    for version in args.versions:
        target = make_target(VERSIONS[version], profile)
        start = time.time()
        if args.langsmith:
            records = run_langsmith(version, target, jobs, args.runs, args.concurrency)
        else:
            records = run_local(target, jobs, args.runs, args.concurrency)
        verdicts, judge_errors = ([], 0) if args.no_judge else run_judge(profile, records, args.concurrency)
        all_records[version], all_verdicts[version] = records, verdicts
        summary[version] = {**summarize_version(records, labels, verdicts), "judge_errors": judge_errors}
        failed = sum(not r["ok"] for r in records)
        print(f"  {version}: {len(records)} 次，失败 {failed}，用时 {time.time() - start:.0f}s")

    meta = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "models": {role: getattr(settings, f"model_{role}") for role in ("analysis", "suggest", "judge")},
        "versions": args.versions,
        "runs": args.runs,
        "jobs": len(jobs),
        "labeled_jobs": len(labels),
        "profile": "db" if args.profile_from_db else "dataset/profile.json",
        "langsmith": args.langsmith,
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    stem = RESULTS_DIR / f"eval_{datetime.now():%Y%m%d_%H%M}"
    stem.with_suffix(".json").write_text(
        json.dumps({"meta": meta, "summary": summary, "records": all_records, "verdicts": all_verdicts},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report = to_markdown(meta, summary)
    stem.with_suffix(".md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"原始记录：{stem.with_suffix('.json')}")


if __name__ == "__main__":
    main()
