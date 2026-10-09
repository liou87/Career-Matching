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

- [ ] 先建评测基线：30 个问题标注预期工具和参数，统计工具选择准确率和
  回答依据率
- [ ] 短期记忆：LangGraph `PostgresSaver`，按 thread_id 持久化，超长自动摘要
- [ ] 长期记忆（可选）：LangMem 记住求职偏好，检索时自动带上
- [ ] SSE 流式输出回答和工具调用过程
- [ ] 写操作工具（加入清单、发起分析）执行前用 `interrupt` 等用户确认
- [ ] 匹配分析加自检节点：建议必须引用真实项目且不空泛，不合格带反馈
  重试一次，用编造率衡量效果

验收：Agent 指标有前后对比；自检节点使编造率下降的幅度有数字。

## 第四阶段：岗位库 RAG

预计 3 天。

- [ ] Neon 启用 pgvector；选一家 embedding API（DeepSeek 目前不提供）
- [ ] 混合检索：jieba 分词 + BM25 与向量检索融合
- [ ] 标注 20 个查询，对比关键词、向量、混合三种方式的 recall@5
- [ ] Agent 回答附带引用的 JD 原文片段

验收：三种检索方式的召回率对比表。

## 第五阶段：上线收尾

预计 2 天。

- [ ] 只读演示模式：浏览公开，调用 LLM 和写数据需要口令
- [ ] 基于 Postgres 的限流和每日 token 预算熔断
- [ ] Docker Compose 一键启动应用和 Postgres
- [ ] 文档：Mermaid 架构图、`docs/evals.md`、关键决策的 ADR
- [ ] 可选：根据技能差距生成面试题

## CareerMatch 明确不做的事

- 多角色登录：单用户产品，没有实际需求。
- 为了多 Agent 而拆 Agent：单图加自检节点已经够用。
- Celery 或消息队列：Vercel 不支持常驻 worker，批量分析只需约 35 秒。
- K8s、政企私有化、全套标书文档。
