import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api";

interface Job {
  id: number;
  title: string;
  company: string;
  city: string;
  salary_min: number | null;
  salary_max: number | null;
  required_skills: string[];
  experience_required: string;
  education_required: string;
  parsed_at: string;
}

function salaryLabel(min: number | null, max: number | null) {
  if (!min && !max) return "薪资面议";
  if (min && max) return `${min}k - ${max}k`;
  return `${min || max}k`;
}

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jdText, setJdText] = useState("");
  const [url, setUrl] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const load = () => api.get("/jobs").then(r => setJobs(r.data));

  useEffect(() => { load(); }, []);

  const addJob = async () => {
    if (!jdText.trim()) { setError("请粘贴JD内容"); return; }
    setAdding(true);
    setError("");
    try {
      await api.post("/jobs", { raw_jd: jdText, source_url: url || null });
      setJdText("");
      setUrl("");
      await load();
    } catch (e: any) {
      setError("解析失败：" + (e.response?.data?.detail || "请检查API Key"));
    }
    setAdding(false);
  };

  const deleteJob = async (id: number) => {
    await api.delete(`/jobs/${id}`);
    setJobs(j => j.filter(x => x.id !== id));
  };

  return (
    <div>
      <h1>岗位库</h1>

      <div className="card">
        <h2>添加岗位</h2>
        <div className="form-group">
          <label>粘贴 JD 全文（AI 自动解析）</label>
          <textarea
            rows={8}
            value={jdText}
            onChange={e => setJdText(e.target.value)}
            placeholder={"把招聘网站上的岗位描述全部复制粘贴到这里\n\n包括职位名、公司、薪资、职责、要求等..."}
          />
        </div>
        <div className="form-group">
          <label>岗位链接（可选）</label>
          <input value={url} onChange={e => setUrl(e.target.value)} placeholder="https://..." />
        </div>
        {error && <p className="error-msg">{error}</p>}
        <button className="btn btn-primary" onClick={addJob} disabled={adding}>
          {adding ? "AI 解析中..." : "解析并添加"}
        </button>
        {adding && <p style={{ color: "#6b7280", fontSize: 13, marginTop: 8 }}>正在调用 Claude 解析 JD，通常需要 5-10 秒...</p>}
      </div>

      <h2>已收录岗位（{jobs.length}）</h2>

      {jobs.length === 0 && <p className="empty">还没有岗位，粘贴第一条 JD 开始吧</p>}

      {jobs.map(job => (
        <div key={job.id} className="job-card">
          <div className="job-card-body">
            <div className="job-title">{job.title || "未知职位"}</div>
            <div className="job-meta">
              {[job.company, job.city, salaryLabel(job.salary_min, job.salary_max)].filter(Boolean).join(" · ")}
              {job.experience_required && ` · ${job.experience_required}`}
              {job.education_required && ` · ${job.education_required}`}
            </div>
            <div>
              {(job.required_skills || []).slice(0, 6).map((s, i) => (
                <span key={i} className="tag tag-blue">{s}</span>
              ))}
              {(job.required_skills || []).length > 6 && (
                <span className="tag tag-gray">+{job.required_skills.length - 6}</span>
              )}
            </div>
            <div className="job-actions">
              <button className="btn btn-primary" onClick={() => navigate(`/analysis?job=${job.id}`)}>
                匹配分析
              </button>
              <button className="btn btn-danger" onClick={() => deleteJob(job.id)}>删除</button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
