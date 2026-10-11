"""
集中配置。所有可调参数都在这里，用环境变量或 backend/.env 覆盖，
环境变量名就是字段名的大写，比如 MODEL_ANALYSIS=deepseek-reasoner。
"""
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]

# LangSmith 等第三方库直接读 os.environ，而 pydantic-settings 不会把 .env
# 写回环境变量，所以先把 .env 整体加载进环境变量，再由 Settings 读取
load_dotenv(BACKEND_DIR / ".env")

class Settings(BaseSettings):
    # 关掉 pydantic 对 model_ 前缀的保护，下面按角色配置的字段要用这个前缀
    model_config = SettingsConfigDict(extra="ignore", protected_namespaces=())

    # ---------- 部署 ----------
    database_url: str | None = None  # 不配就用 backend/job_helper.db
    access_token: str | None = None  # 不配就不校验口令
    # 配了口令时，GET 请求是否公开（只读演示）：访客能浏览，调用 AI 和写数据仍要口令
    public_read: bool = True

    # ---------- LLM 供应商 ----------
    # 走 LangChain 的 init_chat_model，换供应商只改这几项（provider 名称见
    # LangChain 文档，OpenAI 兼容的服务用 openai + base_url）
    llm_provider: str = "deepseek"
    llm_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("LLM_API_KEY", "DEEPSEEK_API_KEY")
    )
    llm_base_url: str | None = None  # 不配就用供应商默认地址
    llm_timeout: float = 60  # 单次调用超时（秒）
    llm_max_retries: int = 2  # 超时、限流、5xx 时 SDK 层的重试次数
    # DeepSeek 的 V4 系列默认开启思考模式，会额外消耗推理 token、拖慢响应。
    # 旧别名 deepseek-chat 等价于 deepseek-flash + 关闭思考，这里保持同样的行为
    llm_thinking: bool = False

    # ---------- 按角色配置模型 ----------
    # 参考 open_deep_research：不同环节可以用不同模型，方便做降本实验。
    # deepseek-chat 是已弃用的旧别名（实际由 deepseek-flash 响应），不要再用
    model_jd_parse: str = "deepseek-flash"
    model_analysis: str = "deepseek-flash"
    model_suggest: str = "deepseek-flash"
    model_merge: str = "deepseek-flash"
    model_agent: str = "deepseek-flash"
    model_interview: str = "deepseek-flash"
    # 评测里判断「编造」的裁判模型，用更强的模型
    model_judge: str = "deepseek-v4-pro"

    max_tokens_jd_parse: int = 1024
    max_tokens_analysis: int = 2048
    max_tokens_suggest: int = 2048
    # 技能归并一次要处理几十条（15 个岗位约 75 条），输出约 3000 token
    max_tokens_merge: int = 8192
    max_tokens_agent: int = 2048
    max_tokens_judge: int = 2048
    max_tokens_interview: int = 4096

    # ---------- 价格（美元 / 百万 token） ----------
    # 用于估算成本，取 DeepSeek 官方价格页的高峰时段价格（偏保守），
    # 不在表里的模型不估算成本。价格变了只改这里
    model_prices: dict[str, dict[str, float]] = {
        "deepseek-flash": {"input": 0.30, "cached_input": 0.006, "output": 1.2},
        "deepseek-v4-pro": {"input": 1.32, "cached_input": 0.044, "output": 3.96},
    }

    # ---------- 匹配评分 ----------
    score_weights: dict[str, float] = {
        "skills": 0.4,
        "experience": 0.3,
        "education": 0.15,
        "other": 0.15,
    }
    # 岗位必需技能里命中这些词，就判定为技术路线不符，跳过建议生成
    excluded_skills: list[str] = ["java", "golang", "go语言"]

    # ---------- AI 接口的限流和预算 ----------
    # 只管会调用 AI 的接口；设为 0 关闭对应检查
    ai_rate_limit: int = 20             # 每个 IP 在一个窗口内最多的 AI 请求数
    ai_rate_window_minutes: int = 10
    daily_token_budget: int = 2_000_000  # 全站每天的 token 上限（按北京时间零点算一天）

    # ---------- 岗位检索 ----------
    # embedding 走 OpenAI 兼容接口，默认硅基流动的 bge-m3；没配 Key 时只用关键词检索
    embedding_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("EMBEDDING_API_KEY", "SILICONFLOW_API_KEY")
    )
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"
    embedding_timeout: float = 20
    search_rrf_k: int = 60  # RRF 融合的常数，取文献里的常用值
    # 线上检索方式。评测里 BM25 的 recall@5 是 0.963，混合 0.943，向量单独 0.792，
    # 所以默认只用关键词；配了 embedding 时入库照样算向量，改成 hybrid 即可切换
    search_mode: Literal["keyword", "hybrid"] = "keyword"

    # ---------- 批量分析 ----------
    batch_max_concurrency: int = 5
    batch_timeout_minutes: int = 5  # 超过这个时间仍是 running 的任务视为中断

    # ---------- 日志与链路追踪 ----------
    log_level: str = "INFO"
    # 每条日志输出一行 JSON。Vercel 运行时会注入 VERCEL=1，线上默认开启、本地默认关闭；
    # 显式设置 LOG_JSON 可以覆盖
    log_json: bool = Field(default_factory=lambda: os.getenv("VERCEL") == "1")
    # LangSmith 由 LangChain 直接读环境变量（LANGSMITH_TRACING / LANGSMITH_API_KEY /
    # LANGSMITH_PROJECT），这里只用来判断请求结束时要不要等 trace 上传完
    langsmith_tracing: bool = False
    # 每次 LLM 调用写一条记录到 llm_calls 表，供 /api/metrics 统计。离线评测时关掉，
    # 免得评测流量混进线上指标
    record_llm_calls: bool = True

    @field_validator("score_weights")
    @classmethod
    def _check_weights(cls, v: dict[str, float]) -> dict[str, float]:
        expected = {"skills", "experience", "education", "other"}
        if set(v) != expected:
            raise ValueError(f"score_weights 必须恰好包含 {sorted(expected)}")
        if abs(sum(v.values()) - 1) > 1e-6:
            raise ValueError(f"score_weights 之和必须为 1，当前为 {sum(v.values())}")
        return v


settings = Settings()
