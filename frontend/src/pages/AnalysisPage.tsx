import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "../api";
import type { Job, Analysis, ScoreBreakdown } from "../types";
import { LevelDot, LevelTag } from "../components/LevelIndicator";

function ScoreRing({ score }: { score: number }) {
  const cls = score >= 70 ? "score-high" : score >= 45 ? "score-mid" : "score-low";
  return <div className={`score-ring ${cls}`}>{score}</div>;
}

function priorityLabel(p: string) {
  return p === "high" ? "优先" : p === "medium" ? "中等" : "可选";
}

function ScoreBreakdownBars({ breakdown }: { breakdown: ScoreBreakdown }) {
  const rows = [
    { label: "技能匹配", value: breakdown.skills },
    { label: "经验匹配", value: breakdown.experience },
    { label: "学历匹配", value: breakdown.education },
    { label: "其他契合", value: breakdown.other },
  ];
  return (
    <div className="score-breakdown">
      {rows.map(r => (
        <div key={r.label} className="score-breakdown-row">
          <span className="score-breakdown-label">{r.label}</span>
          <div className="score-breakdown-track">
            <div className="score-breakdown-fill" style={{ width: `${r.value}%` }} />
          </div>
          <span className="score-breakdown-value">{r.value}</span>
        </div>
      ))}
    </div>
  );
}

export default function AnalysisPage() {
  const [searchParams] = useSearchParams();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedJob, setSelectedJob] = useState<number | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [checkedGaps, setCheckedGaps] = useState<Set<number>>(new Set());
  const [savingChecklist, setSavingChecklist] = useState(false);
  const [checklistMsg, setChecklistMsg] = useState("");
  const [reuseMsg, setReuseMsg] = useState("");

  useEffect(() => {
    api.get("/jobs").then(r => {
      setJobs(r.data);
      const qJob = searchParams.get("job");
      if (qJob) {
        const id = parseInt(qJob);
        setSelectedJob(id);
        loadLatest(id);
      }
    });
  }, []);

  const loadLatest = (id: number) => {
    setCheckedGaps(new Set());
    setChecklistMsg("");
    api.get(`/analysis/${id}/latest`).then(r => setAnalysis(r.data)).catch(() => setAnalysis(null));
  };

  const selectJob = (id: number) => {
    setSelectedJob(id);
    setAnalysis(null);
    setError("");
    loadLatest(id);
  };

  const runAnalysis = async (force = false) => {
    if (!selectedJob) return;
    const previousId = analysis?.id;
    setRunning(true);
    setError("");
    setCheckedGaps(new Set());
    setChecklistMsg("");
    setReuseMsg("");
    try {
      const r = await api.post(`/analysis/${selectedJob}`, null, { params: force ? { force: true } : {} });
      setAnalysis(r.data);
      if (!force && previousId !== undefined && r.data.id === previousId) {
        setReuseMsg("内容没有变化，已复用上次的分析结果");
      }
    } catch (e: any) {
      setError(e.response?.data?.detail || "分析失败，请先完善个人画像并检查API Key");
    }
    setRunning(false);
  };

  const toggleGap = (i: number) => {
    setCheckedGaps(prev => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i); else next.add(i);
      return next;
    });
  };

  const saveToChecklist = async () => {
    if (!analysis || checkedGaps.size === 0) return;
    setSavingChecklist(true);
    setChecklistMsg("");
    try {
      const items = [...checkedGaps].map(i => {
        const g = analysis.gaps[i];
        return { content: g.gap, importance: g.importance, suggestion: g.suggestion };
      });
      await api.post("/checklist", { items });
      setChecklistMsg(`已保存 ${items.length} 条到提升清单`);
      setCheckedGaps(new Set());
    } catch {
      setChecklistMsg("保存失败，请重试");
    }
    setSavingChecklist(false);
  };

  const job = jobs.find(j => j.id === selectedJob);

  return (
    <div>
      <h1>匹配分析</h1>

      <div className="card">
        <h2>选择岗位</h2>
        {jobs.length === 0
          ? <p className="empty">岗位库为空，请先在「岗位库」添加岗位</p>
          : <select value={selectedJob ?? ""} onChange={e => selectJob(Number(e.target.value))}>
              <option value="">请选择岗位...</option>
              {jobs.map(j => (
                <option key={j.id} value={j.id}>
                  {j.title} · {j.company} · {j.city}
                </option>
              ))}
            </select>
        }
        {selectedJob && (
          <div className="btn-row">
            <button className="btn btn-primary" onClick={() => runAnalysis(false)} disabled={running}>
              {running ? "AI 分析中..." : analysis ? "重新分析" : "开始匹配分析"}
            </button>
            {analysis && (
              <button className="btn btn-secondary" onClick={() => runAnalysis(true)} disabled={running} title="不管内容变没变，都强制让 AI 重新判断一次">
                强制重新分析
              </button>
            )}
            {running && <span style={{ alignSelf: "center", color: "var(--text-muted)", fontSize: 13 }}>DeepSeek 正在分析，约 10-15 秒...</span>}
          </div>
        )}
        {error && <p className="error-msg" style={{ marginTop: 8 }}>{error}</p>}
        {reuseMsg && <p className="success-msg" style={{ marginTop: 8 }}>{reuseMsg}</p>}
      </div>

      {analysis && job && (
        <>
          <div className="card">
            <div className="analysis-header">
              <ScoreRing score={analysis.match_score} />
              <div className="analysis-title">
                <h2>{job.title} · {job.company}</h2>
                <p>匹配分：{analysis.match_score} / 100 · {job.city}</p>
                <p style={{ color: "var(--text-faint)", fontSize: 12, marginTop: 2 }}>AI 估算，仅供参考</p>
              </div>
            </div>
            <p style={{ color: "var(--text)", lineHeight: 1.7 }}>{analysis.summary}</p>
            {analysis.score_breakdown && <ScoreBreakdownBars breakdown={analysis.score_breakdown} />}
          </div>

          <div className="two-col">
            <div className="card">
              <div className="section-title">已匹配技能</div>
              {analysis.matched_skills.length === 0
                ? <p style={{ color: "var(--text-faint)", fontSize: 14 }}>暂无</p>
                : analysis.matched_skills.map((s, i) => <span key={i} className="tag tag-green">{s}</span>)
              }
            </div>
            <div className="card">
              <div className="section-title">缺失技能</div>
              {analysis.missing_skills.length === 0
                ? <p style={{ color: "var(--text-faint)", fontSize: 14 }}>暂无</p>
                : analysis.missing_skills.map((s, i) => <span key={i} className="tag tag-red">{s}</span>)
              }
            </div>
          </div>

          <div className="card">
            <div className="section-title">你的优势</div>
            <ul style={{ paddingLeft: 18, lineHeight: 2, fontSize: 14 }}>
              {analysis.strengths.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>

          <div className="card">
            <div className="section-title">主要差距</div>
            {analysis.gaps.map((g, i) => (
              <div key={i} className="suggestion-item">
                <input
                  type="checkbox"
                  style={{ width: "auto", marginTop: 4 }}
                  checked={checkedGaps.has(i)}
                  onChange={() => toggleGap(i)}
                />
                <LevelDot value={g.importance} />
                <div>
                  <div style={{ fontWeight: 500, fontSize: 14, marginBottom: 2 }}>{g.gap}</div>
                  <div style={{ fontSize: 13, color: "var(--text-muted)" }}>{g.suggestion}</div>
                </div>
                <span style={{ marginLeft: "auto", flexShrink: 0 }}>
                  <LevelTag value={g.importance} />
                </span>
              </div>
            ))}
            <div className="btn-row">
              <button className="btn btn-primary" onClick={saveToChecklist} disabled={checkedGaps.size === 0 || savingChecklist}>
                {savingChecklist ? "保存中..." : `保存到提升清单 (${checkedGaps.size})`}
              </button>
              {checklistMsg && <span className={checklistMsg.includes("失败") ? "error-msg" : "success-msg"} style={{ alignSelf: "center" }}>{checklistMsg}</span>}
            </div>
          </div>

          <div className="card">
            <div className="section-title">行动建议</div>
            {analysis.action_items.length === 0 && (
              <p style={{ color: "var(--text-faint)", fontSize: 14 }}>该岗位技术栈与你的求职方向不符，未生成提升建议。</p>
            )}
            {analysis.action_items.map((s, i) => (
              <div key={i} className="suggestion-item">
                <LevelDot value={s.priority} />
                <div>
                  <div style={{ fontWeight: 500, fontSize: 14, marginBottom: 2 }}>{s.item}</div>
                  {s.why_valuable && (
                    <div style={{ fontSize: 13, color: "var(--text)", marginBottom: 2 }}>
                      <span style={{ fontWeight: 500 }}>为什么重要：</span>{s.why_valuable}
                    </div>
                  )}
                  {s.resource && <div style={{ fontSize: 13, color: "var(--text-muted)" }}>{s.resource}</div>}
                </div>
                <span style={{ marginLeft: "auto", flexShrink: 0 }}>
                  <LevelTag value={s.priority} label={priorityLabel(s.priority)} />
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
