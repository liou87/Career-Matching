# CareerMatch

CareerMatch（求职助手）用 AI 管理求职全流程：维护个人画像，
粘贴 JD 自动解析入库，逐岗位做匹配分析，汇总所有岗位的技能缺口，
并把待提升项沉淀成一份可勾选的清单。

## CareerMatch 功能

- **个人画像**：教育、技能、实习/工作经历、项目、目标岗位/城市/公司，
  贯穿后续所有分析。
- **岗位库**：粘贴 JD 全文，AI 解析出职位、公司、城市、薪资、
  必备/加分技能、经验学历要求和职责。可按画像里的目标岗位和城市，
  一键打开拉勾、Boss直聘、前程无忧的搜索结果。
- **匹配分析**：输出匹配分（0-100）、已匹配/缺失技能、优势、差距
  和按优先级排序的行动建议。画像和岗位都没变时直接复用上次结果。
- **技能缺口总览**：对岗位库批量跑分析，用 LLM 合并同义技能，
  按“多少个岗位缺这项技能”排序。
- **提升清单**：从分析结果里勾选差距或行动建议存进清单，
  分栏展示，可标记完成、编辑、删除。
- **AI 助手**：对话式问答，Agent 通过工具查询岗位库、画像、
  单岗分析和技能缺口排行，回答“我现在最该学什么”这类问题。

## CareerMatch 技术栈

- **后端**：FastAPI、SQLAlchemy，本地用 SQLite，线上用 Postgres；
  AI 部分用 LangChain 和 LangGraph，模型走 DeepSeek。
- **前端**：React 19、TypeScript、Vite、React Router、axios。

## CareerMatch 目录结构

```text
backend/
  main.py                  # FastAPI 入口
  models.py / schemas.py   # SQLAlchemy 表 / Pydantic 模型
  routers/                 # profile / jobs / analysis / checklist / agent
  services/
    ai_service.py          # JD 解析；匹配分析 v1、v2（对照实验保留）
    graph.py               # 匹配分析 v3（LangGraph，当前线上版本）
    batch_graph.py         # 批量分析与技能合并
    job_agent.py           # AI 助手 Agent 与工具
  evals/                   # 各版本对比评测脚本与结果
  scripts/                 # SQLite 数据迁移到 Postgres
frontend/
  src/pages/               # 各页面
  src/api.ts               # axios 实例
docs/deploy.md             # Vercel 部署说明
start.bat                  # Windows 下一键启动前后端
```

## 在本地运行 CareerMatch

### 启动后端

```bash
cd backend
pip install -r requirements.txt
```

参考 `.env.example` 新建 `backend/.env`，填入 DeepSeek API Key：

```dotenv
DEEPSEEK_API_KEY=sk-xxxxxx
```

> [!NOTE]
> Key 从 [platform.deepseek.com](https://platform.deepseek.com/) 获取，
> 需要单独绑定支付方式。没有 Key 时 JD 解析、匹配分析、
> 技能缺口总览和 AI 助手不可用，个人画像和清单不受影响。

```bash
uvicorn main:app --reload --port 8000
```

### 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问 <http://localhost:5173>，前端请求 <http://localhost:8000> 的后端接口。

## 部署 CareerMatch

前后端分别部署为两个 Vercel 项目，数据库用 Neon Postgres，
公网访问需要口令。步骤见 [docs/deploy.md](docs/deploy.md)。

## CareerMatch 接口

| 方法           | 路径                        | 说明                           |
| -------------- | --------------------------- | ------------------------------ |
| GET / PUT      | `/profile`                  | 获取/更新个人画像              |
| GET / POST     | `/jobs`                     | 岗位列表 / 粘贴 JD 解析入库    |
| GET / DELETE   | `/jobs/{id}`                | 岗位详情 / 软删除              |
| POST           | `/analysis/{job_id}`        | 匹配分析，`?force=true` 强制重跑 |
| GET            | `/analysis/{job_id}/latest` | 该岗位最近一次分析结果         |
| POST           | `/analysis/batch`           | 发起批量分析，返回 `task_id`   |
| GET            | `/analysis/batch/{task_id}` | 轮询批量分析状态               |
| GET            | `/analysis/batch/latest`    | 最近一次完成的技能缺口排行     |
| GET / POST     | `/checklist`                | 清单列表 / 批量新增            |
| PATCH / DELETE | `/checklist/{id}`           | 更新状态或内容 / 删除          |
| POST           | `/agent/chat`               | AI 助手对话                    |

## 匹配分析的版本演进

用 15 个真实岗位实测，评测脚本在 `backend/evals/`：

| 指标                 | v1 单 prompt          | v2 两步链    | v3 LangGraph       |
| -------------------- | --------------------- | ------------ | ------------------ |
| match_score 计算错误 | 7/15                  | 0/15         | 0/15               |
| 成功率               | 15/15                 | 14/15        | 15/15              |
| 平均耗时             | ~6s                   | ~12s         | ~12s（排除岗 ~4s） |
| 平均 token           | ~2.5K                 | ~4.7K        | ~4.7K              |
| 建议质量             | “系统学习 LangChain” | 绑定已有项目 | 同左               |

## CareerMatch 已知局限

- 单用户设计，没有账号体系，`/profile` 始终操作同一条记录。
  线上只靠一个访问口令保护。
- 新增数据库列不会自动迁移：`create_all` 只建新表，不给已有表补列，
  旧库升级后需要手动 `ALTER TABLE`。
- 批量分析在请求内同步执行，岗位很多时可能超过 Vercel 函数时限。
