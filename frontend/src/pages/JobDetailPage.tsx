import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "../api";

interface JobDetail {
  id: number;
  raw_jd: string;
  title: string | null;
  company: string | null;
  city: string | null;
  salary_min: number | null;
  salary_max: number | null;
  required_skills: string[];
  preferred_skills: string[];
  experience_required: string | null;
  education_required: string | null;
  responsibilities: string[];
}

function salaryLabel(min: number | null, max: number | null) {
  if (!min && !max) return "薪资面议";
  if (min && max) return `${min}k - ${max}k`;
  return `${min || max}k`;
}

export default function JobDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState<JobDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get(`/jobs/${id}`)
      .then(r => setJob(r.data))
      .catch(() => setError("岗位不存在或已删除"))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <p className="loading">加载中...</p>;
  if (error || !job) return <p className="empty">{error || "岗位不存在"}</p>;

  return (
    <div>
      <button className="btn btn-secondary" onClick={() => navigate("/jobs")} style={{ marginBottom: 16 }}>
        ← 返回岗位库
      </button>

      <h1>{job.title || "未知职位"}</h1>

      <div className="card">
        <div className="job-meta" style={{ marginBottom: 12, fontSize: 14 }}>
          {[job.company, job.city, salaryLabel(job.salary_min, job.salary_max)].filter(Boolean).join(" · ")}
          {job.experience_required && ` · ${job.experience_required}`}
          {job.education_required && ` · ${job.education_required}`}
        </div>

        {job.required_skills?.length > 0 && (
          <div style={{ marginBottom: 8 }}>
            <div className="section-title">必备技能</div>
            {job.required_skills.map((s, i) => <span key={i} className="tag tag-blue">{s}</span>)}
          </div>
        )}

        {job.preferred_skills?.length > 0 && (
          <div style={{ marginBottom: 8 }}>
            <div className="section-title">加分技能</div>
            {job.preferred_skills.map((s, i) => <span key={i} className="tag tag-gray">{s}</span>)}
          </div>
        )}

        {job.responsibilities?.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div className="section-title">主要职责</div>
            <ul style={{ paddingLeft: 18, lineHeight: 2, fontSize: 14 }}>
              {job.responsibilities.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          </div>
        )}

        <div className="btn-row">
          <button className="btn btn-primary" onClick={() => navigate(`/analysis?job=${job.id}`)}>匹配分析</button>
        </div>
      </div>

      <div className="card">
        <div className="section-title">JD 原文</div>
        <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", fontSize: 14, lineHeight: 1.7, color: "#374151" }}>
          {job.raw_jd}
        </pre>
      </div>
    </div>
  );
}
