# CareerMatch 接口

所有接口都带 `/api` 前缀，例如 `/api/jobs`。健康检查是 `/api/health`。
配置了 `ACCESS_TOKEN` 时，请求头要带 `X-Access-Token`（值做 URL 编码）。

配置口令后默认是只读演示：GET 请求公开，其他请求要口令。
调用 AI 的接口还受 IP 限流和每日 token 预算约束，超出时分别返回
`429 RATE_LIMITED` 和 `503 BUDGET_EXCEEDED`。

错误响应统一为 `{"detail": 提示, "code": 错误码, "request_id": ...}`，
LLM 相关的错误码有 `LLM_TIMEOUT`、`LLM_RATE_LIMITED`、`LLM_QUOTA`、
`LLM_BAD_OUTPUT` 等，见 `backend/app/core/errors.py`。

## CareerMatch 数据接口

| 方法           | 路径                        | 说明                             |
| -------------- | --------------------------- | -------------------------------- |
| GET / PUT      | `/profile`                  | 获取/更新个人画像                |
| GET / POST     | `/jobs`                     | 岗位列表 / 粘贴 JD 解析入库      |
| GET / DELETE   | `/jobs/{id}`                | 岗位详情 / 软删除                |
| POST           | `/analysis/{job_id}`        | 匹配分析，`?force=true` 强制重跑 |
| GET            | `/analysis/{job_id}/latest` | 该岗位最近一次分析结果           |
| POST           | `/analysis/batch`           | 发起批量分析，返回 `task_id`     |
| GET            | `/analysis/batch/{task_id}` | 轮询批量分析状态                 |
| GET            | `/analysis/batch/latest`    | 最近一次完成的技能缺口排行       |
| GET / POST     | `/checklist`                | 清单列表 / 批量新增              |
| PATCH / DELETE | `/checklist/{id}`           | 更新状态或内容 / 删除            |
| POST           | `/interview/{job_id}`       | 生成面试题，`?force=true` 重新生成 |
| GET            | `/interview/{job_id}/latest`| 该岗位最近一次的面试题           |
| GET            | `/metrics?days=7`           | 线上 LLM 调用指标                |

## CareerMatch AI 助手接口

| 方法   | 路径                         | 说明                                   |
| ------ | ---------------------------- | -------------------------------------- |
| POST   | `/agent/chat`                | 发消息，SSE 流式返回                   |
| POST   | `/agent/resume`              | 确认或取消待确认的写操作，SSE 流式返回 |
| GET    | `/agent/threads/{thread_id}` | 恢复对话历史和待确认的操作             |
| GET    | `/agent/memories`            | 已保存的长期偏好                       |
| DELETE | `/agent/memories/{id}`       | 删除一条偏好                           |

`/agent/chat` 的请求体是 `{"message": "...", "thread_id": "..."}`，
不传 `thread_id` 就开一个新对话。`/agent/resume` 的请求体是
`{"thread_id": "...", "approve": true}`。

流式响应每行一个 `data: {json}` 事件：

- `thread`：本轮所属的对话 id，第一个事件。
- `token`：回答的一段文字。
- `tool_call`：助手发起了一次工具调用，带工具名和参数。
- `tool_result`：工具执行完成。
- `interrupt`：有写操作等待确认，带操作列表。
- `done`：本轮结束。
- `error`：出错，带错误码和提示。有待确认的操作时再发消息，错误码是 `CONFLICT`。
