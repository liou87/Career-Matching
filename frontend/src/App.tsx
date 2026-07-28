import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import ProfilePage from "./pages/ProfilePage";
import JobsPage from "./pages/JobsPage";
import JobDetailPage from "./pages/JobDetailPage";
import AnalysisPage from "./pages/AnalysisPage";
import ChecklistPage from "./pages/ChecklistPage";
import "./App.css";

export default function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <nav className="sidebar">
          <div className="logo">求职助手</div>
          <NavLink to="/" end className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>
            个人画像
          </NavLink>
          <NavLink to="/jobs" className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>
            岗位库
          </NavLink>
          <NavLink to="/analysis" className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>
            匹配分析
          </NavLink>
          <NavLink to="/checklist" className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>
            我的清单
          </NavLink>
        </nav>
        <main className="content">
          <Routes>
            <Route path="/" element={<ProfilePage />} />
            <Route path="/jobs" element={<JobsPage />} />
            <Route path="/jobs/:id" element={<JobDetailPage />} />
            <Route path="/analysis" element={<AnalysisPage />} />
            <Route path="/checklist" element={<ChecklistPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
