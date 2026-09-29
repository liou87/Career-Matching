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

## 部署 CareerMatch

1. 在 Vercel 导入本仓库，Root Directory 保持仓库根目录。
   Vercel 读取根目录的 `vercel.json`，分别构建前端和后端两个服务。
2. 在项目的 Storage 页创建 Neon Postgres 并连接到该项目，
   `DATABASE_URL` 会自动加入环境变量。
3. 添加 `DEEPSEEK_API_KEY` 和 `ACCESS_TOKEN`，然后部署。
4. 访问 `/api/health`，返回 `{"status": "ok"}` 说明后端正常，
   首次启动会自动建表。
5. 打开首页，第一次请求会弹框要求输入访问口令，
   输入后保存在浏览器本地。

> [!TIP]
> Neon 数据库的区域尽量和 Vercel 函数区域一致（默认 `iad1`，美国东部），
> 否则每次查询都要跨区域往返。

## 迁移本地数据到 Postgres

在 Neon 控制台复制连接串，在 `backend/` 下运行：

```bash
python scripts/migrate_to_postgres.py "postgresql://user:pass@host/db?sslmode=require"
```

脚本会复制全部表并重置自增序列。目标库里已有数据时会直接中止，
不会覆盖任何内容。

## CareerMatch 线上限制

- 批量分析在请求内同步执行，15 个岗位约 35 秒。
  Hobby 套餐函数最长 300 秒，岗位数量大幅增加后可能超时。
- 单次匹配分析约 12 秒，AI 助手 10 到 20 秒，都在时限之内。
