# CareerMatch

[![CI](https://img.shields.io/github/actions/workflow/status/liou87/Career-Matching/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/liou87/Career-Matching/actions/workflows/ci.yml)

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
- **AI 助手**：流式对话，Agent 通过工具查询岗位库、画像、分析和排行，
  也能替你加清单、分析岗位、添加岗位、记住求职偏好，写操作都要你确认。
  对话刷新后可恢复，偏好跨对话保留。

## CareerMatch 技术栈

- **后端**：FastAPI、SQLAlchemy，本地用 SQLite，线上用 Postgres；
  AI 部分用 LangChain 和 LangGraph（checkpointer、人工确认中断），
  长期记忆用 LangMem，模型走 DeepSeek。
- **工程**：pydantic-settings 集中配置、Alembic 迁移、结构化日志、
  pytest、ruff、GitHub Actions。
- **前端**：React 19、TypeScript、Vite、React Router、axios。

## CareerMatch 目录结构

```text
backend/
  main.py                  # 部署入口，转发到 app/main.py
  app/
    core/config.py         # 集中配置，环境变量可覆盖
    api/                   # profile / jobs / analysis / checklist / agent / metrics
    db/                    # SQLAlchemy 表与连接
    llm/                   # 模型工厂、链、结构化输出；legacy.py 为 v1/v2 对照实验
    graphs/                # 匹配分析 v3 与批量分析（LangGraph）
    services/              # JD 解析、评分、技能归并
    agent/                 # AI 助手：工具、记忆、持久化、流式输出
  evals/                   # 离线评测框架、评测集与结果
  scripts/                 # SQLite 数据迁移到 Postgres
frontend/
  src/pages/               # 各页面
  src/api.ts               # axios 实例
docs/                      # 部署、接口、评测、路线图
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

首次运行或拉取新代码后先执行数据库迁移，再启动服务（`start.bat` 已包含）：

```bash
alembic upgrade head
uvicorn main:app --reload --port 8000
```

### 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问 <http://localhost:5173>。Vite 会把 `/api` 请求代理到
<http://localhost:8000> 的后端，所以要先启动后端。

## 测试 CareerMatch

```bash
cd backend
pip install -r requirements-dev.txt
ruff check .
pytest --cov=app
```

测试里的 LLM 调用全部替换成假链，不需要 API Key，也不会产生费用。
每次 push 都会在 GitHub Actions 上跑后端测试和前端构建。

## 部署 CareerMatch

前后端用 Vercel Services 部署在同一个项目里，数据库用 Neon Postgres，
公网访问需要口令。步骤见 [docs/deploy.md](docs/deploy.md)。

## CareerMatch 接口

所有接口都带 `/api` 前缀，AI 助手走 SSE 流式返回。
完整列表和事件格式见 [docs/api.md](docs/api.md)。

## 匹配分析的版本演进

15 个真实岗位各跑 3 次，模型 `deepseek-flash`，v3 为当前线上版本。
指标定义和完整数据见 [docs/evals.md](docs/evals.md)。

| 指标             | v1 单 prompt | v2 两步链 | v3 LangGraph |
| ---------------- | ------------ | --------- | ------------ |
| 分数算错         | 28 / 45      | 0 / 45    | 0 / 45       |
| 空泛建议         | 6 / 135      | 0 / 135   | 0 / 99       |
| 耗时 P50         | 6.3s         | 10.6s     | 9.9s         |
| 单次成本（美元） | 0.0016       | 0.0027    | 0.0022       |
| 差距有效率       | 96.2%        | 95.3%     | 99.2%        |

评测还发现并修复了两个问题：规则筛选把两个目标岗位误判为技术栈不符；
分析模型把多选一要求里的其他选项列为缺失。

AI 助手另有 35 道题的评测：改造后通过率从 63% 升到 86%，
写操作先确认从 0/8 到 8/8，偏好记忆从 0/3 到 3/3。

## CareerMatch 已知局限

- 单用户设计，没有账号体系，`/profile` 始终操作同一条记录。
  线上只靠一个访问口令保护。
- 批量分析在请求内同步执行，岗位很多时可能超过 Vercel 函数时限。
