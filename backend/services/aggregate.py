"""
把批量分析结果（多个岗位各自的 missing_skills）合并成一份"高频差距排行榜"。

同一个技能缺口经常被 LLM 用不同措辞描述（比如"缺LangChain经验"和"未掌握
LangGraph等Agent框架"），直接按字符串去重/计数会把同一个技能拆成好几条。
这里用一次 LLM 调用把所有 missing_skills 归到一份固定的标准词表
（CANONICAL_SKILLS）上，再在 Python 里按标准名聚合统计——LLM 只做
"从词表里选一个"这一件事（选择题比自由生成更稳定，两次跑的结果更容易
一致），category 也不再让 LLM 判断，而是从词表反查，统计逻辑完全
确定性，不受 LLM 输出方式影响。
"""
import json
from collections import defaultdict

from dotenv import load_dotenv
from langchain_deepseek import ChatDeepSeek
from langchain_core.prompts import ChatPromptTemplate

from .schemas import SkillMergeResult

# 这个模块不再 import ai_service，之前是靠那边的 import 链间接触发
# load_dotenv() 才能读到 DEEPSEEK_API_KEY，现在要自己重新加载一次。
load_dotenv()

# 不复用 ai_service.llm：那边 max_tokens=2048 是按单个岗位的匹配分析输出量
# 定的，这里一次要归并几十条 missing_skills（比如 15 个岗位约 75 条），
# 输出规模不是一个量级（约 3000 token），复用会被截断。
merge_llm = ChatDeepSeek(model="deepseek-chat", max_tokens=8192, temperature=0)

CANONICAL_SKILLS = [
    "RAG", "Multi-Agent协作", "LangChain/LangGraph", "MCP",
    "向量数据库与Embedding", "Function/Tool Calling", "Agent记忆机制",
    "Java", "Golang", "TypeScript",
    "MySQL", "Redis", "Elasticsearch", "消息队列",
    "Docker/K8s", "微服务与分布式", "系统设计", "评测体系",
    "多模态", "大数据处理", "云平台",
]

# category 不再让 LLM 判断，固定从这份词表反查——canonical 是封闭词表，
# 这里跟它一一对应即可。
CANONICAL_CATEGORY = {
    "RAG": "框架工具",
    "Multi-Agent协作": "框架工具",
    "LangChain/LangGraph": "框架工具",
    "MCP": "框架工具",
    "向量数据库与Embedding": "框架工具",
    "Function/Tool Calling": "框架工具",
    "Agent记忆机制": "框架工具",
    "Java": "语言技能",
    "Golang": "语言技能",
    "TypeScript": "语言技能",
    "MySQL": "框架工具",
    "Redis": "框架工具",
    "Elasticsearch": "框架工具",
    "消息队列": "框架工具",
    "Docker/K8s": "框架工具",
    "微服务与分布式": "工程能力",
    "系统设计": "工程能力",
    "评测体系": "工程能力",
    "多模态": "领域知识",
    "大数据处理": "工程能力",
    "云平台": "工程能力",
}


def _category_for(canonical: str) -> str:
    if canonical in CANONICAL_CATEGORY:
        return CANONICAL_CATEGORY[canonical]
    return "其他"


MERGE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "你负责把一批技能缺口描述归类到一份固定的标准词表上。"),
    ("user", """下面是一批"缺失技能"描述，每条都有一个序号（index）：
{items}

标准技能词表（canonical 必须从这里面原样选一个）：
{canonical_skills}

要求：
- 给列表里每一条都从上面的标准词表里选一个最贴切的 canonical 填入，必须原样使用词表里的写法，不要改写、不要自己发明新名称。
- 如果某一条实在没有任何一个词条能覆盖，canonical 填 "其他:<一句话描述>"。
- index 必须跟输入列表的序号一一对应，不能遗漏任何一条。"""),
])

merge_chain = MERGE_PROMPT | merge_llm.with_structured_output(SkillMergeResult)


def aggregate_gaps(batch_results: list[dict]) -> list[dict]:
    # 1. 收集所有 missing_skills，带 job_id 和序号
    items = []
    for r in batch_results:
        if "error" in r:
            continue
        for s in r.get("missing_skills", []):
            items.append({"index": len(items), "job_id": r["job_id"], "text": s})

    # 2. 一次 LLM 调用做映射（从固定词表里选，不是自由生成）
    mapping = merge_chain.invoke({
        "items": json.dumps(items, ensure_ascii=False),
        "canonical_skills": json.dumps(CANONICAL_SKILLS, ensure_ascii=False),
    })

    # 3. 校验：LLM 遗漏条目是这类任务最常见的失败模式
    if len(mapping.mappings) != len(items):
        raise ValueError(
            f"skill mapping 数量不一致：输入 {len(items)} 条，返回 {len(mapping.mappings)} 条"
        )

    # 数量对了不代表索引对——LLM 可能把某个 index 写重复、另一个漏掉，
    # 重复索引会在下面的统计里静默覆盖/丢数据，必须单独查
    seen_indexes = set()
    for m in mapping.mappings:
        if not (0 <= m.index < len(items)):
            raise ValueError(f"skill mapping 里有越界的 index: {m.index}（输入范围 0~{len(items) - 1}）")
        if m.index in seen_indexes:
            raise ValueError(f"skill mapping 里有重复的 index: {m.index}")
        seen_indexes.add(m.index)

    # 4. Python 统计，category 从词表反查，不依赖 LLM 判断
    buckets = defaultdict(lambda: {"jobs": set(), "originals": []})
    for m in mapping.mappings:
        src = items[m.index]
        b = buckets[m.canonical]
        b["jobs"].add(src["job_id"])
        b["originals"].append(src["text"])

    return sorted(
        [{"skill": k, "job_count": len(v["jobs"]), "category": _category_for(k),
          "originals": v["originals"]} for k, v in buckets.items()],
        key=lambda x: -x["job_count"],
    )
