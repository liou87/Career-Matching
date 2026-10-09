"""
统一的错误分类与响应格式。

所有错误响应都是 {"detail": 提示文案, "code": 错误码, "request_id": ...}，
前端直接展示 detail。LLM 相关的失败按原因分成超时、限流、鉴权、上游错误、
输出格式错误几类，不再统一变成 500。
"""
import logging

import openai
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class DomainError(Exception):
    """业务错误：带状态码和给用户看的提示。接口层转成对应的 HTTP 响应，
    Agent 工具把提示原样返回给模型，由模型转告用户。"""

    status = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    status = 404
    code = "NOT_FOUND"


class ConflictError(DomainError):
    status = 409
    code = "CONFLICT"


class LLMOutputError(Exception):
    """LLM 没有返回符合结构的结果，比如 with_structured_output 返回 None。

    不能继承 ValueError：langgraph 的 default_retry_on 明确把 ValueError
    及其子类排除在重试范围外，继承 ValueError 会让 RetryPolicy 形同虚设。
    """


def classify(exc: Exception) -> tuple[int, str, str]:
    """把异常映射成 (HTTP 状态码, 错误码, 给用户看的提示)。"""
    if isinstance(exc, DomainError):
        return exc.status, exc.code, exc.message
    # 子类必须排在父类前面：APITimeoutError 继承自 APIConnectionError，
    # RateLimitError、AuthenticationError 继承自 APIStatusError
    if isinstance(exc, openai.APITimeoutError):
        return 504, "LLM_TIMEOUT", "AI 服务响应超时，请稍后重试"
    if isinstance(exc, openai.RateLimitError):
        return 503, "LLM_RATE_LIMITED", "AI 服务当前繁忙（被限流），请稍后重试"
    if isinstance(exc, openai.AuthenticationError):
        return 502, "LLM_AUTH", "AI 服务鉴权失败，请检查 API Key 配置"
    if isinstance(exc, openai.APIStatusError):
        return 502, "LLM_UPSTREAM", f"AI 服务返回错误（状态码 {exc.status_code}），请稍后重试"
    if isinstance(exc, openai.APIConnectionError):
        return 502, "LLM_UNAVAILABLE", "无法连接 AI 服务，请稍后重试"
    # 请求参数的校验错误是 RequestValidationError，不会走到这里；
    # 这里的 ValidationError 只可能来自 LLM 结构化输出的校验
    if isinstance(exc, (LLMOutputError, ValidationError)):
        return 502, "LLM_BAD_OUTPUT", "AI 返回的结果格式不正确，请重试"
    return 500, "INTERNAL", "服务器内部错误"


def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        {"detail": message, "code": code, "request_id": request_id},
        status_code=status,
    )


def register_error_handlers(app: FastAPI) -> None:
    llm_errors = (openai.OpenAIError, LLMOutputError, ValidationError)

    async def handle_llm_error(request: Request, exc: Exception):
        status, code, message = classify(exc)
        logger.warning(
            "llm_request_failed",
            extra={"fields": {"code": code, "error": f"{type(exc).__name__}: {exc}"}},
        )
        return error_response(request, status, code, message)

    async def handle_domain_error(request: Request, exc: DomainError):
        return error_response(request, exc.status, exc.code, exc.message)

    async def handle_unexpected(request: Request, exc: Exception):
        # 日志已在 main.py 的请求中间件里记过（那里能带上 request_id），这里只负责响应
        return error_response(request, *classify(exc))

    app.add_exception_handler(DomainError, handle_domain_error)
    for exc_type in llm_errors:
        app.add_exception_handler(exc_type, handle_llm_error)
    app.add_exception_handler(Exception, handle_unexpected)
