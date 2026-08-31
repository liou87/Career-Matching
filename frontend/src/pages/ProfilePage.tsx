import { useEffect, useState } from "react";
import api from "../api";
import type { ProfileData } from "../types";
import { updateItem, removeItem } from "../lib/list";
import TagInput from "../components/TagInput";

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
                <input value={edu.degree} onChange={e => setProfile(p => ({ ...p, education: updateItem(p.education, i, "degree", e.target.value) }))} placeholder="硕士 / 学士" />
              </div>
              <div className="form-group" style={{ margin: 0 }}>
                <label>学校</label>
                <input value={edu.school} onChange={e => setProfile(p => ({ ...p, education: updateItem(p.education, i, "school", e.target.value) }))} placeholder="学校名称" />
              </div>
              <div className="form-group" style={{ margin: 0 }}>
                <label>专业</label>
                <input value={edu.major} onChange={e => setProfile(p => ({ ...p, education: updateItem(p.education, i, "major", e.target.value) }))} placeholder="专业方向" />
              </div>
              <div className="form-group" style={{ margin: 0 }}>
                <label>毕业年份</label>
                <input value={edu.year} onChange={e => setProfile(p => ({ ...p, education: updateItem(p.education, i, "year", e.target.value) }))} placeholder="2025" />
              </div>
            </div>
            <button className="btn btn-danger" onClick={() => setProfile(p => ({ ...p, education: removeItem(p.education, i) }))}>删除</button>
          </div>
        ))}
        <button className="btn btn-secondary" onClick={addEdu}>+ 添加教育经历</button>
      </div>

      <div className="card">
        <h2>技能标签</h2>
        <TagInput
          values={profile.skills}
          onChange={v => setProfile(p => ({ ...p, skills: v }))}
          placeholder="输入技能后按 Enter（如 Python、SQL、React）"
          tagClassName="tag-blue"
        />
      </div>

      <div className="card">
        <h2>实习 / 工作经历</h2>
        {profile.experiences.map((exp, i) => (
          <div key={i} style={{ marginBottom: 16, paddingBottom: 16, borderBottom: "1px solid #f0f0f0" }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
              <div className="form-group" style={{ margin: 0 }}>
                <label>职位</label>
                <input value={exp.title} onChange={e => setProfile(p => ({ ...p, experiences: updateItem(p.experiences, i, "title", e.target.value) }))} placeholder="实习生 / 工程师" />
              </div>
              <div className="form-group" style={{ margin: 0 }}>
                <label>公司</label>
                <input value={exp.company} onChange={e => setProfile(p => ({ ...p, experiences: updateItem(p.experiences, i, "company", e.target.value) }))} placeholder="公司名称" />
              </div>
              <div className="form-group" style={{ margin: 0 }}>
                <label>时间段</label>
                <input value={exp.duration} onChange={e => setProfile(p => ({ ...p, experiences: updateItem(p.experiences, i, "duration", e.target.value) }))} placeholder="2024.06 - 2024.09" />
              </div>
            </div>
            <div className="form-group">
              <label>工作描述</label>
              <textarea rows={3} value={exp.description} onChange={e => setProfile(p => ({ ...p, experiences: updateItem(p.experiences, i, "description", e.target.value) }))} placeholder="简述主要工作内容和成果" />
            </div>
            <button className="btn btn-danger" onClick={() => setProfile(p => ({ ...p, experiences: removeItem(p.experiences, i) }))}>删除</button>
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
              <input value={proj.name} onChange={e => setProfile(p => ({ ...p, projects: updateItem(p.projects, i, "name", e.target.value) }))} placeholder="项目名" />
            </div>
            <div className="form-group">
              <label>项目描述</label>
              <textarea rows={3} value={proj.description} onChange={e => setProfile(p => ({ ...p, projects: updateItem(p.projects, i, "description", e.target.value) }))} placeholder="项目背景、你的角色、技术亮点" />
            </div>
            <div className="form-group">
              <label>技术栈（逗号分隔）</label>
              <input
                value={proj.tech_stack.join(", ")}
                onChange={e => {
                  const tech_stack = e.target.value.split(",").map(s => s.trim()).filter(Boolean);
                  setProfile(p => ({ ...p, projects: updateItem(p.projects, i, "tech_stack", tech_stack) }));
                }}
                placeholder="Python, FastAPI, React"
              />
            </div>
            <button className="btn btn-danger" onClick={() => setProfile(p => ({ ...p, projects: removeItem(p.projects, i) }))}>删除</button>
          </div>
        ))}
        <button className="btn btn-secondary" onClick={addProject}>+ 添加项目</button>
      </div>

      <div className="card">
        <h2>求职意向</h2>
        <div className="form-group">
          <label>目标岗位（Enter 添加）</label>
          <TagInput
            values={profile.target_roles}
            onChange={v => setProfile(p => ({ ...p, target_roles: v }))}
            placeholder="如：数据分析师、后端工程师"
            tagClassName="tag-green"
          />
        </div>
        <div className="form-group">
          <label>目标城市（Enter 添加）</label>
          <TagInput
            values={profile.target_cities}
            onChange={v => setProfile(p => ({ ...p, target_cities: v }))}
            placeholder="如：北京、上海"
            tagClassName="tag-gray"
          />
        </div>
        <div className="form-group">
          <label>目标公司（Enter 添加）</label>
          <TagInput
            values={profile.target_companies}
            onChange={v => setProfile(p => ({ ...p, target_companies: v }))}
            placeholder="如：字节跳动、外企在华"
            tagClassName="tag-blue"
          />
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
