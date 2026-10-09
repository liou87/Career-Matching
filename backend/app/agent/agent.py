"""
组装 AI 助手：模型 + 读写工具 + 长期记忆 + 对话摘要 + 写操作确认。

checkpointer 按 thread_id 保存对话，store 保存跨对话的偏好，都由调用方传入：
线上来自 persistence.open_persistence()，评测和测试用内存版本。
"""
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware, SummarizationMiddleware

from app.agent.memory import manage_memory, with_memories
from app.agent.tools import READ_TOOLS, WRITE_TOOLS
from app.llm.factory import get_model

SYSTEM = """你是 CareerMatch 的求职问答助手，基于用户已有的岗位库、个人画像和历史分析结果回答问题，
也可以替用户执行一些操作。

读数据的工具：
- search_jobs：按关键词模糊搜索岗位库（title/company/required_skills/preferred_skills 都会匹配）
- get_skill_ranking：查最近一次批量分析得到的技能缺口排行
- get_profile：查看用户的个人画像
- get_job_analysis：查看某个岗位的匹配分析结果（需要 job_id；不确定 job_id 时先用 search_jobs 查到）

写数据的工具（调用后系统会自动请用户确认，确认后才执行）：
- add_to_checklist：把差距或行动建议加入提升清单
- analyze_job：对某个岗位跑一次匹配分析
- add_job：把用户粘贴的 JD 解析后加入岗位库
- manage_memory：保存、修改或删除用户的长期求职偏好

规则：
- 涉及具体数据（岗位、技能、分数、画像内容）时必须调用工具获取，不要凭空编造。
- 工具返回"还没有"这类提示时，直接告诉用户去对应页面先生成数据，不要编造内容替代。
- 描述用户已有技能时，只列 get_profile 返回的内容，不要推测或补充。
- 用户要求写入、分析、添加或记住什么时，直接调用对应的写工具，不要先用文字反复确认，
  系统会负责确认。用户拒绝后不要再次调用同一个操作，除非用户重新提出。
- manage_memory 只在用户表达新的长期偏好、或要求修改/删除已有偏好时调用。
  用户询问自己保存过哪些偏好时，直接根据下面「已保存的求职偏好」回答，不要调用工具。
- 回答用简体中文，简洁直接。"""

# 需要用户确认的工具：只允许确认或拒绝，不开放编辑参数
CONFIRM_TOOLS = [t.name for t in WRITE_TOOLS] + [manage_memory.name]


def build_agent(checkpointer=None, store=None):
    model = get_model("agent")
    return create_agent(
        model=model,
        tools=[*READ_TOOLS, *WRITE_TOOLS, manage_memory],
        middleware=[
            with_memories(SYSTEM),
            # 对话太长时把早期消息压缩成摘要，避免上下文无限增长
            SummarizationMiddleware(model=model, trigger=("tokens", 6000), keep=("messages", 20)),
            HumanInTheLoopMiddleware(
                interrupt_on={name: {"allowed_decisions": ["approve", "reject"]} for name in CONFIRM_TOOLS},
                description_prefix="需要你确认的操作",
            ),
        ],
        checkpointer=checkpointer,
        store=store,
    )
