"""
AI 助手评测：35 道题（30 单轮 + 5 多轮），检查工具选择、参数、写操作是否先确认、
回答里有没有必须出现的内容，再由裁判判断回答是否有依据。

题目见 evals/dataset/agent_cases.json。评测在一个临时数据库里进行，
种子数据由 evals/agent_seed.py 写入，不碰本地真实数据。

运行（在 backend 目录下）：
    python -m evals.agent_eval                 # 全部题目
    python -m evals.agent_eval --cases 5       # 只跑前 5 道，快速冒烟
    python -m evals.agent_eval --no-judge      # 跳过回答依据检查
    python -m evals.agent_eval --rejudge evals/results/agent_eval_<...>.json   # 只重跑裁判
"""
import os
import sys
import tempfile
from pathlib import Path

# 必须在 import app 之前设置：工具读写的是临时评测库，评测流量不进线上指标
_TMP_DB = Path(tempfile.mkdtemp(prefix="careermatch-agent-eval-")) / "agent_eval.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ["RECORD_LLM_CALLS"] = "false"
if "--langsmith" not in sys.argv:
    os.environ["LANGSMITH_TRACING"] = "false"

import argparse  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from datetime import datetime  # noqa: E402

from langchain_core.callbacks import get_usage_metadata_callback  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402
from evals import agent_seed  # noqa: E402
from evals.agent_judge import context_from_turns, judge_grounding  # noqa: E402
from evals.agent_metrics import WRITE_TOOLS, check_case, summarize, to_markdown  # noqa: E402,F401
from evals.run import DATASET_DIR, RESULTS_DIR, _sum_usage  # noqa: E402

# ---------- 适配器：怎样和被测的助手对话 ----------

class AgentSession:
    """当前的助手：对话存在 checkpointer 里，写操作先中断等确认，偏好存在 Store 里。
    评测用内存版本，每道题一个独立的对话，题目给出的偏好预先写进 Store。

    第三阶段之前的无状态助手（基线）在 commit 2174560，结果见
    evals/results/agent_eval_stateless_20261009_2337.json。"""

    def __init__(self, case: dict):
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.store.memory import InMemoryStore

        from app.agent.agent import build_agent
        from app.agent.memory import NAMESPACE

        store = InMemoryStore()
        for i, content in enumerate(case.get("memories", [])):
            store.put(NAMESPACE, f"seed-{i}", {"content": content})
        self.agent = build_agent(InMemorySaver(), store)
        self.config = {"configurable": {"thread_id": case["id"]}}

    def send(self, message: str) -> dict:
        from langchain_core.messages import AIMessage, ToolMessage

        before = len((self.agent.get_state(self.config).values or {}).get("messages", []))
        result = self.agent.invoke({"messages": [("user", message)]}, self.config)
        new = result["messages"][before + 1:]
        answer = next((m.content for m in reversed(new) if isinstance(m, AIMessage) and m.content), "")
        return {
            "answer": answer,
            "tool_calls": [{"name": tc["name"], "args": tc["args"]}
                           for m in new if isinstance(m, AIMessage) for tc in m.tool_calls],
            "tool_outputs": [{"name": m.name, "content": str(m.content)[:3000]}
                             for m in new if isinstance(m, ToolMessage)],
            "interrupt": _interrupt_of(result),
        }


def _interrupt_of(result: dict) -> dict | None:
    """从 agent 返回里取出等待确认的操作（HumanInTheLoopMiddleware 的中断）。"""
    interrupts = result.get("__interrupt__") or []
    for it in interrupts:
        for req in (getattr(it, "value", None) or {}).get("action_requests", []):
            return {"name": req["name"], "args": req.get("args", {})}
    return None


ADAPTERS = {"agent": AgentSession}


# ---------- 执行 ----------

def run_case(adapter_cls, case: dict, judge: bool) -> dict:
    turns, error = [], None
    with get_usage_metadata_callback() as cb:
        try:
            session = adapter_cls(case)
            for message in case["turns"]:
                start = time.perf_counter()
                out = session.send(message)
                turns.append({**out, "message": message, "latency_ms": round((time.perf_counter() - start) * 1000)})
        except Exception as e:  # noqa: BLE001  评测要记录失败而不是中断
            error = f"{type(e).__name__}: {e}"
    _, cost = _sum_usage(cb.usage_metadata)

    checks = check_case(case, turns[-1], turns) if not error else {"failed": False}
    claims = None
    if judge and not error and turns[-1]["answer"]:
        try:
            claims = judge_grounding(turns[-1]["message"], context_from_turns(turns, case.get("memories", [])),
                                     turns[-1]["answer"])
        except Exception as e:  # noqa: BLE001
            error = f"judge {type(e).__name__}: {e}"
    grounded_ok = claims is None or all(c["supported"] for c in claims)
    return {
        "id": case["id"], "category": case["category"], "expect": case["expect"],
        "turns": turns, "checks": checks, "claims": claims, "cost_usd": cost, "error": error,
        "passed": not error and all(v for v in checks.values() if v is not None) and grounded_ok,
    }


def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        agent_seed.seed(db)


def _judge_result(r: dict, case: dict) -> dict:
    last = r["turns"][-1] if r["turns"] else None
    claims = None
    if last and last["answer"] and not r["error"]:
        claims = judge_grounding(last["message"], context_from_turns(r["turns"], case.get("memories", [])),
                                 last["answer"])
    grounded_ok = claims is None or all(c["supported"] for c in claims)
    return {**r, "claims": claims,
            "passed": not r["error"] and all(v for v in r["checks"].values() if v is not None) and grounded_ok}


def rejudge(path: Path, concurrency: int):
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in json.loads((DATASET_DIR / "agent_cases.json").read_text(encoding="utf-8"))}
    with ThreadPoolExecutor(concurrency) as pool:
        data["results"] = list(pool.map(lambda r: _judge_result(r, cases[r["id"]]), data["results"]))
    data["summary"] = summarize(data["results"])
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    report = to_markdown(data["meta"], data["summary"])
    path.with_suffix(".md").write_text(report, encoding="utf-8")
    print(report)


def main():
    p = argparse.ArgumentParser(description="CareerMatch AI 助手评测")
    p.add_argument("--adapter", default="agent", choices=list(ADAPTERS))
    p.add_argument("--cases", type=int, default=None, help="只跑前 N 道题")
    p.add_argument("--concurrency", type=int, default=5)
    p.add_argument("--no-judge", action="store_true")
    p.add_argument("--langsmith", action="store_true", help="保留 LangSmith 追踪")
    p.add_argument("--rejudge", type=Path, help="对已有结果只重跑回答依据检查")
    args = p.parse_args()

    if args.rejudge:
        rejudge(args.rejudge, args.concurrency)
        return

    cases = json.loads((DATASET_DIR / "agent_cases.json").read_text(encoding="utf-8"))[:args.cases]
    reset_db()
    print(f"AI 助手评测：{len(cases)} 道题，助手 {args.adapter}")

    with ThreadPoolExecutor(args.concurrency) as pool:
        results = list(pool.map(lambda c: run_case(ADAPTERS[args.adapter], c, not args.no_judge), cases))

    summary = summarize(results)
    meta = {"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "adapter": args.adapter,
            "model": settings.model_agent, "judge": settings.model_judge}
    RESULTS_DIR.mkdir(exist_ok=True)
    stem = RESULTS_DIR / f"agent_eval_{args.adapter}_{datetime.now():%Y%m%d_%H%M}"
    stem.with_suffix(".json").write_text(
        json.dumps({"meta": meta, "summary": summary, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    report = to_markdown(meta, summary)
    stem.with_suffix(".md").write_text(report, encoding="utf-8")
    print("\n" + report)
    for r in results:
        if not r["passed"]:
            failed = [k for k, v in r["checks"].items() if v is False]
            if r["claims"] and not all(c["supported"] for c in r["claims"]):
                failed.append("grounded")
            print(f"  未通过 {r['id']}: {failed or r['error']}")
    print(f"原始记录：{stem.with_suffix('.json')}")


if __name__ == "__main__":
    main()
