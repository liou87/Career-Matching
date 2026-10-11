# CareerMatch 路线图

本项目定位为 AI Agent / LLM 应用开发方向的作品集。差异化不在功能数量，
而在「评测驱动的匹配分析」和「跨岗位技能缺口聚合」。每一步都让这两点
更深、更可证明，而不是堆更多页面。

每个阶段的完成标准：CI 通过、线上已部署、README 和 `docs/` 里的数据已更新。
工期按每天 3 到 4 小时粗估。

## CareerMatch 参考项目

| 项目                                                                                   | 借鉴点                                                 |
| -------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| [full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template) | pydantic-settings、pytest + GitHub Actions、Alembic    |
| [Langfuse](https://github.com/langfuse/langfuse)                                       | LLM 链路追踪、prompt 版本、评测数据集（与 LangSmith 二选一） |
| [Resume-Matcher](https://github.com/srbhr/Resume-Matcher)                              | 同领域产品；LiteLLM 多模型、Docker 单容器部署          |
| [DeepEval](https://github.com/confident-ai/deepeval)                                   | pytest 风格的 LLM 测试，Tool Correctness 指标          |
| [open_deep_research](https://github.com/langchain-ai/open_deep_research)               | 按角色配置模型、LangSmith 数据集 + LLM 打分            |
| [LangMem](https://github.com/langchain-ai/langmem)                                     | 与 LangGraph Store 集成的长期记忆                      |

## 第一阶段：工程底座

预计 4 天。

- [x] 目录重组为 `backend/app/` 包：`core`、`db`、`api`、`llm`、`graphs`、
  `agent`、`services`
- [x] `pydantic-settings` 集中配置：模型名、max_tokens、超时、权重、排除技能；
  评分权重只保留一份
- [x] LLM 工厂 `get_model(role)`：按角色配置模型，换模型只改配置；
  `parse_jd` 改为 `with_structured_output` 校验
- [x] 全局错误处理：LLM 超时返回 504、上游失败返回 502，带错误码
- [x] 结构化日志：request_id 中间件；每次 LLM 调用记录角色、模型、耗时、token
- [x] 接入 LangSmith：本地和线上都已验证，请求结束前等 trace 上传完
- [x] Alembic 迁移取代 `create_all`
- [x] pytest 覆盖确定性逻辑（39 个用例，覆盖率 89%）；
  GitHub Actions 跑 ruff、pytest、前端构建

验收：CI 通过；任意一次分析都能在 LangSmith 看到完整 trace。

## 第二阶段：评测体系升级

预计 3 天。

- [x] 15 个岗位脱敏后作为固定评测集，可作为实验上传 LangSmith 对比各版本
- [x] 新增指标：稳定性（同岗位 3 次的分数波动）、编造率（裁判模型判断，
  已用构造样本校验）
- [x] 差距识别准确率：裁判自动检查（摘录 JD 原文后分类），附裁判校验集
- [ ] 差距识别召回率：计算已就绪，待人工校对 `labels.json`
- [x] 线上指标：`llm_calls` 表 + `/api/metrics`，成功率、P50/P95 耗时、单次成本
- [x] 确定性测试每次 push 都跑；花钱的 LLM 评测改为手动触发
- [x] 评测发现并修复规则筛选误排除两个目标岗位的问题
- [x] 迁移出已弃用的 `deepseek-chat` 别名，改用 `deepseek-flash` 并关闭思考模式

验收：`docs/evals.md` 写明指标定义、数值和版本间的改进幅度。

## 第三阶段：Agent 做深

预计 5 天。

- [x] 先建评测基线：30 道单轮 + 5 道多轮，统计工具选择、参数、写操作确认、
  回答依据率（裁判已校验）
- [x] 短期记忆：LangGraph checkpointer（线上 Postgres、本地 SQLite），
  按 thread_id 持久化，超长自动摘要
- [x] 长期记忆：LangMem 保存求职偏好，保存前需确认，每轮注入系统提示
- [x] SSE 流式输出回答和工具调用过程
- [x] 写操作工具（加入清单、分析岗位、添加岗位、保存偏好）执行前
  经 HumanInTheLoopMiddleware 等用户确认
- [x] 自检节点改为 prompt 约束：编造率已是 0，自检节点测不出收益；
  针对评测发现的「多选一误读」在 v3 分析 prompt 里加约束，用误报缺失率衡量

验收：Agent 指标有前后对比；prompt 约束对误报缺失率的影响有数字。

## 第四阶段：岗位库 RAG

预计 3 天。

- [x] embedding 选用硅基流动 bge-m3；向量存普通列、Python 计算相似度
  （岗位规模小，本地和线上同一套代码；规模变大再换 pgvector）
- [x] 混合检索：jieba 分词 + BM25 与向量检索，用 RRF 融合
- [x] 20 个查询（规则推导 + 裁判标注），对比子串、BM25、向量、混合的 recall@5
- [x] 线上默认只用 BM25（recall@5 0.963，混合 0.943，向量 0.792），
  向量保留为可选（`SEARCH_MODE=hybrid`）
- [x] 搜索结果附带命中的片段原文，助手据此回答
- [x] 补齐第三阶段评测发现的工具能力缺口：按城市筛选岗位、统计岗位总数、
  汇总所有岗位的匹配分

验收：三种检索方式的召回率对比表。

## 第五阶段：上线收尾

预计 2 天。

- [x] 只读演示模式：配置口令后浏览公开，调用 AI 和写数据需要口令
- [x] 基于数据库的 IP 限流（10 分钟 20 次）和每日 token 预算（200 万）
- [x] Docker Compose 一键启动应用和 Postgres，由 CI 构建并做冒烟测试
- [x] 文档：Mermaid 架构图、`docs/evals.md`、设计决策记录
- [x] 面试题：从 JD 出发，用优势和差距排优先级，附评测

## CareerMatch 明确不做的事

- 多角色登录：单用户产品，没有实际需求。
- 为了多 Agent 而拆 Agent：单图加自检节点已经够用。
- Celery 或消息队列：Vercel 不支持常驻 worker，批量分析只需约 35 秒。
- K8s、政企私有化、全套标书文档。
