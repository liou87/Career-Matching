import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)
MODEL = "deepseek-chat"


def _ask_json(prompt: str, max_tokens: int) -> dict:
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def parse_jd(raw_jd: str) -> dict:
    prompt = f"""请解析以下招聘JD，提取结构化信息，返回严格的JSON格式，不要有任何多余文字。

JD原文：
{raw_jd}

返回格式：
{{
  "title": "职位名称",
  "company": "公司名称",
  "city": "城市（多城市用逗号分隔）",
  "salary_min": 月薪下限（整数，单位千元，无法确定填null）,
  "salary_max": 月薪上限（整数，单位千元，无法确定填null）,
  "required_skills": ["必须技能1", "必须技能2"],
  "preferred_skills": ["加分技能1", "加分技能2"],
  "experience_required": "经验要求，如'1-3年'或'应届生可'",
  "education_required": "学历要求，如'本科及以上'",
  "responsibilities": ["职责1", "职责2", "职责3"]
}}"""

    return _ask_json(prompt, 1024)


def analyze_match(profile: dict, job: dict) -> dict:
    prompt = f"""你是一个专业的求职顾问，请分析以下候选人与岗位的匹配情况。

候选人信息：
{json.dumps(profile, ensure_ascii=False, indent=2)}

目标岗位：
{json.dumps(job, ensure_ascii=False, indent=2)}

请返回严格的JSON格式，不要有任何多余文字：
{{
  "match_score": 0到100的整数（综合匹配分）,
  "matched_skills": ["已具备的匹配技能"],
  "missing_skills": ["缺失的必要技能"],
  "strengths": ["候选人的优势亮点（2-4条）"],
  "gaps": ["主要差距（2-4条）"],
  "suggestions": [
    {{
      "item": "具体提升建议",
      "priority": "high/medium/low",
      "resource": "推荐学习资源或行动（可选）"
    }}
  ],
  "summary": "100字以内的整体评估总结"
}}"""

    return _ask_json(prompt, 2048)
