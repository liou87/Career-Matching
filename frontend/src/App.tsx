import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import ProfilePage from "./pages/ProfilePage";
import JobsPage from "./pages/JobsPage";
import AnalysisPage from "./pages/AnalysisPage";
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
        </nav>
        <main className="content">
          <Routes>
            <Route path="/" element={<ProfilePage />} />
            <Route path="/jobs" element={<JobsPage />} />
            <Route path="/analysis" element={<AnalysisPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
