class LLMOutputError(Exception):
    """LLM 没有返回符合结构的结果，比如 with_structured_output 返回 None。

    不能继承 ValueError：langgraph 的 default_retry_on 明确把 ValueError
    及其子类排除在重试范围外，继承 ValueError 会让 RetryPolicy 形同虚设。
    """
