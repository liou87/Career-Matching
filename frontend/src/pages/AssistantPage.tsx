import { useState, type KeyboardEvent } from "react";
import Markdown from "markdown-to-jsx";
import api from "../api";
import type { AgentMessage } from "../types";

const EXAMPLES = [
  "我现在最该学什么",
  "字节的岗位我差在哪",
  "帮我找找 LangChain 相关的岗位",
];

export default function AssistantPage() {
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;

    const history = messages.map(m => ({ role: m.role, content: m.content }));
    setMessages(prev => [...prev, { role: "user", content: text }]);
    setInput("");
    setLoading(true);
    setError("");

    try {
      const r = await api.post("/agent/chat", { message: text, history });
      setMessages(prev => [...prev, { role: "assistant", content: r.data.reply, tool_calls: r.data.tool_calls }]);
    } catch (e: any) {
      setError(e.response?.data?.detail || "请求失败，请检查后端是否在运行");
    }
    setLoading(false);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div>
      <h1>AI 助手</h1>

      <div className="card">
        {messages.length === 0 && !loading && (
          <div className="empty">
            <p>问我关于岗位库、技能缺口、个人画像或匹配分析的问题，比如：</p>
            <div className="btn-row" style={{ justifyContent: "center" }}>
              {EXAMPLES.map(ex => (
                <button key={ex} className="btn btn-secondary" onClick={() => setInput(ex)}>{ex}</button>
              ))}
            </div>
          </div>
        )}

        {messages.length > 0 && (
          <div className="chat-messages">
            {messages.map((m, i) => (
              <div key={i} className={`chat-bubble ${m.role === "user" ? "chat-bubble-user" : "chat-bubble-assistant"}`}>
                {m.role === "assistant" ? <Markdown>{m.content}</Markdown> : m.content}
                {m.role === "assistant" && m.tool_calls && m.tool_calls.length > 0 && (
                  <div className="chat-tool-calls">调用了工具：{m.tool_calls.map(tc => tc.name).join("、")}</div>
                )}
              </div>
            ))}
          </div>
        )}

        {loading && <p className="loading">AI 正在思考，可能需要 10-20 秒...</p>}
        {error && <p className="error-msg">{error}</p>}

        <div className="chat-input-row">
          <textarea
            rows={2}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入问题，Enter 发送，Shift+Enter 换行"
          />
          <button className="btn btn-primary" onClick={send} disabled={loading || !input.trim()}>
            发送
          </button>
        </div>
      </div>
    </div>
  );
}
