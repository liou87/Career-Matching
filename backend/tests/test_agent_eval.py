"""AI 助手评测的判分逻辑（evals/agent_metrics.py、evals/agent_judge.py），都是纯函数。"""
from evals.agent_judge import _consistent, context_from_turns
from evals.agent_metrics import check_case, summarize


def _turn(answer="", tools=(), interrupt=None):
    return {"answer": answer, "tool_calls": [{"name": n, "args": a} for n, a in tools],
            "tool_outputs": [], "interrupt": interrupt, "message": "q", "latency_ms": 100}


def test_tools_args_and_mentions():
    case = {"expect": {"tools": ["get_job_analysis"], "args": {"get_job_analysis": {"job_id": 4}},
                       "mention": ["73"]}}
    good = _turn("匹配分 73", [("search_jobs", {"keyword": "快手"}), ("get_job_analysis", {"job_id": 4})])
    wrong_id = _turn("匹配分 73", [("get_job_analysis", {"job_id": 5})])

    assert check_case(case, good, [good]) == {"tools": True, "args": True, "confirm": True, "mention": True}
    assert check_case(case, wrong_id, [wrong_id])["args"] is False


def test_write_must_stop_for_confirmation():
    case = {"expect": {"interrupt": "analyze_job", "args": {"analyze_job": {"job_id": 13}}}}
    confirmed = _turn(interrupt={"name": "analyze_job", "args": {"job_id": 13}})
    executed_directly = _turn("已经帮你分析好了", [("analyze_job", {"job_id": 13})])

    assert check_case(case, confirmed, [confirmed]) == {"args": True, "confirm": True}
    assert check_case(case, executed_directly, [executed_directly])["confirm"] is False


def test_unexpected_interrupt_fails_read_only_case():
    case = {"expect": {"tools": ["get_profile"]}}
    turn = _turn(tools=[("get_profile", {})], interrupt={"name": "add_to_checklist", "args": {}})
    assert check_case(case, turn, [turn])["confirm"] is False


def test_no_tools_and_mention_any():
    case = {"expect": {"no_tools": True, "mention_any": ["腾讯", "法本"]}}
    turn = _turn("深圳有法本的岗位")
    assert check_case(case, turn, [turn]) == {"tools": True, "confirm": True, "mention": True}


def test_summarize_counts_write_confirmation_and_grounding():
    ok = {"id": "a", "category": "写操作", "expect": {"interrupt": "add_job"}, "passed": True,
          "checks": {"confirm": True}, "claims": [], "turns": [_turn()], "cost_usd": 0.001, "error": None}
    bad = {"id": "b", "category": "画像查询", "expect": {}, "passed": False,
           "checks": {"confirm": True, "tools": False}, "claims": [{"supported": False}],
           "turns": [_turn()], "cost_usd": 0.001, "error": None}

    s = summarize([ok, bad])

    assert s["pass_rate"] == 0.5
    assert s["write_confirmed"] == "1/1"
    assert s["grounded_rate"] == 0.5
    assert s["by_category"] == {"写操作": "1/1", "画像查询": "0/1"}


def test_grounding_requires_quoted_source():
    assert _consistent({"claim": "73 分", "source": "无", "supported": True})["supported"] is False
    assert _consistent({"claim": "73 分", "source": "match_score: 73", "supported": True})["supported"] is True


def test_context_includes_memories_history_and_tool_outputs():
    first = {**_turn("有腾讯的岗位"), "message": "有腾讯的岗位吗"}
    last = {**_turn("59 分"), "tool_outputs": [{"name": "get_job_analysis", "content": "{\"match_score\": 59}"}]}
    ctx = context_from_turns([first, last], ["只看上海"])
    assert "只看上海" in ctx[0] and "有腾讯的岗位吗" in ctx[1] and "59" in ctx[2]


def test_multi_turn_tools_count_across_turns():
    case = {"expect": {"tools": ["get_job_analysis"], "args": {"get_job_analysis": {"job_id": 1}}}}
    first = _turn(tools=[("get_job_analysis", {"job_id": 1})])
    second = _turn("这个岗位主要缺 RAG")
    assert check_case(case, second, [first, second]) == {"tools": True, "args": True, "confirm": True}


def test_equivalent_tool_paths_and_conditional_args():
    case = {"expect": {"tools_one_of": ["get_job_analysis", "list_job_scores"],
                       "args_if_called": {"get_job_analysis": {"job_id": 5}}, "mention": ["64"]}}
    via_scores = _turn("匹配分 64", [("list_job_scores", {})])
    wrong_job = _turn("匹配分 64", [("get_job_analysis", {"job_id": 4})])

    assert check_case(case, via_scores, [via_scores]) == {"tools": True, "args": None, "confirm": True, "mention": True}
    assert check_case(case, wrong_job, [wrong_job])["args"] is False
