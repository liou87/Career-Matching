# 部署 CareerMatch 到 Vercel

前端和后端分别部署成两个 Vercel 项目，数据库用 Neon Postgres。
本地开发不受影响：没有配置 `DATABASE_URL` 时仍然使用 SQLite。

## CareerMatch 线上环境变量

后端项目：

- `DEEPSEEK_API_KEY`：DeepSeek API Key。
- `DATABASE_URL`：Postgres 连接串，接入 Neon 后自动注入。
- `ACCESS_TOKEN`：访问口令。不配置则任何人都能访问并消耗 API 额度。
- `CORS_ORIGINS`：前端域名，多个用英文逗号分隔，末尾不带 `/`。

前端项目：

- `VITE_API_URL`：后端域名，末尾不带 `/`。构建时写入代码，
  修改后需要重新部署前端。

## 部署 CareerMatch 后端

1. 在 Vercel 导入本仓库，Root Directory 选 `backend`。
   框架会被识别为 FastAPI，入口是 `main.py` 里的 `app`。
2. 在项目的 Storage 页创建 Neon Postgres 并连接到该项目，
   `DATABASE_URL` 会自动加入环境变量。
3. 添加 `DEEPSEEK_API_KEY` 和 `ACCESS_TOKEN`，然后部署。
4. 部署完成后访问后端根路径，返回 `{"status": "ok"}` 即正常。
   首次启动会自动建表。

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

## 部署 CareerMatch 前端

1. 再导入一次本仓库，Root Directory 选 `frontend`，框架识别为 Vite。
2. 添加 `VITE_API_URL`，值为后端域名，然后部署。
3. 回到后端项目，把前端域名填进 `CORS_ORIGINS`，重新部署后端。
4. 打开前端，首次请求会弹框要求输入访问口令，
   输入后保存在浏览器本地。

> [!NOTE]
> `CORS_ORIGINS` 只放行列出的域名。Vercel 的预览部署域名每次都不同，
> 预览环境的前端会被跨域拦截，需要时把预览域名也加进去。

## CareerMatch 线上限制

- 批量分析在请求内同步执行，15 个岗位约 35 秒。
  Hobby 套餐函数最长 300 秒，岗位数量大幅增加后可能超时。
- 单次匹配分析约 12 秒，AI 助手 10 到 20 秒，都在时限之内。
