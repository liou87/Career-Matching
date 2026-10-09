"""测试用的假链和假数据，代替真实的 LLM 调用。"""
from app.llm.schemas import (
    ActionItem2,
    AnalysisResult,
    GapItem,
    GapWithSuggestion,
    SuggestionResult,
)


class FakeChain:
    """按顺序返回预设结果；预设值是异常就抛出，最后一个结果会一直重复。"""

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    def invoke(self, payload, *args, **kwargs):
        self.calls.append(payload)
        out = self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]
        if isinstance(out, BaseException):
            raise out
        return out


def make_analysis(skills=80, experience=70, education=60, other=50) -> AnalysisResult:
    return AnalysisResult(
        skills_score=skills,
        experience_score=experience,
        education_score=education,
        other_score=other,
        matched_skills=["Python", "FastAPI"],
        missing_skills=["RAG", "K8s"],
        strengths=["优势1", "优势2", "优势3"],
        gaps=[GapItem(gap=f"差距{i}", importance="高") for i in range(5)],
    )


def make_suggestion(n_actions=2) -> SuggestionResult:
    return SuggestionResult(
        gaps=[GapWithSuggestion(gap=f"差距{i}", importance="高", suggestion=f"建议{i}") for i in range(5)],
        action_items=[
            ActionItem2(item=f"行动{i}", why_valuable="理由", priority="high") for i in range(n_actions)
        ],
        summary="总结",
    )


def fake_match_result(skills=80, experience=70, education=60, other=50) -> dict:
    """analyze_match_v3 的返回值。match_score 故意给错，用来验证接口层会按子分重算。"""
    return {
        "match_score": 0,
        "score_breakdown": {
            "skills": skills, "experience": experience, "education": education, "other": other,
        },
        "matched_skills": ["Python"],
        "missing_skills": ["RAG"],
        "strengths": ["a", "b", "c"],
        "gaps": [{"gap": "g", "importance": "高", "suggestion": "s"}],
        "action_items": [{"item": "i", "why_valuable": "w", "priority": "high", "resource": None}],
        "summary": "总结",
    }
