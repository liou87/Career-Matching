# 部署入口：vercel.json 的 entrypoint 和 uvicorn main:app 都指向这里，
# 应用本体在 app/main.py
from app.main import app  # noqa: F401
