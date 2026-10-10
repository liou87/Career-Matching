import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import Markdown from "markdown-to-jsx";
import api, { streamPost } from "../api";
import type { AgentEvent, AgentMessage, AgentThread, Memory, PendingAction } from "../types";

const EXAMPLES = [
  "我现在最该学什么",
  "字节跳动的岗位我差在哪",
  "记住：我不考虑外包岗位",
];

const THREAD_KEY = "assistant_thread_id";

const TOOL_LABELS: Record<string, string> = {
  search_jobs: "搜索岗位",
  get_skill_ranking: "查看技能排行",
  get_profile: "查看画像",
  get_job_analysis: "查看岗位分析",
  add_to_checklist: "加入提升清单",
  analyze_job: "分析岗位",
  add_job: "添加岗位",
  manage_memory: "保存偏好",
  generate_interview_questions: "生成面试题",
  list_job_scores: "查看所有匹配分",
};

function readThreadId(): string | null {
  try { return localStorage.getItem(THREAD_KEY); } catch { return null; }
}

function saveThreadId(id: string | null) {
  try {
    if (id) localStorage.setItem(THREAD_KEY, id); else localStorage.removeItem(THREAD_KEY);
  } catch { /* 存不了只影响刷新后恢复对话 */ }
}

/** 把待确认操作的参数翻译成一句人能看懂的话 */
function describeAction(a: PendingAction): string {
  const args = a.args;
  switch (a.name) {
    case "add_to_checklist": {
      const items = (args.items as { content: string }[] | undefined) ?? [];
      return items.map(i => `「${i.content}」`).join("、");
    }
    case "analyze_job":
      return `岗位 ${args.job_id}${args.force ? "（重新分析，约 10 秒）" : "（约 10 秒）"}`;
    case "generate_interview_questions":
      return `岗位 ${args.job_id}${args.force ? "（重新生成）" : ""}，约 15 秒`;
    case "add_job":
      return `${String(args.raw_jd ?? "").slice(0, 80)}…`;
    case "manage_memory":
      return `${args.action === "delete" ? "删除" : args.action === "update" ? "修改" : "记住"}：${args.content ?? args.id ?? ""}`;
    default:
      return JSON.stringify(args);
  }
}

export default function AssistantPage() {
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [pending, setPending] = useState<PendingAction[]>([]);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const threadId = useRef<string | null>(readThreadId());
  const bottomRef = useRef<HTMLDivElement>(null);

  const loadMemories = useCallback(() => {
    api.get<Memory[]>("/agent/memories").then(r => setMemories(r.data)).catch(() => {});
  }, []);

  // 刷新页面后从服务端恢复当前对话
  useEffect(() => {
    loadMemories();
    if (!threadId.current) return;
    api.get<AgentThread>(`/agent/threads/${threadId.current}`)
      .then(r => { setMessages(r.data.messages); setPending(r.data.pending); })
      .catch(() => {});
  }, [loadMemories]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, pending]);

  // 流式事件都追加到最后一条助手消息上
  const updateLast = (fn: (m: AgentMessage) => AgentMessage) =>
    setMessages(prev => [...prev.slice(0, -1), fn(prev[prev.length - 1])]);

  const handleEvent = (e: AgentEvent) => {
    switch (e.type) {
      case "thread":
        threadId.current = e.thread_id;
        saveThreadId(e.thread_id);
        break;
      case "token":
        updateLast(m => ({ ...m, content: m.content + e.text }));
        break;
      case "tool_call":
        updateLast(m => ({ ...m, tool_calls: [...(m.tool_calls ?? []), e.name] }));
        break;
      case "interrupt":
        setPending(e.actions);
        break;
      case "error":
        setError(e.detail);
        break;
    }
  };

  const run = async (path: string, body: unknown) => {
    setMessages(prev => [...prev, { role: "assistant", content: "", tool_calls: [] }]);
    setStreaming(true);
    setError("");
    try {
      await streamPost<AgentEvent>(path, body, handleEvent);
    } catch (e) {
      setError(e instanceof Error ? e.message : "请求失败，请检查后端是否在运行");
    }
    setStreaming(false);
    // 去掉什么都没产生的空消息（比如只触发了确认就结束的那一轮）
    setMessages(prev => prev.filter(m => m.role === "user" || m.content || m.tool_calls?.length));
  };

  const send = async (text = input.trim()) => {
    if (!text || streaming || pending.length) return;
    setMessages(prev => [...prev, { role: "user", content: text }]);
    setInput("");
    await run("/agent/chat", { message: text, thread_id: threadId.current });
  };

  const decide = async (approve: boolean) => {
    if (!threadId.current) return;
    const touchesMemory = pending.some(a => a.name === "manage_memory");
    setPending([]);
    await run("/agent/resume", { thread_id: threadId.current, approve });
    if (touchesMemory) loadMemories();
  };

  const newConversation = () => {
    threadId.current = null;
    saveThreadId(null);
    setMessages([]);
    setPending([]);
    setError("");
  };

  const deleteMemory = async (id: string) => {
    await api.delete(`/agent/memories/${id}`);
    loadMemories();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const busy = streaming || pending.length > 0;

  return (
    <div>
      <div className="page-header-row">
        <h1>AI 助手</h1>
        <button className="btn btn-secondary" onClick={newConversation} disabled={streaming}>新对话</button>
      </div>

      <div className="card">
        {messages.length === 0 && (
          <div className="empty">
            <p>问我关于岗位库、技能缺口、个人画像或匹配分析的问题，也可以让我替你加清单、分析岗位、记住偏好：</p>
            <div className="btn-row" style={{ justifyContent: "center" }}>
              {EXAMPLES.map(ex => (
                <button key={ex} className="btn btn-secondary" onClick={() => send(ex)}>{ex}</button>
              ))}
            </div>
          </div>
        )}

        {messages.length > 0 && (
          <div className="chat-messages">
            {messages.map((m, i) => (
              <div key={i} className={`chat-bubble ${m.role === "user" ? "chat-bubble-user" : "chat-bubble-assistant"}`}>
                {m.role === "assistant" && m.tool_calls && m.tool_calls.length > 0 && (
                  <div className="chat-tool-calls">
                    {m.tool_calls.map(t => TOOL_LABELS[t] ?? t).join(" → ")}
                  </div>
                )}
                {m.role === "assistant"
                  ? (m.content ? <Markdown>{m.content}</Markdown> : streaming && i === messages.length - 1 && <span className="loading">思考中…</span>)
                  : m.content}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        )}

        {pending.length > 0 && (
          <div className="chat-pending">
            <div className="chat-pending-title">需要你确认的操作</div>
            {pending.map((a, i) => (
              <div key={i} className="chat-pending-item">
                <strong>{TOOL_LABELS[a.name] ?? a.name}</strong>：{describeAction(a)}
              </div>
            ))}
            <div className="btn-row">
              <button className="btn btn-primary" onClick={() => decide(true)} disabled={streaming}>确认</button>
              <button className="btn btn-secondary" onClick={() => decide(false)} disabled={streaming}>取消</button>
            </div>
          </div>
        )}

        {error && <p className="error-msg">{error}</p>}

        <div className="chat-input-row">
          <textarea
            rows={2}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={pending.length ? "请先确认或取消上面的操作" : "输入问题，Enter 发送，Shift+Enter 换行"}
            disabled={busy}
          />
          <button className="btn btn-primary" onClick={() => send()} disabled={busy || !input.trim()}>
            发送
          </button>
        </div>
      </div>

      <div className="card">
        <div className="section-title">已记住的偏好（{memories.length}）</div>
        {memories.length === 0
          ? <p style={{ color: "var(--text-faint)", fontSize: 14 }}>还没有。在对话里说「记住……」，确认后会出现在这里，以后每次对话都会遵守。</p>
          : memories.map(m => (
            <div key={m.id} className="memory-row">
              <span>{m.content}</span>
              <button className="btn btn-secondary" onClick={() => deleteMemory(m.id)}>删除</button>
            </div>
          ))}
      </div>
    </div>
  );
}
