import { useEffect, useState } from "react";
import api from "../api";
import type { InterviewPrep } from "../types";

const RELATION: Record<string, { label: string; className: string }> = {
  strength: { label: "你的优势", className: "tag tag-green" },
  gap: { label: "你的差距", className: "tag tag-red" },
  neutral: { label: "常规考察", className: "tag tag-gray" },
};

/** 匹配分析页里的「面试准备」：从 JD 出发出题，标出对应你的优势还是差距 */
export default function InterviewPrepCard({ jobId }: { jobId: number }) {
  const [prep, setPrep] = useState<InterviewPrep | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setPrep(null);
    setError("");
    api.get<InterviewPrep>(`/interview/${jobId}/latest`).then(r => setPrep(r.data)).catch(() => {});
  }, [jobId]);

  const generate = async (force: boolean) => {
    setLoading(true);
    setError("");
    try {
      const r = await api.post<InterviewPrep>(`/interview/${jobId}`, null, { params: force ? { force: true } : {} });
      setPrep(r.data);
    } catch (e: any) {
      setError(e.response?.data?.detail || "生成失败，请稍后重试");
    }
    setLoading(false);
  };

  return (
    <div className="card">
      <div className="section-title">面试准备</div>
      {!prep && (
        <p style={{ color: "var(--text-faint)", fontSize: 14 }}>
          根据 JD 的要求出这个岗位最可能被问到的题，并标出对应你的优势还是差距，附答题要点。
        </p>
      )}

      {prep?.questions.map((q, i) => (
        <div key={i} className="interview-question">
          <div className="interview-question-head">
            <span className={RELATION[q.relation]?.className ?? "tag tag-gray"}>{RELATION[q.relation]?.label ?? q.relation}</span>
            <span className="tag tag-gray">{q.category}</span>
            <span className="interview-jd">考察：{q.jd_requirement}</span>
          </div>
          <div className="interview-question-text">{q.question}</div>
          <ul className="interview-points">
            {q.answer_points.map((p, j) => <li key={j}>{p}</li>)}
          </ul>
        </div>
      ))}

      {error && <p className="error-msg">{error}</p>}
      <div className="btn-row">
        <button className="btn btn-primary" onClick={() => generate(Boolean(prep))} disabled={loading}>
          {loading ? "生成中，约 15 秒…" : prep ? "重新生成" : "生成面试题"}
        </button>
      </div>
    </div>
  );
}
