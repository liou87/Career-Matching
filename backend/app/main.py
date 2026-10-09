import hmac
import logging
import time
import uuid
from urllib.parse import unquote

from fastapi import APIRouter, FastAPI, Request
from langchain_core.tracers.langchain import wait_for_all_tracers
from starlette.concurrency import run_in_threadpool

from app.api import agent, analysis, checklist, jobs, profile
from app.core.config import settings
from app.core.errors import error_response, register_error_handlers
from app.core.logging import request_id_var, setup_logging

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Job Helper API")
register_error_handlers(app)

# 所有接口挂在 /api 下：线上前后端同域（Vercel 把 /api/* 转给后端，
# 后端收到的是完整路径），本地由 Vite 把 /api 代理到 8000 端口，不需要 CORS
HEALTH_PATH = "/api/health"


# 单用户、无账号体系，公网部署时用一个口令挡住外人（防止刷 DeepSeek 额度）。
# 没配 ACCESS_TOKEN（本地开发）时不校验。
@app.middleware("http")
async def check_access_token(request: Request, call_next):
    token = settings.access_token
    if token and request.url.path != HEALTH_PATH:
        # 前端做过 encodeURIComponent（请求头只能放 ASCII），口令可以含中文
        given = unquote(request.headers.get("X-Access-Token", ""))
        if not hmac.compare_digest(given.encode(), token.encode()):
            return error_response(request, 401, "UNAUTHORIZED", "访问口令错误")
    return await call_next(request)


# 必须注册在口令校验之后：后注册的中间件在最外层，被拦下的 401 也会记日志
@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    token = request_id_var.set(request_id)
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception:
        # 在这里记录而不是在全局 handler 里：这里还在请求上下文中，能带上 request_id
        logger.exception("unhandled_exception")
        raise
    finally:
        logger.info(
            "request",
            extra={"fields": {
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "ms": round((time.perf_counter() - start) * 1000),
            }},
        )
        # Serverless 函数返回后进程可能立刻被冻结，trace 要在返回前传完
        if settings.langsmith_tracing:
            await run_in_threadpool(wait_for_all_tracers)
        request_id_var.reset(token)


api = APIRouter(prefix="/api")
api.include_router(profile.router)
api.include_router(jobs.router)
api.include_router(analysis.router)
api.include_router(checklist.router)
api.include_router(agent.router)


@api.get("/health")
def health():
    return {"status": "ok", "message": "Job Helper API running"}


app.include_router(api)
