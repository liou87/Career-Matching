import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import ProfilePage from "./pages/ProfilePage";
import JobsPage from "./pages/JobsPage";
import JobDetailPage from "./pages/JobDetailPage";
import AnalysisPage from "./pages/AnalysisPage";
import ChecklistPage from "./pages/ChecklistPage";
import SkillGapsPage from "./pages/SkillGapsPage";
import AssistantPage from "./pages/AssistantPage";
import { ProfileIcon, JobsIcon, AnalysisIcon, ChecklistIcon, GapsIcon, ChatIcon, SunIcon, MoonIcon } from "./components/Icons";
import "./App.css";

type Theme = "light" | "dark";

function getInitialTheme(): Theme {
  const stored = localStorage.getItem("theme");
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  return (
    <BrowserRouter>
      <div className="app">
        <nav className="sidebar">
          <div className="logo">求职助手</div>
          <NavLink to="/" end className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>
            <ProfileIcon /> 个人画像
          </NavLink>
          <NavLink to="/jobs" className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>
            <JobsIcon /> 岗位库
          </NavLink>
          <NavLink to="/analysis" className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>
            <AnalysisIcon /> 匹配分析
          </NavLink>
          <NavLink to="/skill-gaps" className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>
            <GapsIcon /> 技能缺口
          </NavLink>
          <NavLink to="/checklist" className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>
            <ChecklistIcon /> 我的清单
          </NavLink>
          <NavLink to="/assistant" className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>
            <ChatIcon /> AI 助手
          </NavLink>
          <button
            className="theme-toggle"
            onClick={() => setTheme(t => t === "light" ? "dark" : "light")}
            title={theme === "light" ? "切换到深色模式" : "切换到浅色模式"}
          >
            {theme === "light" ? <MoonIcon width={16} height={16} /> : <SunIcon width={16} height={16} />}
            {theme === "light" ? "深色模式" : "浅色模式"}
          </button>
        </nav>
        <main className="content">
          <Routes>
            <Route path="/" element={<ProfilePage />} />
            <Route path="/jobs" element={<JobsPage />} />
            <Route path="/jobs/:id" element={<JobDetailPage />} />
            <Route path="/analysis" element={<AnalysisPage />} />
            <Route path="/skill-gaps" element={<SkillGapsPage />} />
            <Route path="/checklist" element={<ChecklistPage />} />
            <Route path="/assistant" element={<AssistantPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
