"""
岗位检索评测：20 个查询，对比四种检索方式的排序质量。

- substring：第四阶段之前 search_jobs 的子串匹配（输入用助手当时会传的关键词，对旧方式最有利）
- keyword：jieba 分词 + BM25
- vector：bge-m3 向量（需要配置 embedding 服务）
- hybrid：keyword 和 vector 用 RRF 融合

标注：14 个规则推导的查询（按城市、公司、技能、标题，相关岗位直接从数据算出），
6 个语义查询由裁判对全部岗位逐一判断，结果缓存在 evals/dataset/retrieval_labels.json，
人工抽查后再采用。

运行（在 backend 目录下）：
    python -m evals.retrieval_eval
    python -m evals.retrieval_eval --relabel     # 重新让裁判标注语义查询
"""
import os
import tempfile
from pathlib import Path

# 必须在 import app 之前设置：检索在临时评测库里进行，评测流量不进线上指标
_TMP_DB = Path(tempfile.mkdtemp(prefix="careermatch-retrieval-eval-")) / "retrieval_eval.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ["RECORD_LLM_CALLS"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

import argparse  # noqa: E402
import json  # noqa: E402
from datetime import datetime  # noqa: E402

from langchain_core.prompts import ChatPromptTemplate  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.llm import embeddings  # noqa: E402
from app.llm.factory import get_model  # noqa: E402
from app.services.retrieval import search  # noqa: E402
from evals import agent_seed  # noqa: E402
from evals.run import DATASET_DIR, RESULTS_DIR  # noqa: E402

LABELS_PATH = DATASET_DIR / "retrieval_labels.json"
METHODS = ("substring", "keyword", "vector", "hybrid")
K = 5


# ---------- 标注 ----------

def rule_relevant(rule: dict, jobs: list[dict]) -> list[int]:
    def text(job):
        if rule["field"] == "skills":
            parts = (job.get("required_skills") or []) + (job.get("preferred_skills") or []) \
                + (job.get("responsibilities") or [])
            return " ".join(parts).lower()
        return (job.get(rule["field"]) or "").lower()

    return [j["job_id"] for j in jobs if any(a in text(j) for a in rule["aliases"])]


class JobJudgement(BaseModel):
    id: int = Field(description="岗位 id")
    # 先写依据再下结论：只输出「相关列表」时，裁判出现过理由写着不相关、却把岗位放进列表的情况
    reason: str = Field(description="一句话依据，引用岗位里的原文")
    relevant: bool = Field(description="是否明确符合查询描述")


class RelevanceResult(BaseModel):
    judgements: list[JobJudgement] = Field(description="每个岗位一条判断，不能遗漏")


RELEVANCE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你是严格的检索评测标注员，只依据给定的岗位信息判断，不做推测。"),
    ("user", """查询：{query}

岗位列表：
{jobs}

对每个岗位逐一判断是否明确符合查询描述：岗位的标题、技能要求或职责里有直接依据才算，
只是方向沾边、需要推测才能联系上的不算。每个岗位都要给出判断。"""),
])


def judge_semantic(queries: list[dict], jobs: list[dict]) -> dict:
    chain = RELEVANCE_PROMPT | get_model("judge").with_structured_output(RelevanceResult)
    listing = "\n".join(
        json.dumps({k: j.get(k) for k in ("job_id", "title", "company", "city", "required_skills",
                                           "preferred_skills", "responsibilities")}, ensure_ascii=False)
        for j in jobs
    )
    valid_ids = {j["job_id"] for j in jobs}
    labels = {}
    for q in queries:
        out = chain.invoke({"query": q["text"], "jobs": listing})
        if {j.id for j in out.judgements} != valid_ids:
            raise ValueError(f"裁判没有覆盖全部岗位：{q['id']}")
        labels[q["id"]] = [{"id": j.id, "reason": j.reason} for j in out.judgements if j.relevant]
        print(f"  裁判标注 {q['id']}: {[r['id'] for r in labels[q['id']]]}")
    return labels


def load_labels(queries: list[dict], jobs: list[dict], relabel: bool) -> dict[str, list[int]]:
    semantic = [q for q in queries if q["type"] == "semantic"]
    cached = json.loads(LABELS_PATH.read_text(encoding="utf-8")) if LABELS_PATH.exists() else {}
    if relabel or any(q["id"] not in cached for q in semantic):
        cached = judge_semantic(semantic, jobs)
        LABELS_PATH.write_text(json.dumps(cached, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    labels = {q["id"]: [r["id"] for r in cached[q["id"]]] for q in semantic}
    labels.update({q["id"]: rule_relevant(q["rule"], jobs) for q in queries if q["type"] == "rule"})
    return labels


# ---------- 指标 ----------

def score(ranking: list[int], relevant: list[int], k: int = K) -> dict:
    rel = set(relevant)
    first = next((i for i, j in enumerate(ranking, start=1) if j in rel), None)
    return {
        "recall": len(rel & set(ranking[:k])) / min(len(rel), k),
        "mrr": 1 / first if first else 0.0,
        "hit1": float(bool(ranking) and ranking[0] in rel),
    }


def aggregate(rows: list[dict]) -> dict:
    if not rows:
        return {}
    return {m: round(sum(r[m] for r in rows) / len(rows), 3) for m in ("recall", "mrr", "hit1")}


# ---------- 执行 ----------

def main():
    p = argparse.ArgumentParser(description="CareerMatch 岗位检索评测")
    p.add_argument("--relabel", action="store_true")
    args = p.parse_args()

    queries = json.loads((DATASET_DIR / "retrieval_queries.json").read_text(encoding="utf-8"))
    jobs = json.loads((DATASET_DIR / "jobs.json").read_text(encoding="utf-8"))
    labels = load_labels(queries, jobs, args.relabel)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    methods = [m for m in METHODS if m in ("substring", "keyword") or embeddings.enabled()]
    print(f"检索评测：{len(queries)} 个查询，方式 {methods}")

    per_query = []
    with SessionLocal() as db:
        agent_seed.seed(db)
        for q in queries:
            relevant = labels[q["id"]]
            row = {"id": q["id"], "type": q["type"], "text": q["text"], "relevant": relevant, "methods": {}}
            for m in methods:
                text = q["keyword"] if m == "substring" else q["text"]
                ranking = [r["id"] for r in search(db, text, limit=len(jobs), mode=m)["results"]]
                row["methods"][m] = {"ranking": ranking, **(score(ranking, relevant) if relevant else {})}
            per_query.append(row)

    summary = {}
    for m in methods:
        scored = [r for r in per_query if r["relevant"]]
        summary[m] = {
            "all": aggregate([r["methods"][m] for r in scored]),
            "rule": aggregate([r["methods"][m] for r in scored if r["type"] == "rule"]),
            "semantic": aggregate([r["methods"][m] for r in scored if r["type"] == "semantic"]),
        }

    meta = {"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "k": K, "methods": methods,
            "embedding_model": settings.embedding_model if embeddings.enabled() else None,
            "queries": len(queries), "skipped_no_relevant": [r["id"] for r in per_query if not r["relevant"]]}
    RESULTS_DIR.mkdir(exist_ok=True)
    stem = RESULTS_DIR / f"retrieval_eval_{datetime.now():%Y%m%d_%H%M}"
    stem.with_suffix(".json").write_text(
        json.dumps({"meta": meta, "summary": summary, "queries": per_query}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    report = to_markdown(meta, summary)
    stem.with_suffix(".md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"原始记录：{stem.with_suffix('.json')}")


def to_markdown(meta: dict, summary: dict) -> str:
    lines = [f"评测时间 {meta['date']}，{meta['queries']} 个查询，embedding {meta['embedding_model'] or '未配置'}。", "",
             f"| 方式 | recall@{meta['k']}（全部） | recall@{meta['k']}（规则） | recall@{meta['k']}（语义） | MRR | 首位命中 |",
             "| --- | --- | --- | --- | --- | --- |"]
    for m, s in summary.items():
        lines.append(f"| {m} | {s['all'].get('recall')} | {s['rule'].get('recall')} | "
                     f"{s['semantic'].get('recall')} | {s['all'].get('mrr')} | {s['all'].get('hit1')} |")
    if meta["skipped_no_relevant"]:
        lines.append(f"\n没有相关岗位、不计入指标的查询：{', '.join(meta['skipped_no_relevant'])}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
