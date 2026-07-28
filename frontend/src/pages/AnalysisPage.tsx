import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "../api";

interface Job { id: number; title: string; company: string; city: string; }
interface Suggestion { item: string; priority: string; resource?: string; }
interface Analysis {
  id: number;
  job_id: number;
  match_score: number;
  matched_skills: string[];
  missing_skills: string[];
  strengths: string[];
  gaps: string[];
  suggestions: Suggestion[];
  summary: string;
}

function ScoreRing({ score }: { score: number }) {
  const cls = score >= 70 ? "score-high" : score >= 45 ? "score-mid" : "score-low";
  return <div className={`score-ring ${cls}`}>{score}</div>;
}

function PriorityDot({ p }: { p: string }) {
  const cls = p === "high" ? "dot-high" : p === "medium" ? "dot-mid" : "dot-low";
  return <div className={`priority-dot ${cls}`} />;
}

export default function AnalysisPage() {
  const [searchParams] = useSearchParams();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedJob, setSelectedJob] = useState<number | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

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
    api.get(`/analysis/${id}/latest`).then(r => setAnalysis(r.data)).catch(() => setAnalysis(null));
  };

  const selectJob = (id: number) => {
    setSelectedJob(id);
    setAnalysis(null);
    setError("");
    loadLatest(id);
  };

  const runAnalysis = async () => {
    if (!selectedJob) return;
    setRunning(true);
    setError("");
    try {
      const r = await api.post(`/analysis/${selectedJob}`);
      setAnalysis(r.data);
    } catch (e: any) {
      setError(e.response?.data?.detail || "分析失败，请先完善个人画像并检查API Key");
    }
    setRunning(false);
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
            <button className="btn btn-primary" onClick={runAnalysis} disabled={running}>
              {running ? "AI 分析中..." : analysis ? "重新分析" : "开始匹配分析"}
            </button>
            {running && <span style={{ alignSelf: "center", color: "#6b7280", fontSize: 13 }}>Claude 正在分析，约 10-15 秒...</span>}
          </div>
        )}
        {error && <p className="error-msg" style={{ marginTop: 8 }}>{error}</p>}
      </div>

      {analysis && job && (
        <>
          <div className="card">
            <div className="analysis-header">
              <ScoreRing score={analysis.match_score} />
              <div className="analysis-title">
                <h2>{job.title} · {job.company}</h2>
                <p>匹配分：{analysis.match_score} / 100 · {job.city}</p>
              </div>
            </div>
            <p style={{ color: "#374151", lineHeight: 1.7 }}>{analysis.summary}</p>
          </div>

          <div className="two-col">
            <div className="card">
              <div className="section-title">已匹配技能</div>
              {analysis.matched_skills.length === 0
                ? <p style={{ color: "#9ca3af", fontSize: 14 }}>暂无</p>
                : analysis.matched_skills.map((s, i) => <span key={i} className="tag tag-green">{s}</span>)
              }
            </div>
            <div className="card">
              <div className="section-title">缺失技能</div>
              {analysis.missing_skills.length === 0
                ? <p style={{ color: "#9ca3af", fontSize: 14 }}>暂无</p>
                : analysis.missing_skills.map((s, i) => <span key={i} className="tag tag-red">{s}</span>)
              }
            </div>
          </div>

          <div className="two-col">
            <div className="card">
              <div className="section-title">你的优势</div>
              <ul style={{ paddingLeft: 18, lineHeight: 2, fontSize: 14 }}>
                {analysis.strengths.map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </div>
            <div className="card">
              <div className="section-title">主要差距</div>
              <ul style={{ paddingLeft: 18, lineHeight: 2, fontSize: 14 }}>
                {analysis.gaps.map((g, i) => <li key={i}>{g}</li>)}
              </ul>
            </div>
          </div>

          <div className="card">
            <div className="section-title">提升建议</div>
            {analysis.suggestions.map((s, i) => (
              <div key={i} className="suggestion-item">
                <PriorityDot p={s.priority} />
                <div>
                  <div style={{ fontWeight: 500, fontSize: 14, marginBottom: 2 }}>{s.item}</div>
                  {s.resource && <div style={{ fontSize: 13, color: "#6b7280" }}>{s.resource}</div>}
                </div>
                <span className="tag" style={{ marginLeft: "auto", flexShrink: 0,
                  background: s.priority === "high" ? "#fee2e2" : s.priority === "medium" ? "#fef9c3" : "#dcfce7",
                  color: s.priority === "high" ? "#dc2626" : s.priority === "medium" ? "#b45309" : "#16a34a"
                }}>
                  {s.priority === "high" ? "优先" : s.priority === "medium" ? "中等" : "可选"}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
