"""岗位检索：分词、BM25、RRF、向量一路、降级与建索引。embedding 用假的确定性向量。"""
import pytest

from app.db import models
from app.llm import embeddings
from app.services import retrieval
from app.services.retrieval import BM25, build_chunks, index_job, rrf, search, tokenize

# 假 embedding：按几个概念维度给向量，语义相近的文本向量相近
CONCEPTS = [("后端", "服务端", "golang", "java"), ("评测", "测试", "eval"), ("检索", "rag", "向量")]


def fake_embed(texts):
    return [[1.0 if any(k in t.lower() for k in words) else 0.0 for words in CONCEPTS] + [0.1] for t in texts]


@pytest.fixture
def vectors_on(monkeypatch):
    monkeypatch.setattr(embeddings, "enabled", lambda: True)
    monkeypatch.setattr(embeddings, "embed", fake_embed)


def _job(db, title, skills=(), city=None, responsibilities=()):
    job = models.Job(raw_jd="", title=title, required_skills=list(skills), city=city,
                     responsibilities=list(responsibilities), status="active")
    db.add(job)
    db.commit()
    index_job(db, job)
    return job.id


def test_tokenize_keeps_domain_words_and_drops_stopwords():
    tokens = tokenize("要求大模型应用开发的岗位")
    assert "大模型" in tokens
    assert "岗位" not in tokens and "要求" not in tokens


def test_bm25_ranks_relevant_document_first():
    docs = [tokenize("必需技能：Python、FastAPI"), tokenize("必需技能：RAG、向量数据库、Python")]
    scores = BM25(docs).scores(tokenize("RAG 向量数据库"))
    assert scores[1] > scores[0] == 0


def test_rrf_rewards_agreement_between_rankings():
    assert rrf([[1, 2, 3], [2, 1, 3]], k=60)[:2] in ([1, 2], [2, 1])
    assert rrf([[1, 2], [2, 3]], k=60)[0] == 2  # 两路都靠前的排第一


def test_build_chunks_by_field():
    job = models.Job(title="AI 工程师", company="某公司", city="上海", salary_min=20, salary_max=30,
                     required_skills=["Python"], preferred_skills=["RAG"], experience_required="1-3年",
                     responsibilities=["负责 Agent 开发", "建设评测体系"])
    fields = [f for f, _ in build_chunks(job)]
    assert fields == ["header", "required", "preferred", "requirements", "responsibility", "responsibility"]
    assert build_chunks(job)[0][1] == "AI 工程师 | 某公司 | 上海 | 20-30K"


def test_keyword_only_without_embedding_service(db):
    _job(db, "RAG 工程师", ["RAG"])
    out = search(db, "RAG")
    assert out["mode"] == "keyword" and out["results"][0]["title"] == "RAG 工程师"


def test_vector_path_finds_semantic_match_keyword_misses(db, vectors_on):
    _job(db, "服务端开发", ["Golang", "Java"])
    _job(db, "前端开发", ["React"])

    keyword = search(db, "后端方向", mode="keyword")["results"]
    hybrid = search(db, "后端方向", mode="hybrid")

    assert keyword == []                                   # 字面上没有「后端」
    assert hybrid["mode"] == "keyword+vector"
    assert hybrid["results"][0]["title"] == "服务端开发"


def test_embedding_failure_falls_back_to_keyword(db, monkeypatch):
    monkeypatch.setattr(embeddings, "enabled", lambda: True)

    def broken(texts):
        raise RuntimeError("embedding 服务不可用")

    monkeypatch.setattr(embeddings, "embed", broken)
    job_id = _job(db, "RAG 工程师", ["RAG"])

    chunks = db.query(models.JobChunk).filter(models.JobChunk.job_id == job_id).all()
    assert chunks and all(c.embedding is None for c in chunks)   # 片段照样保存
    assert search(db, "RAG")["results"][0]["id"] == job_id      # 关键词仍可检索


def test_substring_mode_reproduces_old_behaviour(db):
    _job(db, "Agent 工程师", ["LangChain"], city="深圳")
    assert search(db, "深圳", mode="substring")["results"] == []   # 旧方式不搜城市
    assert search(db, "深圳", mode="keyword")["results"][0]["title"] == "Agent 工程师"


def test_new_job_is_indexed_on_creation(client, db, monkeypatch):
    import app.services.jobs as jobs_service

    monkeypatch.setattr(jobs_service, "parse_jd", lambda raw: {"title": "Agent 工程师", "required_skills": ["RAG"]})
    job_id = client.post("/api/jobs", json={"raw_jd": "原文"}).json()["id"]

    assert db.query(models.JobChunk).filter(models.JobChunk.job_id == job_id).count() == 2
    assert retrieval.search(db, "RAG")["results"][0]["id"] == job_id
