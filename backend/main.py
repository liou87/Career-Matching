import hmac
import os
from urllib.parse import unquote

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from database import engine
import models
from routers import profile, jobs, analysis, checklist, agent

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Job Helper API")

# 所有接口挂在 /api 下：线上前后端同域（Vercel 把 /api/* 转给后端，
# 后端收到的是完整路径），本地由 Vite 把 /api 代理到 8000 端口，不需要 CORS
HEALTH_PATH = "/api/health"


# 单用户、无账号体系，公网部署时用一个口令挡住外人（防止刷 DeepSeek 额度）。
# 没配 ACCESS_TOKEN（本地开发）时不校验。
@app.middleware("http")
async def check_access_token(request: Request, call_next):
    token = os.getenv("ACCESS_TOKEN")
    if token and request.url.path != HEALTH_PATH:
        # 前端做过 encodeURIComponent（请求头只能放 ASCII），口令可以含中文
        given = unquote(request.headers.get("X-Access-Token", ""))
        if not hmac.compare_digest(given.encode(), token.encode()):
            return JSONResponse({"detail": "访问口令错误"}, status_code=401)
    return await call_next(request)


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
