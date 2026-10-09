"""
长期记忆：用 LangMem 的 manage_memory 工具保存求职偏好（跨对话保留），存在 LangGraph Store 里。

- 写入：助手在对话里发现长期偏好时调用 manage_memory，和其他写操作一样先经用户确认。
- 读取：偏好条数很少，每轮对话把全部偏好注入系统提示，不做语义检索
  （DeepSeek 不提供 embedding 接口，接入 embedding 服务后可以改成按相关性检索）。
"""
from langchain.agents.middleware import ModelRequest, dynamic_prompt
from langgraph.store.base import BaseStore
from langmem import create_manage_memory_tool

NAMESPACE = ("preferences",)

manage_memory = create_manage_memory_tool(
    namespace=NAMESPACE,
    instructions=(
        "用户表达了长期有效的求职偏好时调用，比如只看某些城市、不考虑外包或某类公司、"
        "期望的岗位方向或薪资底线，或者明确说「记住」。一次性的提问不要保存。"
        "已有偏好过时或被用户推翻时用 update 或 delete。调用后系统会先请用户确认。"
    ),
)


def list_memories(store: BaseStore | None) -> list[dict]:
    if store is None:
        return []
    items = store.search(NAMESPACE, limit=100)
    return [
        {"id": i.key, "content": i.value.get("content"), "updated_at": i.updated_at.isoformat()}
        for i in sorted(items, key=lambda i: i.created_at)
    ]


def memory_section(store: BaseStore | None) -> str:
    memories = list_memories(store)
    if not memories:
        return ""
    lines = "\n".join(f"- {m['content']}（id: {m['id']}）" for m in memories)
    return f"\n\n用户已保存的求职偏好（回答、搜索和推荐时都要遵守）：\n{lines}"


def with_memories(base_prompt: str):
    """返回一个动态系统提示中间件：基础提示 + 当前已保存的偏好。"""

    @dynamic_prompt
    def prompt(request: ModelRequest) -> str:
        return base_prompt + memory_section(request.runtime.store)

    return prompt
