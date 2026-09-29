import { useEffect, useState, type KeyboardEvent } from "react";
import api from "../api";
import type { ChecklistItem } from "../types";
import { LevelDot, LevelTag } from "../components/LevelIndicator";

export default function ChecklistPage() {
  const [items, setItems] = useState<ChecklistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editValue, setEditValue] = useState("");

  const load = () => api.get("/checklist").then(r => setItems(r.data)).finally(() => setLoading(false));

  useEffect(() => { load(); }, []);

  const toggleStatus = async (item: ChecklistItem) => {
    const status = item.status === "done" ? "todo" : "done";
    setItems(list => list.map(i => i.id === item.id ? { ...i, status } : i));
    await api.patch(`/checklist/${item.id}`, { status });
  };

  const startEdit = (item: ChecklistItem) => {
    setEditingId(item.id);
    setEditValue(item.content);
  };

  const saveEdit = async (id: number) => {
    const content = editValue.trim();
    setEditingId(null);
    if (!content) return;
    setItems(list => list.map(i => i.id === id ? { ...i, content } : i));
    await api.patch(`/checklist/${id}`, { content });
  };

  const handleEditKey = (e: KeyboardEvent<HTMLInputElement>, id: number) => {
    if (e.key === "Enter") saveEdit(id);
    if (e.key === "Escape") setEditingId(null);
  };

  const remove = async (id: number) => {
    if (!window.confirm("确定要删除这条清单吗？")) return;
    setItems(list => list.filter(i => i.id !== id));
    await api.delete(`/checklist/${id}`);
  };

  const gapTodoItems = items.filter(i => i.status === "todo" && i.category !== "action");
  const actionTodoItems = items.filter(i => i.status === "todo" && i.category === "action");
  const doneItems = items.filter(i => i.status === "done");

  const renderItem = (item: ChecklistItem) => (
    <div key={item.id} className="suggestion-item">
      <input
        type="checkbox"
        style={{ width: "auto", marginTop: 4 }}
        checked={item.status === "done"}
        onChange={() => toggleStatus(item)}
        title="标记完成/未完成"
      />
      {item.importance && <LevelDot value={item.importance} />}
      <div style={{ flex: 1 }}>
        {editingId === item.id ? (
          <input
            autoFocus
            value={editValue}
            onChange={e => setEditValue(e.target.value)}
            onBlur={() => saveEdit(item.id)}
            onKeyDown={e => handleEditKey(e, item.id)}
          />
        ) : (
          <div
            onClick={() => startEdit(item)}
            style={{
              fontWeight: 500, fontSize: 14, marginBottom: 2, cursor: "text",
              textDecoration: item.status === "done" ? "line-through" : "none",
              color: item.status === "done" ? "var(--text-faint)" : "inherit",
            }}
            title="点击编辑"
          >
            {item.content}
          </div>
        )}
        {item.suggestion && <div style={{ fontSize: 13, color: "var(--text-muted)" }}>{item.suggestion}</div>}
      </div>
      {item.importance && (
        <span style={{ flexShrink: 0 }}>
          <LevelTag value={item.importance} />
        </span>
      )}
      <button className="btn btn-danger" onClick={() => remove(item.id)}>删除</button>
    </div>
  );

  return (
    <div>
      <h1>我的清单</h1>

      {loading && <p className="loading">加载中...</p>}

      {!loading && items.length === 0 && (
        <p className="empty">清单还是空的，去「匹配分析」页面勾选差距或行动建议保存进来吧</p>
      )}

      {!loading && items.length > 0 && (
        <>
          <div className="card">
            <div className="section-title">待提升（{gapTodoItems.length}）</div>
            {gapTodoItems.length === 0
              ? <p style={{ color: "var(--text-faint)", fontSize: 14 }}>暂无</p>
              : gapTodoItems.map(renderItem)}
          </div>

          <div className="card">
            <div className="section-title">行动建议（{actionTodoItems.length}）</div>
            {actionTodoItems.length === 0
              ? <p style={{ color: "var(--text-faint)", fontSize: 14 }}>暂无</p>
              : actionTodoItems.map(renderItem)}
          </div>

          {doneItems.length > 0 && (
            <div className="card">
              <div className="section-title">已完成（{doneItems.length}）</div>
              {doneItems.map(renderItem)}
            </div>
          )}
        </>
      )}
    </div>
  );
}
