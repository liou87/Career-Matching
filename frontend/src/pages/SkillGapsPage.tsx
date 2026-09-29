import { useCallback, useEffect, useRef, useState } from "react";
import api from "../api";
import type { BatchAnalysis, SkillRankingItem } from "../types";

type LoadState = "loading" | "empty" | "ready";

const isOther = (item: SkillRankingItem) => item.job_count === 1 || item.skill.startsWith("其他:");

export default function SkillGapsPage() {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [batch, setBatch] = useState<BatchAnalysis | null>(null);
  const [activeJobCount, setActiveJobCount] = useState(0);
  const [polling, setPolling] = useState(false);
  const [pollError, setPollError] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [othersOpen, setOthersOpen] = useState(false);
  const pollRef = useRef<number | null>(null);

  const loadLatest = useCallback(() => {
    return api.get("/analysis/batch/latest").then(r => {
      if (r.data.status === "none") {
        setBatch(null);
        setLoadState("empty");
      } else {
        setBatch(r.data);
        setLoadState("ready");
      }
    });
  }, []);

  useEffect(() => {
    loadLatest();
    api.get("/jobs").then(r => {
      setActiveJobCount(r.data.filter((j: any) => (j.status ?? "active") === "active").length);
    }).catch(() => {});
  }, [loadLatest]);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    setPolling(false);
  }, []);

  // 组件卸载时清掉定时器，避免用户切走页面后还在后台轮询
  useEffect(() => {
    return () => {
      if (pollRef.current !== null) window.clearInterval(pollRef.current);
    };
  }, []);

  const checkTask = useCallback((taskId: number) => {
    api.get(`/analysis/batch/${taskId}`).then(r => {
      const task = r.data;
      if (task.status === "done") {
        stopPolling();
        loadLatest();
      } else if (task.status === "failed") {
        stopPolling();
        setPollError(task.error || "分析失败");
      }
      // pending / running：什么都不做，等下一次轮询
    }).catch(() => {
      stopPolling();
      setPollError("查询任务状态失败，请检查后端是否在运行");
    });
  }, [loadLatest, stopPolling]);

  const startAnalysis = async () => {
    setPollError("");
    // 后端在请求里同步跑完才返回（约半分钟），等待期间就显示「分析中」
    setPolling(true);
    try {
      const r = await api.post("/analysis/batch");
      const taskId = r.data.task_id;
      checkTask(taskId);
      pollRef.current = window.setInterval(() => checkTask(taskId), 3000);
    } catch {
      setPolling(false);
      setPollError("触发分析失败，请检查后端是否在运行");
    }
  };

  const toggleExpand = (skill: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(skill)) next.delete(skill); else next.add(skill);
      return next;
    });
  };

  const renderRow = (item: SkillRankingItem, tagClass: string) => (
    <div key={item.skill} className="skill-gap-row">
      <div className="skill-gap-row-head" onClick={() => toggleExpand(item.skill)}>
        <span className="skill-gap-name">{item.skill.replace(/^其他:/, "")}</span>
        <span className={`tag ${tagClass}`}>{item.job_count}/{batch?.job_count ?? 0} 岗位</span>
        <span className="tag tag-gray">{item.category}</span>
        <span className={`skill-gap-arrow ${expanded.has(item.skill) ? "open" : ""}`}>›</span>
      </div>
      {expanded.has(item.skill) && (
        <ul className="skill-gap-originals">
          {item.originals.map((o, i) => <li key={i}>{o}</li>)}
        </ul>
      )}
    </div>
  );

  if (loadState === "loading") {
    return (
      <div>
        <h1>技能缺口总览</h1>
        <p className="loading">加载中...</p>
      </div>
    );
  }

  const ranking = batch?.ranking ?? [];
  const mainList = ranking.filter(r => !isOther(r));
  const otherList = ranking.filter(isOther);
  const estSeconds = activeJobCount > 0 ? Math.max(10, Math.round(activeJobCount * 2.5)) : null;

  return (
    <div>
      <h1>技能缺口总览</h1>

      {polling && (
        <div className="card">
          <p className="loading">
            {estSeconds
              ? `正在分析 ${activeJobCount} 个岗位，约需 ${estSeconds} 秒，请稍候...`
              : "正在分析岗位技能缺口，请稍候..."}
          </p>
        </div>
      )}

      {!polling && pollError && (
        <div className="card">
          <p className="error-msg">分析失败：{pollError}</p>
        </div>
      )}

      {loadState === "empty" && !polling && (
        <div className="card">
          <p className="empty">还没有分析数据，点击开始批量分析所有岗位的技能缺口</p>
          <div className="btn-row">
            <button className="btn btn-primary" onClick={startAnalysis}>开始分析</button>
          </div>
        </div>
      )}

      {loadState === "ready" && batch && (
        <div className="card">
          <div className="analysis-header">
            <div className="analysis-title" style={{ flex: 1 }}>
              <h2>技能缺口排行</h2>
              <p>
                上次更新：{batch.finished_at ? new Date(batch.finished_at).toLocaleString() : "-"}
                {" · "}共 {batch.job_count} 个岗位，成功 {batch.success_count} 个
              </p>
            </div>
            <button className="btn btn-secondary" onClick={startAnalysis} disabled={polling}>
              {polling ? "分析中..." : "重新分析"}
            </button>
          </div>

          {mainList.length === 0 && <p className="empty">暂无覆盖多个岗位的共性技能缺口</p>}
          {mainList.map(item => renderRow(item, "tag-blue"))}

          {otherList.length > 0 && (
            <div className="skill-gap-others">
              <div className="skill-gap-row-head" onClick={() => setOthersOpen(o => !o)}>
                <span className="skill-gap-name" style={{ color: "var(--text-muted)" }}>
                  其他（词表未覆盖，可能是新兴要求）· {otherList.length}
                </span>
                <span className={`skill-gap-arrow ${othersOpen ? "open" : ""}`}>›</span>
              </div>
              {othersOpen && otherList.map(item => renderRow(item, "tag-gray"))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
