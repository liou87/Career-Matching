import hmac
import os
from urllib.parse import unquote

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from database import engine
import models
from routers import profile, jobs, analysis, checklist, agent

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Job Helper API")


# 单用户、无账号体系，公网部署时用一个口令挡住外人（防止刷 DeepSeek 额度）。
# 没配 ACCESS_TOKEN（本地开发）时不校验。
@app.middleware("http")
async def check_access_token(request: Request, call_next):
    token = os.getenv("ACCESS_TOKEN")
    if token and request.method != "OPTIONS" and request.url.path != "/":
        # 前端做过 encodeURIComponent（请求头只能放 ASCII），口令可以含中文
        given = unquote(request.headers.get("X-Access-Token", ""))
        if not hmac.compare_digest(given.encode(), token.encode()):
            return JSONResponse({"detail": "访问口令错误"}, status_code=401)
    return await call_next(request)


# CORS 必须在口令校验之后注册：后注册的在最外层，
# 这样预检请求和 401 响应也会带上 CORS 头
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profile.router)
app.include_router(jobs.router)
app.include_router(analysis.router)
app.include_router(checklist.router)
app.include_router(agent.router)


@app.get("/")
def root():
    return {"status": "ok", "message": "Job Helper API running"}
