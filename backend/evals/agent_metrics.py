"""
AI 助手评测的判分与汇总。全部是纯函数、没有导入副作用，单元测试见 tests/test_agent_eval.py。
执行逻辑在 evals/agent_eval.py。
"""
from collections import defaultdict

from app.services.metrics import percentile

WRITE_TOOLS = {"add_to_checklist", "analyze_job", "add_job", "generate_interview_questions", "manage_memory"}


def check_case(case: dict, last: dict, all_turns: list[dict]) -> dict:
    """按题目的预期检查最后一轮。不适用的检查项记为 None。"""
    exp = case["expect"]
    # 工具和参数看所有轮次：多轮对话里前一轮查过的信息，后一轮直接用是合理的
    all_calls = [c for t in all_turns for c in t["tool_calls"]]
    called = [c["name"] for c in all_calls]
    interrupt = last["interrupt"]
    answer = last["answer"].lower()
    checks = {}

    if "tools" in exp:
        checks["tools"] = all(t in called for t in exp["tools"])
    # 有多条等价路径时（如问匹配分，get_job_analysis 和 list_job_scores 都能拿到），任选其一
    if "tools_one_of" in exp:
        checks["tools"] = any(t in called for t in exp["tools_one_of"])
    if exp.get("no_tools"):
        checks["tools"] = not called
    if exp.get("no_write"):
        checks["tools"] = not (set(called) & WRITE_TOOLS)

    def matches(tool, want):
        calls = [c for c in all_calls if c["name"] == tool]
        if interrupt and interrupt["name"] == tool:
            calls.append(interrupt)
        return any(all(c["args"].get(k) == v for k, v in want.items()) for c in calls)

    if "args" in exp:
        checks["args"] = all(matches(tool, want) for tool, want in exp["args"].items())
    # 只在调用了对应工具时才检查参数
    if "args_if_called" in exp:
        applicable = {t: w for t, w in exp["args_if_called"].items() if t in called}
        checks["args"] = all(matches(t, w) for t, w in applicable.items()) if applicable else None

    # 写操作必须停下来等确认；不该写的题目不能出现任何中断
    if "interrupt" in exp:
        checks["confirm"] = bool(interrupt) and interrupt["name"] == exp["interrupt"]
    else:
        checks["confirm"] = interrupt is None

    if "mention" in exp:
        checks["mention"] = all(m.lower() in answer for m in exp["mention"])
    if "mention_any" in exp:
        checks["mention"] = any(m.lower() in answer for m in exp["mention_any"])

    return checks


def summarize(results: list[dict]) -> dict:
    passed = [r for r in results if r["passed"]]
    by_cat = defaultdict(list)
    for r in results:
        by_cat[r["category"]].append(r["passed"])

    def rate(key):
        vals = [r["checks"][key] for r in results if r["checks"].get(key) is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    judged = [r for r in results if r["claims"] is not None]
    grounded = [r for r in judged if all(c["supported"] for c in r["claims"])]
    claims = [c for r in judged for c in r["claims"]]
    latencies = [t["latency_ms"] for r in results for t in r["turns"]]
    costs = [r["cost_usd"] for r in results if r["cost_usd"] is not None]
    write_cases = [r for r in results if "interrupt" in r["expect"]]
    return {
        "cases": len(results),
        "pass_rate": round(len(passed) / len(results), 3),
        "by_category": {k: f"{sum(v)}/{len(v)}" for k, v in by_cat.items()},
        "tool_accuracy": rate("tools"),
        "arg_accuracy": rate("args"),
        "mention_accuracy": rate("mention"),
        "write_confirmed": f"{sum(bool(r['checks'].get('confirm')) for r in write_cases)}/{len(write_cases)}",
        "unexpected_interrupts": sum(
            1 for r in results if "interrupt" not in r["expect"] and r["checks"].get("confirm") is False),
        "grounded_rate": round(len(grounded) / len(judged), 3) if judged else None,
        "unsupported_claims": f"{sum(not c['supported'] for c in claims)}/{len(claims)}",
        "turn_latency_ms_p50": percentile(latencies, 50),
        "turn_latency_ms_p95": percentile(latencies, 95),
        "avg_cost_usd": round(sum(costs) / len(costs), 5) if costs else None,
        "errors": sum(1 for r in results if r["error"]),
    }


def to_markdown(meta: dict, s: dict) -> str:
    rows = [
        ("通过率", s["pass_rate"]),
        ("工具选择准确率", s["tool_accuracy"]),
        ("参数准确率", s["arg_accuracy"]),
        ("必须内容命中率", s["mention_accuracy"]),
        ("写操作先确认", s["write_confirmed"]),
        ("不该中断却中断", s["unexpected_interrupts"]),
        ("回答依据率", s["grounded_rate"]),
        ("无依据说法 / 全部说法", s["unsupported_claims"]),
        ("单轮耗时 P50（ms）", s["turn_latency_ms_p50"]),
        ("单轮耗时 P95（ms）", s["turn_latency_ms_p95"]),
        ("每题成本（美元）", s["avg_cost_usd"]),
        ("执行出错", s["errors"]),
    ]
    lines = [f"评测时间 {meta['date']}，助手 {meta['adapter']}，模型 {meta['model']}，{s['cases']} 道题。", "",
             "| 指标 | 数值 |", "| --- | --- |"]
    lines += [f"| {k} | {'-' if v is None else v} |" for k, v in rows]
    lines += ["", "| 类别 | 通过 |", "| --- | --- |"]
    lines += [f"| {k} | {v} |" for k, v in s["by_category"].items()]
    return "\n".join(lines) + "\n"
