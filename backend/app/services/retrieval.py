"""
岗位检索：关键词和向量两路，用 RRF（Reciprocal Rank Fusion）按排名融合。

- 关键词：jieba 分词 + BM25，对岗位的每个片段打分，岗位取最高分的片段
- 向量：bge-m3 向量的余弦相似度，同样按片段算、岗位取最高
- 融合：每个岗位得分 = Σ 1 / (k + 在各路里的名次)，只看名次不看原始分数，不用调权重
- 城市、公司是过滤条件，返回过滤后的岗位总数，用来回答「深圳有哪些岗位」「一共多少个岗位」

只索引结构化字段（标题、公司、城市、技能、经验学历、职责），每个片段原文随结果返回，
回答时可以引用。没有配置 embedding 服务时自动只用关键词检索。

mode="substring" 是第四阶段之前的子串匹配，只用于评测对照。
"""
import logging
import math
import re
from collections import Counter

import jieba
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import models
from app.llm import embeddings

logger = logging.getLogger(__name__)

jieba.setLogLevel(logging.WARNING)
# 招聘领域的常见词，避免被切碎（比如默认会把「大模型」切成「大 / 模型」）
for _w in ["大模型", "多模态", "向量数据库", "智能体", "提示词", "检索增强", "知识库", "微调",
           "后端", "前端", "全栈", "分布式", "高并发", "微服务", "数据结构", "应届生", "校招"]:
    jieba.add_word(_w)

_HAS_WORD = re.compile(r"\w")
STOPWORDS = {"的", "了", "和", "与", "及", "或", "等", "有", "吗", "呢", "哪些", "什么", "哪个", "我",
             "岗位", "职位", "要求", "需要", "相关", "工作", "一些", "这个", "那个"}

MODES = ("hybrid", "keyword", "vector", "substring")


def tokenize(text: str) -> list[str]:
    return [t for t in jieba.lcut_for_search(text.lower()) if _HAS_WORD.search(t) and t not in STOPWORDS]


# ---------- 建索引 ----------

def build_chunks(job: models.Job) -> list[tuple[str, str]]:
    """把岗位切成 (字段, 文本) 片段。"""
    salary = f"{job.salary_min}-{job.salary_max}K" if job.salary_min and job.salary_max else None
    header = " | ".join(x for x in [job.title, job.company, job.city, salary] if x)
    chunks = [("header", header)] if header else []
    if job.required_skills:
        chunks.append(("required", "必需技能：" + "、".join(job.required_skills)))
    if job.preferred_skills:
        chunks.append(("preferred", "加分技能：" + "、".join(job.preferred_skills)))
    reqs = [x for x in [job.experience_required and f"经验：{job.experience_required}",
                        job.education_required and f"学历：{job.education_required}"] if x]
    if reqs:
        chunks.append(("requirements", "；".join(reqs)))
    chunks += [("responsibility", f"职责：{r}") for r in job.responsibilities or []]
    return chunks


def index_job(db: Session, job: models.Job) -> int:
    """重建一个岗位的片段和向量。embedding 失败不抛错：片段照样保存，只参与关键词检索。"""
    db.query(models.JobChunk).filter(models.JobChunk.job_id == job.id).delete()
    chunks = build_chunks(job)
    vectors = None
    if embeddings.enabled() and chunks:
        try:
            vectors = embeddings.embed([text for _, text in chunks])
        except Exception:
            logger.warning("embedding_failed", exc_info=True, extra={"fields": {"job_id": job.id}})
    for i, (field, text) in enumerate(chunks):
        db.add(models.JobChunk(
            job_id=job.id, field=field, text=text,
            embedding=vectors[i] if vectors else None,
            embedding_model=settings.embedding_model if vectors else None,
        ))
    db.commit()
    return len(chunks)


# ---------- 检索 ----------

class BM25:
    """标准 BM25（k1=1.5, b=0.75），语料只有几百个片段，直接在内存里算。"""

    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.avgdl = sum(map(len, docs)) / len(docs) if docs else 0
        df = Counter(t for d in docs for t in set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d) for d in docs]

    def scores(self, query: list[str]) -> list[float]:
        out = []
        for tf, doc in zip(self.tf, self.docs):
            norm = self.k1 * (1 - self.b + self.b * len(doc) / self.avgdl) if self.avgdl else self.k1
            out.append(sum(self.idf.get(t, 0) * tf[t] * (self.k1 + 1) / (tf[t] + norm) for t in query if t in tf))
        return out


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _rank_by_chunks(chunks: list[models.JobChunk], scores: list[float], positive_only: bool) -> list[tuple[int, int]]:
    """片段分数汇总到岗位（取最高分），返回按分数降序的 [(job_id, 最佳片段下标)]。"""
    best: dict[int, tuple[float, int]] = {}
    for i, (c, s) in enumerate(zip(chunks, scores)):
        if positive_only and s <= 0:
            continue
        if c.job_id not in best or s > best[c.job_id][0]:
            best[c.job_id] = (s, i)
    return [(job_id, idx) for job_id, (_, idx) in sorted(best.items(), key=lambda kv: -kv[1][0])]


def rrf(rankings: list[list[int]], k: int) -> list[int]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, job_id in enumerate(ranking, start=1):
            scores[job_id] = scores.get(job_id, 0) + 1 / (k + rank)
    return sorted(scores, key=lambda j: -scores[j])


def search(db: Session, query: str = "", city: str | None = None, company: str | None = None,
           limit: int = 5, mode: str = "hybrid") -> dict:
    """返回 {"total": 满足城市/公司筛选的岗位数, "matched": 其中与 query 关键词相关的岗位数,
    "mode": 实际使用的方式, "results": 按相关度排序的前 limit 条}。

    只有向量一路时没有「是否相关」的硬边界，matched 为 None。"""
    jobs = db.query(models.Job).filter(models.Job.status == "active").order_by(models.Job.id).all()
    if city:
        jobs = [j for j in jobs if city.lower() in (j.city or "").lower()]
    if company:
        jobs = [j for j in jobs if company.lower() in (j.company or "").lower()]
    by_id = {j.id: j for j in jobs}

    snippets: dict[int, list[str]] = {}
    if not query.strip():
        ranking, used = [j.id for j in jobs], "filter"
        matched = len(jobs)
    elif mode == "substring":
        ranking, used = _substring(jobs, query), "substring"
        matched = len(ranking)
    else:
        chunks = db.query(models.JobChunk).filter(models.JobChunk.job_id.in_(by_id)).order_by(models.JobChunk.id).all()
        ranking, used, matched = _ranked(chunks, query, mode, snippets)

    results = []
    for job_id in ranking[:limit]:
        j = by_id[job_id]
        results.append({
            "id": j.id, "title": j.title, "company": j.company, "city": j.city,
            "salary": f"{j.salary_min}-{j.salary_max}K" if j.salary_min and j.salary_max else None,
            "required_skills": j.required_skills,
            "snippets": snippets.get(job_id, []),
        })
    return {"total": len(jobs), "matched": matched, "mode": used, "results": results}


def _ranked(chunks: list[models.JobChunk], query: str, mode: str,
            snippets: dict) -> tuple[list[int], str, int | None]:
    rankings, used, matched = [], [], None

    if mode in ("keyword", "hybrid"):
        scores = BM25([tokenize(c.text) for c in chunks]).scores(tokenize(query))
        kw = _rank_by_chunks(chunks, scores, positive_only=True)
        rankings.append([job_id for job_id, _ in kw])
        used.append("keyword")
        matched = len(kw)
        _add_snippets(snippets, chunks, kw)

    if mode in ("vector", "hybrid") and embeddings.enabled():
        with_vec = [c for c in chunks if c.embedding]
        if with_vec:
            try:
                qvec = embeddings.embed([query])[0]
                vec = _rank_by_chunks(with_vec, [_cosine(qvec, c.embedding) for c in with_vec], positive_only=False)
                rankings.append([job_id for job_id, _ in vec])
                used.append("vector")
                _add_snippets(snippets, with_vec, vec)
            except Exception:
                logger.warning("query_embedding_failed", exc_info=True)

    if not rankings:
        return [], "none", 0
    ranking = rankings[0] if len(rankings) == 1 else rrf(rankings, settings.search_rrf_k)
    return ranking, "+".join(used), matched


def _add_snippets(snippets: dict, chunks: list[models.JobChunk], ranked: list[tuple[int, int]]) -> None:
    for job_id, idx in ranked:
        text = chunks[idx].text
        if text not in snippets.setdefault(job_id, []):
            snippets[job_id].append(text)


def _substring(jobs: list[models.Job], keyword: str) -> list[int]:
    """第四阶段之前 search_jobs 的匹配方式：关键词是否出现在标题、公司、技能里。"""
    kw = keyword.lower()
    return [
        j.id for j in jobs
        if kw in " ".join([j.title or "", j.company or "", *(j.required_skills or []),
                           *(j.preferred_skills or [])]).lower()
    ]
