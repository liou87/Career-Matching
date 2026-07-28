import { useEffect, useState, type KeyboardEvent } from "react";
import api from "../api";

interface Education { degree: string; school: string; major: string; year: string; }
interface Experience { title: string; company: string; duration: string; description: string; }
interface Project { name: string; description: string; tech_stack: string[]; }

interface ProfileData {
  name: string;
  education: Education[];
  skills: string[];
  experiences: Experience[];
  projects: Project[];
  target_roles: string[];
  target_cities: string[];
  target_companies: string[];
}

const emptyProfile: ProfileData = {
  name: "",
  education: [],
  skills: [],
  experiences: [],
  projects: [],
  target_roles: [],
  target_cities: [],
  target_companies: [],
};

export default function ProfilePage() {
  const [profile, setProfile] = useState<ProfileData>(emptyProfile);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [skillInput, setSkillInput] = useState("");
  const [roleInput, setRoleInput] = useState("");
  const [cityInput, setCityInput] = useState("");
  const [companyInput, setCompanyInput] = useState("");

  useEffect(() => {
    api.get("/profile").then(r => setProfile(r.data)).catch(() => {});
  }, []);

  const save = async () => {
    setSaving(true);
    setMsg("");
    try {
      await api.put("/profile", profile);
      setMsg("已保存");
    } catch {
      setMsg("保存失败，请检查必填项");
    }
    setSaving(false);
  };

  const addTag = (field: "skills" | "target_roles" | "target_cities" | "target_companies", val: string, setter: (v: string) => void) => {
    const v = val.trim();
    if (!v) return;
    setProfile(p => ({ ...p, [field]: [...p[field], v] }));
    setter("");
  };

  const removeTag = (field: "skills" | "target_roles" | "target_cities" | "target_companies", idx: number) => {
    setProfile(p => ({ ...p, [field]: p[field].filter((_, i) => i !== idx) }));
  };

  const addEdu = () => setProfile(p => ({
    ...p,
    education: [...p.education, { degree: "", school: "", major: "", year: "" }]
  }));

  const addExp = () => setProfile(p => ({
    ...p,
    experiences: [...p.experiences, { title: "", company: "", duration: "", description: "" }]
  }));

  const addProject = () => setProfile(p => ({
    ...p,
    projects: [...p.projects, { name: "", description: "", tech_stack: [] }]
  }));

  const handleKey = (e: KeyboardEvent<HTMLInputElement>, fn: () => void) => {
    if (e.key === "Enter") { e.preventDefault(); fn(); }
  };

  return (
    <div>
      <h1>个人画像</h1>

      <div className="card">
        <h2>基本信息</h2>
        <div className="form-group">
          <label>姓名</label>
          <input value={profile.name} onChange={e => setProfile(p => ({ ...p, name: e.target.value }))} placeholder="你的名字" />
        </div>
      </div>

      <div className="card">
        <h2>教育经历</h2>
        {profile.education.map((edu, i) => (
          <div key={i} style={{ marginBottom: 16, paddingBottom: 16, borderBottom: "1px solid #f0f0f0" }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
              <div className="form-group" style={{ margin: 0 }}>
                <label>学位</label>
                <input value={edu.degree} onChange={e => {
                  const arr = [...profile.education]; arr[i].degree = e.target.value; setProfile(p => ({ ...p, education: arr }));
                }} placeholder="硕士 / 学士" />
              </div>
              <div className="form-group" style={{ margin: 0 }}>
                <label>学校</label>
                <input value={edu.school} onChange={e => {
                  const arr = [...profile.education]; arr[i].school = e.target.value; setProfile(p => ({ ...p, education: arr }));
                }} placeholder="学校名称" />
              </div>
              <div className="form-group" style={{ margin: 0 }}>
                <label>专业</label>
                <input value={edu.major} onChange={e => {
                  const arr = [...profile.education]; arr[i].major = e.target.value; setProfile(p => ({ ...p, education: arr }));
                }} placeholder="专业方向" />
              </div>
              <div className="form-group" style={{ margin: 0 }}>
                <label>毕业年份</label>
                <input value={edu.year} onChange={e => {
                  const arr = [...profile.education]; arr[i].year = e.target.value; setProfile(p => ({ ...p, education: arr }));
                }} placeholder="2025" />
              </div>
            </div>
            <button className="btn btn-danger" onClick={() => setProfile(p => ({ ...p, education: p.education.filter((_, j) => j !== i) }))}>删除</button>
          </div>
        ))}
        <button className="btn btn-secondary" onClick={addEdu}>+ 添加教育经历</button>
      </div>

      <div className="card">
        <h2>技能标签</h2>
        <div className="tag-input-row" style={{ marginBottom: 12 }}>
          <input
            value={skillInput}
            onChange={e => setSkillInput(e.target.value)}
            onKeyDown={e => handleKey(e, () => addTag("skills", skillInput, setSkillInput))}
            placeholder="输入技能后按 Enter（如 Python、SQL、React）"
          />
          <button className="btn btn-secondary" onClick={() => addTag("skills", skillInput, setSkillInput)}>添加</button>
        </div>
        <div>
          {profile.skills.map((s, i) => (
            <span key={i} className="tag tag-blue" onClick={() => removeTag("skills", i)} style={{ cursor: "pointer" }} title="点击删除">
              {s} ×
            </span>
          ))}
        </div>
      </div>

      <div className="card">
        <h2>实习 / 工作经历</h2>
        {profile.experiences.map((exp, i) => (
          <div key={i} style={{ marginBottom: 16, paddingBottom: 16, borderBottom: "1px solid #f0f0f0" }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
              <div className="form-group" style={{ margin: 0 }}>
                <label>职位</label>
                <input value={exp.title} onChange={e => {
                  const arr = [...profile.experiences]; arr[i].title = e.target.value; setProfile(p => ({ ...p, experiences: arr }));
                }} placeholder="实习生 / 工程师" />
              </div>
              <div className="form-group" style={{ margin: 0 }}>
                <label>公司</label>
                <input value={exp.company} onChange={e => {
                  const arr = [...profile.experiences]; arr[i].company = e.target.value; setProfile(p => ({ ...p, experiences: arr }));
                }} placeholder="公司名称" />
              </div>
              <div className="form-group" style={{ margin: 0 }}>
                <label>时间段</label>
                <input value={exp.duration} onChange={e => {
                  const arr = [...profile.experiences]; arr[i].duration = e.target.value; setProfile(p => ({ ...p, experiences: arr }));
                }} placeholder="2024.06 - 2024.09" />
              </div>
            </div>
            <div className="form-group">
              <label>工作描述</label>
              <textarea rows={3} value={exp.description} onChange={e => {
                const arr = [...profile.experiences]; arr[i].description = e.target.value; setProfile(p => ({ ...p, experiences: arr }));
              }} placeholder="简述主要工作内容和成果" />
            </div>
            <button className="btn btn-danger" onClick={() => setProfile(p => ({ ...p, experiences: p.experiences.filter((_, j) => j !== i) }))}>删除</button>
          </div>
        ))}
        <button className="btn btn-secondary" onClick={addExp}>+ 添加经历</button>
      </div>

      <div className="card">
        <h2>项目经历</h2>
        {profile.projects.map((proj, i) => (
          <div key={i} style={{ marginBottom: 16, paddingBottom: 16, borderBottom: "1px solid #f0f0f0" }}>
            <div className="form-group">
              <label>项目名称</label>
              <input value={proj.name} onChange={e => {
                const arr = [...profile.projects]; arr[i].name = e.target.value; setProfile(p => ({ ...p, projects: arr }));
              }} placeholder="项目名" />
            </div>
            <div className="form-group">
              <label>项目描述</label>
              <textarea rows={3} value={proj.description} onChange={e => {
                const arr = [...profile.projects]; arr[i].description = e.target.value; setProfile(p => ({ ...p, projects: arr }));
              }} placeholder="项目背景、你的角色、技术亮点" />
            </div>
            <div className="form-group">
              <label>技术栈（逗号分隔）</label>
              <input
                value={proj.tech_stack.join(", ")}
                onChange={e => {
                  const arr = [...profile.projects];
                  arr[i].tech_stack = e.target.value.split(",").map(s => s.trim()).filter(Boolean);
                  setProfile(p => ({ ...p, projects: arr }));
                }}
                placeholder="Python, FastAPI, React"
              />
            </div>
            <button className="btn btn-danger" onClick={() => setProfile(p => ({ ...p, projects: p.projects.filter((_, j) => j !== i) }))}>删除</button>
          </div>
        ))}
        <button className="btn btn-secondary" onClick={addProject}>+ 添加项目</button>
      </div>

      <div className="card">
        <h2>求职意向</h2>
        <div className="form-group">
          <label>目标岗位（Enter 添加）</label>
          <div className="tag-input-row" style={{ marginBottom: 8 }}>
            <input
              value={roleInput}
              onChange={e => setRoleInput(e.target.value)}
              onKeyDown={e => handleKey(e, () => addTag("target_roles", roleInput, setRoleInput))}
              placeholder="如：数据分析师、后端工程师"
            />
            <button className="btn btn-secondary" onClick={() => addTag("target_roles", roleInput, setRoleInput)}>添加</button>
          </div>
          {profile.target_roles.map((r, i) => (
            <span key={i} className="tag tag-green" onClick={() => removeTag("target_roles", i)} style={{ cursor: "pointer" }} title="点击删除">{r} ×</span>
          ))}
        </div>
        <div className="form-group">
          <label>目标城市（Enter 添加）</label>
          <div className="tag-input-row" style={{ marginBottom: 8 }}>
            <input
              value={cityInput}
              onChange={e => setCityInput(e.target.value)}
              onKeyDown={e => handleKey(e, () => addTag("target_cities", cityInput, setCityInput))}
              placeholder="如：北京、上海"
            />
            <button className="btn btn-secondary" onClick={() => addTag("target_cities", cityInput, setCityInput)}>添加</button>
          </div>
          {profile.target_cities.map((c, i) => (
            <span key={i} className="tag tag-gray" onClick={() => removeTag("target_cities", i)} style={{ cursor: "pointer" }} title="点击删除">{c} ×</span>
          ))}
        </div>
        <div className="form-group">
          <label>目标公司（Enter 添加）</label>
          <div className="tag-input-row" style={{ marginBottom: 8 }}>
            <input
              value={companyInput}
              onChange={e => setCompanyInput(e.target.value)}
              onKeyDown={e => handleKey(e, () => addTag("target_companies", companyInput, setCompanyInput))}
              placeholder="如：字节跳动、外企在华"
            />
            <button className="btn btn-secondary" onClick={() => addTag("target_companies", companyInput, setCompanyInput)}>添加</button>
          </div>
          {profile.target_companies.map((c, i) => (
            <span key={i} className="tag tag-blue" onClick={() => removeTag("target_companies", i)} style={{ cursor: "pointer" }} title="点击删除">{c} ×</span>
          ))}
        </div>
      </div>

      <div className="btn-row">
        <button className="btn btn-primary" onClick={save} disabled={saving}>
          {saving ? "保存中..." : "保存画像"}
        </button>
        {msg && <span className={msg.includes("失败") ? "error-msg" : "success-msg"} style={{ alignSelf: "center" }}>{msg}</span>}
      </div>
    </div>
  );
}
