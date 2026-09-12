from typing import Literal, Optional
from pydantic import BaseModel, Field


class Gap(BaseModel):
    gap: str = Field(description="具体差距描述")
    importance: Literal["高", "中", "低"]
    suggestion: str = Field(description="针对这条差距的一句话提升建议")


class ActionItem(BaseModel):
    item: str = Field(description="具体的行动建议，比如做什么项目/学什么/怎么准备面试")
    priority: Literal["high", "medium", "low"]
    resource: Optional[str] = Field(default=None, description="推荐的具体学习资源或行动步骤")


class MatchResult(BaseModel):
    skills_score: int = Field(ge=0, le=100, description="技能匹配度，基于 required_skills/preferred_skills 与候选人 skills 的重合与深度")
    experience_score: int = Field(ge=0, le=100, description="经验匹配度，基于 experience_required 与候选人 experiences 的年限/相关度")
    education_score: int = Field(ge=0, le=100, description="学历匹配度")
    other_score: int = Field(ge=0, le=100, description="其他匹配度：项目、目标城市/公司等契合因素")
    match_score: int = Field(ge=0, le=100, description="综合匹配分")

    matched_skills: list[str] = Field(description="已具备的匹配技能")
    missing_skills: list[str] = Field(description="缺失的必要技能")
    strengths: list[str] = Field(min_length=3, max_length=3, description="候选人优势亮点，正好3条")
    gaps: list[Gap] = Field(min_length=5, max_length=5, description="与岗位的差距，正好5条，按 importance 从高到低排序")
    action_items: list[ActionItem] = Field(min_length=3, max_length=3, description="提升建议，正好3条，按 priority 从高到低排序")
    summary: str = Field(description="100字以内的整体评估总结")



# ---------- B2: 两步拆分 ----------

class GapItem(BaseModel):
    """节点1 产出：只识别差距，不给建议"""
    gap: str = Field(description="具体差距描述，要落到点上（缺什么技能/经验/背景）")
    importance: Literal["高", "中", "低"]


class AnalysisResult(BaseModel):
    """节点1：客观比对"""
    skills_score: int = Field(ge=0, le=100, description="技能匹配度")
    experience_score: int = Field(ge=0, le=100, description="经验匹配度")
    education_score: int = Field(ge=0, le=100, description="学历匹配度")
    other_score: int = Field(ge=0, le=100, description="其他匹配度：项目、目标城市/公司等")
    matched_skills: list[str] = Field(description="已具备的匹配技能")
    missing_skills: list[str] = Field(description="缺失的必要技能")
    strengths: list[str] = Field(min_length=3, max_length=3, description="候选人优势亮点，正好3条")
    gaps: list[GapItem] = Field(min_length=5, max_length=5, description="差距，正好5条，按 importance 从高到低")


class GapWithSuggestion(BaseModel):
    gap: str = Field(description="原样复制输入的差距描述，不要改写")
    importance: Literal["高", "中", "低"]
    suggestion: str = Field(description="针对这条差距的一句话建议，必须结合候选人已有项目或经历")


class ActionItem2(BaseModel):
    item: str = Field(description="具体要做的事，必须有可验证的产出物（代码/数据/上线地址/性能数字），不是'学习X'")
    why_valuable: str = Field(description="这件事对这个岗位为什么有含金量——对应JD里哪条要求，或能证明什么能力")
    priority: Literal["high", "medium", "low"]
    resource: Optional[str] = Field(default=None, description="具体资源或步骤")


class SuggestionResult(BaseModel):
    """节点2：生成建议"""
    gaps: list[GapWithSuggestion] = Field(min_length=5, max_length=5)
    action_items: list[ActionItem2] = Field(
        min_length=1, max_length=3,
        description="只给真正有价值的建议，1-3条。宁可少给，不要为凑数写'去实习''去开源'这类通用建议"
    )
    summary: str = Field(description="100字以内整体评估")


# ---------- 批量结果聚合：missing_skills 归一化 ----------

class SkillMapping(BaseModel):
    index: int = Field(description="对应输入列表中该条目的序号")
    canonical: str = Field(
        description="必须从给定的标准技能词表中原样选一个填入。"
        "如果实在没有任何一个词条能覆盖，填 '其他:<一句话描述>'，不要自己发明新的标准名称。"
    )


class SkillMergeResult(BaseModel):
    mappings: list[SkillMapping] = Field(description="输入列表中每一条都必须有对应映射，不能遗漏")