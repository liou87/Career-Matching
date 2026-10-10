# 部署 CareerMatch 到 Vercel

前后端部署在同一个 Vercel 项目里，用 Vercel Services 共享一个域名：
`/api/*` 转给 FastAPI 后端，其余路径交给 Vite 前端。
配置在仓库根目录的 `vercel.json`。数据库用 Neon Postgres。

本地开发不受影响：没有配置 `DATABASE_URL` 时仍然使用 SQLite，
Vite 开发服务器会把 `/api` 代理到本机 8000 端口。

## CareerMatch 线上环境变量

- `DEEPSEEK_API_KEY`：DeepSeek API Key。
- `DATABASE_URL`：Postgres 连接串，接入 Neon 后自动注入。
- `ACCESS_TOKEN`：访问口令。不配置则任何人都能访问并消耗 API 额度。
- `PUBLIC_READ`：默认 `true`。配了口令时访客可以浏览（只读演示），
  调用 AI 和修改数据仍要口令；设为 `false` 则所有接口都要口令。
- `AI_RATE_LIMIT`、`AI_RATE_WINDOW_MINUTES`：每个 IP 在窗口内最多的 AI 请求数，
  默认 10 分钟 20 次。
- `DAILY_TOKEN_BUDGET`：全站每天的 token 上限，默认 200 万，按北京时间零点重置，
  超出后当天停用 AI。设为 0 关闭。
- `SILICONFLOW_API_KEY`：可选，岗位语义检索用的 embedding（BAAI/bge-m3）。
  不配置时岗位搜索只用关键词。
- `LOG_JSON`：日志一行一条 JSON，方便在 Vercel Logs 里检索。在 Vercel 上
  默认开启，不用手动设置。
- `LANGSMITH_TRACING`、`LANGSMITH_API_KEY`、`LANGSMITH_PROJECT`：可选，
  开启 LangSmith 链路追踪。每次请求返回前会等 trace 上传完，
  避免函数被冻结时丢数据。

其他可调参数（按角色换模型、超时、评分权重等）见
`backend/app/core/config.py`，环境变量名为字段名的大写。

## 部署 CareerMatch

1. 在 Vercel 导入本仓库，Root Directory 保持仓库根目录。
   Vercel 读取根目录的 `vercel.json`，分别构建前端和后端两个服务。
2. 在项目的 Storage 页创建 Neon Postgres 并连接到该项目，
   `DATABASE_URL` 会自动加入环境变量。
3. 添加 `DEEPSEEK_API_KEY` 和 `ACCESS_TOKEN`，然后部署。
4. 在本地对 Neon 执行一次建表（见下一节），应用启动时不会自动建表。
5. 访问 `/api/health`，返回 `{"status": "ok"}` 说明后端正常。
6. 打开首页，第一次请求会弹框要求输入访问口令，
   输入后保存在浏览器本地。

> [!TIP]
> Neon 数据库的区域尽量和 Vercel 函数区域一致（默认 `iad1`，美国东部），
> 否则每次查询都要跨区域往返。

## 管理 CareerMatch 数据库结构

表结构由 Alembic 管理，迁移文件在 `backend/migrations/versions/`。
在 `backend/` 下对线上库执行，连接串从 Neon 控制台复制：

```bash
# 全新的空库：建出全部表
DATABASE_URL="postgresql://..." alembic upgrade head

# 已有表、但从未用过 Alembic 的库（比如用下面的迁移脚本导入过数据）：
# 只记录版本号，不改表
DATABASE_URL="postgresql://..." alembic stamp head
```

修改了 `app/db/models.py` 之后：

```bash
alembic revision --autogenerate -m "说明这次改了什么"
alembic upgrade head                              # 先更新本地库
DATABASE_URL="postgresql://..." alembic upgrade head   # 再更新线上库，然后再部署代码
```

> [!WARNING]
> 先迁移线上库、再推送依赖新表结构的代码，否则新代码上线后会因为缺列报错。

新入库的岗位会自动建检索索引。第一次上线检索功能、或者配置 embedding 之后，
在本地对线上库补算一次已有岗位的索引：

```bash
DATABASE_URL="postgresql://..." SILICONFLOW_API_KEY="sk-..." python scripts/index_jobs.py
```

## 迁移本地数据到 Postgres

在 Neon 控制台复制连接串，在 `backend/` 下运行：

```bash
python scripts/migrate_to_postgres.py "postgresql://user:pass@host/db?sslmode=require"
```

脚本会复制全部表并重置自增序列。目标库里已有数据时会直接中止，
不会覆盖任何内容。完成后按上一节对目标库执行一次 `alembic stamp head`。

## CareerMatch 线上限制

- 批量分析在请求内同步执行，15 个岗位约 35 秒。
  Hobby 套餐函数最长 300 秒，岗位数量大幅增加后可能超时。
- 单次匹配分析约 12 秒，AI 助手 10 到 20 秒，都在时限之内。
