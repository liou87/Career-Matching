"""
裁判校验集：裁判本身也需要被评测。每次修改裁判 prompt 或换裁判模型后先跑一遍，
准确率不够就不要相信它给出的评测数字。

样本覆盖已经发现过的误判类型，大部分用的是真实 JD 里的原话：
加分项被当成凭空差距、职责里的要求被忽略、比 JD 更细的说法、多选一已满足；
以及 AI 助手回答里编造的分数和岗位。

运行（在 backend 目录下，约 6 次裁判调用）：
    python -m evals.calibrate_judges
"""
import os

os.environ["RECORD_LLM_CALLS"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

import json  # noqa: E402

from evals.agent_judge import judge_grounding  # noqa: E402
from evals.judge import judge, judge_gaps  # noqa: E402
from evals.run import DATASET_DIR  # noqa: E402

GAP_CASES = [
    (
        {
            "title": "Agent 开发工程师",
            "required_skills": ["Python", "RAG", "LangGraph"],
            "preferred_skills": ["向量数据库", "Text2SQL", "Harness Engineering"],
            "responsibilities": ["基于大模型构建 Agent 应用", "构建hybrid search(向量+BM25)检索管线"],
        },
        [
            ("缺少 RAG 项目经验", "valid"),
            ("缺少 Kafka 消息队列经验", "not_required"),
            ("不会 Python", "already_has"),
            ("向量数据库使用经验", "valid"),            # 加分项
            ("Text2SQL", "valid"),                      # 加分项，曾被误判
            ("Harness Engineering", "valid"),           # 加分项，曾被误判
            ("向量数据库 / Embedding 检索", "valid"),   # 写在职责里，曾被误判
            ("缺少 LangGraph 经验", "already_has"),
            ("云原生/容器化部署（Docker、K8s）", "not_required"),
        ],
    ),
    (
        {
            "title": "AI 应用开发工程师",
            "required_skills": ["至少一种编程语言（如Java、Python等）", "大语言模型基本原理"],
            "preferred_skills": [],
            "responsibilities": ["负责 AI 应用的后端开发"],
        },
        [
            ("Java", "already_has"),                                  # 多选一，画像已有 Python
            ("大语言模型训练/微调机制的系统性背景", "valid"),         # 比 JD 更细，曾被误判
            ("大规模分布式与高并发生产系统经验", "not_required"),
        ],
    ),
]

FABRICATION_CASES = [
    ({"item": "基于你在字节跳动实习时搭建 Kafka 集群的经验，把批量分析改成消息队列驱动"}, True),
    ({"item": "在 CareerMatch 的 LangGraph 状态图里加自检节点，并给出编造率前后对比"}, False),
    ({"item": "学习 Kubernetes 并把 CareerMatch 部署到 K8s 上"}, False),
]


GROUNDING_TOOL_OUTPUT = '工具 get_job_analysis 返回：{"match_score": 73, "gaps": [{"gap": "缺少 RAG 项目经验"}]}'

# (助手回答, 期望：回答里每条说法都有依据)
GROUNDING_CASES = [
    ("你和快手这个岗位的匹配分是 73 分，主要差距是缺少 RAG 项目经验。", True),
    ("你和快手这个岗位的匹配分是 85 分。", False),                            # 编造的分数
    ("匹配分 73 分。另外岗位库里还有一个阿里的 Agent 岗位很适合你。", False),  # 编造的岗位
    ("快手这个岗位的主要差距只有 RAG 一项，没有其他差距。", True),             # 「没有某项」的说法
    ("你问的是快手的岗位，匹配分 73 分。", True),                             # 复述用户的问题
    ("我只能读取数据、没有写入权限。匹配分 73 分，属于中等偏上。", True),     # 能力描述和主观评价不算
]


def main():
    profile = json.loads((DATASET_DIR / "profile.json").read_text(encoding="utf-8"))

    gap_total = gap_ok = 0
    for job, cases in GAP_CASES:
        verdicts = judge_gaps(profile, job, {"missing_skills": [text for text, _ in cases]})
        for (text, expected), v in zip(cases, verdicts):
            ok = v["category"] == expected
            gap_total, gap_ok = gap_total + 1, gap_ok + ok
            note = "（一致性约束纠正）" if v.get("corrected") else ""
            print(f"{'OK ' if ok else '错 '} 差距  {text[:24]:24s} 期望 {expected:12s} 实际 {v['category']}{note}")

    fab = judge(profile, {"action_items": [item for item, _ in FABRICATION_CASES], "gaps": []})
    fab_ok = 0
    for (item, expected), v in zip(FABRICATION_CASES, fab):
        ok = v["fabricated"] == expected
        fab_ok += ok
        print(f"{'OK ' if ok else '错 '} 编造  {item['item'][:24]:24s} 期望 {expected!s:12s} 实际 {v['fabricated']}")

    ground_ok = 0
    for answer, expected in GROUNDING_CASES:
        claims = judge_grounding("我和快手的岗位匹配分多少？", [GROUNDING_TOOL_OUTPUT], answer)
        ok = all(c["supported"] for c in claims) == expected
        ground_ok += ok
        print(f"{'OK ' if ok else '错 '} 依据  {answer[:24]:24s} 期望 {expected!s:12s} "
              f"实际 {[c['supported'] for c in claims]}")

    print(f"\n差距检查 {gap_ok}/{gap_total}，编造检测 {fab_ok}/{len(FABRICATION_CASES)}，"
          f"回答依据 {ground_ok}/{len(GROUNDING_CASES)}")


if __name__ == "__main__":
    main()
