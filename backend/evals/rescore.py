"""
用最新的人工标注重新计算一份评测结果的指标，不重新调用 LLM、不产生费用。
校对完 evals/dataset/labels.json 后运行（在 backend 目录下）：

    python -m evals.rescore evals/results/eval_<时间>.json

会原地更新该 JSON 的 summary 和同名 .md 汇总表。
"""
import json
import sys
from pathlib import Path

from evals.metrics import summarize_version
from evals.run import DATASET_DIR, to_markdown


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    path = Path(sys.argv[1])
    data = json.loads(path.read_text(encoding="utf-8"))

    all_labels = json.loads((DATASET_DIR / "labels.json").read_text(encoding="utf-8"))
    labels = {lab["job_id"]: lab for lab in all_labels if lab.get("reviewed")}

    for version, records in data["records"].items():
        judge_errors = data["summary"][version].get("judge_errors", 0)
        data["summary"][version] = {
            **summarize_version(records, labels, data["verdicts"][version]),
            "judge_errors": judge_errors,
        }
    data["meta"]["labeled_jobs"] = len(labels)

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    report = to_markdown(data["meta"], data["summary"])
    path.with_suffix(".md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
