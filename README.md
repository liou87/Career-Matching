# CareerMatch（求职助手）

用 AI 帮你管理求职全流程：维护个人画像、粘贴 JD 自动解析入库、AI 匹配分析给出差距和行动建议，并把待提升项沉淀成一份可勾选打勾的清单。

## 功能

- **个人画像**：录入教育经历、技能、实习/工作经历、项目经历、目标岗位/城市/公司，一份画像贯穿后续所有分析。
- **岗位库**：粘贴招聘网站上的 JD 全文，AI 自动解析出职位、公司、城市、薪资范围、必备/加分技能、经验学历要求、职责；点进岗位卡片可看详情和 JD 原文。
- **匹配分析**：针对画像 + 目标岗位调用 AI，输出匹配分（0-100）、已匹配/缺失技能、3 条优势、5 条差距（含重要程度和一句话建议）、3 条按优先级排序的行动建议。
- **提升清单**：在差距分析里勾选想跟进的条目，一键存进清单；清单页可以标记完成、编辑内容、删除。

## 技术栈

- **后端**：FastAPI + SQLAlchemy + SQLite，AI 调用走 DeepSeek（OpenAI 兼容接口）
- **前端**：React 19 + TypeScript + Vite + React Router + axios

## 项目结构

```
backend/
  main.py              # FastAPI 入口
  models.py            # SQLAlchemy 表：Profile / Job / Analysis / Checklist
  schemas.py           # Pydantic 请求/响应模型
  database.py          # SQLite 连接
  routers/             # profile / jobs / analysis / checklist 四组接口
  services/ai_service.py  # 封装 DeepSeek 调用（JD 解析、匹配分析）

frontend/
  src/pages/           # ProfilePage / JobsPage / JobDetailPage / AnalysisPage / ChecklistPage
  src/api.ts           # axios 实例
```

## 本地运行

### 后端

```bash
cd backend
pip install -r requirements.txt
```

新建 `backend/.env`（参考 `.env.example`），填入你的 DeepSeek API Key：

```
DEEPSEEK_API_KEY=sk-xxxxxx
```

Key 从 [platform.deepseek.com](https://platform.deepseek.com/) 获取，需要单独绑定支付方式。没有这个 key，「岗位库」的 JD 解析和「匹配分析」这两个 AI 功能不可用，其余功能（个人画像、清单）不受影响。

```bash
uvicorn main:app --reload --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

默认访问 http://localhost:5173 ，前端会请求 http://localhost:8000 的后端接口。

## 接口一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET / PUT | `/profile` | 获取/更新个人画像（单用户，无登录体系） |
| GET / POST | `/jobs` | 岗位列表 / 粘贴 JD 触发 AI 解析入库 |
| GET / DELETE | `/jobs/{id}` | 岗位详情 / 软删除 |
| POST | `/analysis/{job_id}` | 触发一次匹配分析 |
| GET | `/analysis/{job_id}/latest` | 获取该岗位最近一次分析结果 |
| GET / POST | `/checklist` | 清单列表 / 批量新增条目 |
| PATCH / DELETE | `/checklist/{id}` | 更新状态或内容 / 删除条目 |

## 已知局限

- 单用户设计，没有账号体系，`/profile` 始终操作同一条记录。
- 数据存在本地 SQLite 文件（`backend/job_helper.db`），部署到无持久化磁盘的平台（如 Render/Vercel 的无状态服务）会在重启后丢数据，需要挂载持久化卷或换成 Postgres。
