"""
集中配置。所有可调参数都在这里，用环境变量或 backend/.env 覆盖，
环境变量名就是字段名的大写，比如 MODEL_ANALYSIS=deepseek-reasoner。
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]

# LangSmith 等第三方库直接读 os.environ，而 pydantic-settings 不会把 .env
# 写回环境变量，所以先把 .env 整体加载进环境变量，再由 Settings 读取
load_dotenv(BACKEND_DIR / ".env")

LLM_ROLES = ("jd_parse", "analysis", "suggest", "merge", "agent")


class Settings(BaseSettings):
    # 关掉 pydantic 对 model_ 前缀的保护，下面按角色配置的字段要用这个前缀
    model_config = SettingsConfigDict(extra="ignore", protected_namespaces=())

    # ---------- 部署 ----------
    database_url: str | None = None  # 不配就用 backend/job_helper.db
    access_token: str | None = None  # 不配就不校验口令

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

    # ---------- 按角色配置模型 ----------
    # 参考 open_deep_research：不同环节可以用不同模型，方便做降本实验
    model_jd_parse: str = "deepseek-chat"
    model_analysis: str = "deepseek-chat"
    model_suggest: str = "deepseek-chat"
    model_merge: str = "deepseek-chat"
    model_agent: str = "deepseek-chat"

    max_tokens_jd_parse: int = 1024
    max_tokens_analysis: int = 2048
    max_tokens_suggest: int = 2048
    # 技能归并一次要处理几十条（15 个岗位约 75 条），输出约 3000 token
    max_tokens_merge: int = 8192
    max_tokens_agent: int = 2048

    # ---------- 匹配评分 ----------
    score_weights: dict[str, float] = {
        "skills": 0.4,
        "experience": 0.3,
        "education": 0.15,
        "other": 0.15,
    }
    # 岗位必需技能里命中这些词，就判定为技术路线不符，跳过建议生成
    excluded_skills: list[str] = ["java", "golang", "go语言"]

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
