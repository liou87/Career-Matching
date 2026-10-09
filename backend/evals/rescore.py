"""
对已有的评测结果重新计算指标，不重跑分析本身（在 backend 目录下运行）：

    python -m evals.rescore evals/results/eval_<时间>.json            # 只用最新标注重算，不调 LLM
    python -m evals.rescore evals/results/eval_<时间>.json --judge    # 另外重跑裁判（编造、差距检查）

会原地更新该 JSON 的 summary 和同名 .md 汇总表。
"""
import argparse
import json
from pathlib import Path

from evals.metrics import summarize_version
from evals.run import _all_jobs, load_dataset, run_judge, to_markdown


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("path", type=Path)
    p.add_argument("--judge", action="store_true", help="重跑裁判模型（只产生裁判的费用）")
    p.add_argument("--concurrency", type=int, default=5)
    args = p.parse_args()

    data = json.loads(args.path.read_text(encoding="utf-8"))
    _, profile, labels = load_dataset(None, profile_from_db=data["meta"]["profile"] == "db")
    jobs_by_id = {j["job_id"]: j for j in _all_jobs()}
    data.setdefault("gap_verdicts", {})

    for version, records in data["records"].items():
        if args.judge:
            verdicts, gap_verdicts, errors = run_judge(profile, jobs_by_id, records, args.concurrency)
            data["verdicts"][version], data["gap_verdicts"][version] = verdicts, gap_verdicts
            print(f"  {version}: 裁判完成，失败 {errors}")
        else:
            errors = data["summary"][version].get("judge_errors", 0)
        data["summary"][version] = {
            **summarize_version(records, labels, data["verdicts"][version], data["gap_verdicts"].get(version, [])),
            "judge_errors": errors,
        }
    data["meta"]["labeled_jobs"] = len(labels)

    args.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    report = to_markdown(data["meta"], data["summary"])
    args.path.with_suffix(".md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
