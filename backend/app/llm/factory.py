"""
LLM 工厂：所有模型实例都从这里拿，业务代码不直接构造模型。

模型懒加载并按角色缓存：import 时不会创建模型，所以没有 API Key 时
应用照样能启动（不调 LLM 的接口和测试都不受影响）。
"""
from functools import lru_cache
from typing import Literal

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from app.core.config import settings

Role = Literal["jd_parse", "analysis", "suggest", "merge", "agent"]


@lru_cache
def get_model(role: Role) -> BaseChatModel:
    kwargs = {}
    if settings.llm_base_url:
        kwargs["base_url"] = settings.llm_base_url

    return init_chat_model(
        getattr(settings, f"model_{role}"),
        model_provider=settings.llm_provider,
        api_key=settings.llm_api_key,
        temperature=0,
        max_tokens=getattr(settings, f"max_tokens_{role}"),
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
        # 打上角色标签，链路追踪里可以按角色筛选
        tags=[f"role:{role}"],
        metadata={"llm_role": role},
        **kwargs,
    )
