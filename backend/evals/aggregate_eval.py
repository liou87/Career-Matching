"""
读 evals/results/batch_result.json，跑 aggregate_gaps，把所有岗位的
missing_skills 聚合成一份"高频差距排行榜"，打印并存成
evals/results/aggregate_result.json。

不修改 services/graph.py、services/batch_graph.py、routers 或任何现有文件，
只读 batch_eval.py 已经产出的结果文件、调用现成的 aggregate_gaps。

运行（在 backend 目录下，需要先跑过 evals/batch_eval.py 产出输入文件）：
    python evals/aggregate_eval.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.aggregate import aggregate_gaps

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def main():
    in_path = os.path.join(RESULTS_DIR, "batch_result.json")
    with open(in_path, encoding="utf-8") as f:
        batch_results = json.load(f)

    ranking = aggregate_gaps(batch_results)

    print(f"{'技能':<30}{'覆盖岗位数':<10}分类")
    for item in ranking:
        print(f"{item['skill']:<30}{item['job_count']:<10}{item['category']}")

    out_path = os.path.join(RESULTS_DIR, "aggregate_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(ranking, f, ensure_ascii=False, indent=2)

    print(f"\n结果已写入 {out_path}")


if __name__ == "__main__":
    main()
