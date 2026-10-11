"""
差距标注界面：本地起一个小服务，在浏览器里校对 evals/dataset/labels.json。

运行（在 backend 目录下）：
    python -m evals.label_ui                # 打开 http://127.0.0.1:8765

保存时直接写回 labels.json。界面里刻意不显示模型的分析结果：
看着模型列出的缺失技能去标注，标准答案会被模型带偏，召回率就失去了意义。
只用标准库，不依赖应用本身，也不调用任何模型。
"""
import argparse
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DATASET_DIR = Path(__file__).resolve().parent / "dataset"


def load(labels_path: Path) -> dict:
    jobs = json.loads((DATASET_DIR / "jobs.json").read_text(encoding="utf-8"))
    profile = json.loads((DATASET_DIR / "profile.json").read_text(encoding="utf-8"))
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    return {
        "jobs": jobs,
        "labels": labels,
        "profile_skills": profile.get("skills") or [],
        "profile_projects": [
            {"name": p.get("name"), "description": p.get("description")} for p in profile.get("projects") or []
        ],
    }


def apply_label(labels: list[dict], job_id: int, missing: list[dict], reviewed: bool) -> dict:
    """更新一个岗位的标注：去掉空白和重复，别名至少包含技能名本身。返回更新后的条目。"""
    entry = next((x for x in labels if x["job_id"] == job_id), None)
    if entry is None:
        raise KeyError(f"没有岗位 {job_id} 的标注")
    cleaned, seen = [], set()
    for m in missing:
        skill = str(m.get("skill", "")).strip()
        if not skill or skill.lower() in seen:
            continue
        seen.add(skill.lower())
        aliases = []
        for a in [skill, *(m.get("aliases") or [])]:
            a = str(a).strip()
            if a and a.lower() not in {x.lower() for x in aliases}:
                aliases.append(a)
        cleaned.append({"skill": skill, "aliases": aliases})
    entry["missing"] = cleaned
    entry["reviewed"] = bool(reviewed)
    return entry


def save(path: Path, labels: list[dict]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(labels, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def make_handler(labels_path: Path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # 不刷屏
            pass

        def _send(self, status: int, body: bytes, content_type: str):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, data):
            self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            if self.path == "/":
                self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/api/data":
                self._json(200, load(labels_path))
            else:
                self._json(404, {"detail": "not found"})

        def do_POST(self):
            if not self.path.startswith("/api/labels/"):
                return self._json(404, {"detail": "not found"})
            try:
                job_id = int(self.path.rsplit("/", 1)[1])
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                labels = json.loads(labels_path.read_text(encoding="utf-8"))
                entry = apply_label(labels, job_id, body.get("missing") or [], body.get("reviewed", False))
                save(labels_path, labels)
                self._json(200, entry)
            except (KeyError, ValueError) as e:
                self._json(400, {"detail": str(e)})

    return Handler


PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>差距标注</title>
<style>
  :root { --bg:#f7f7f8; --card:#fff; --text:#1f2328; --muted:#656d76; --faint:#8c959f; --border:#d0d7de;
          --primary:#4f46e5; --primary-bg:#ede9fe; --ok:#1a7f37; --ok-bg:#dafbe1; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#0d1117; --card:#161b22; --text:#e6edf3; --muted:#9198a1; --faint:#6e7681; --border:#30363d;
            --primary:#818cf8; --primary-bg:#2d2a52; --ok:#3fb950; --ok-bg:#12261e; }
  }
  * { box-sizing: border-box; }
  body { margin:0; font:14px/1.6 -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; background:var(--bg); color:var(--text); }
  header { padding:14px 20px; border-bottom:1px solid var(--border); background:var(--card); display:flex; gap:16px; align-items:baseline; flex-wrap:wrap; }
  header h1 { font-size:17px; margin:0; }
  header .hint { color:var(--muted); font-size:13px; }
  .layout { display:grid; grid-template-columns: 220px 1fr 260px; gap:16px; padding:16px 20px; }
  @media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }
  .card { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:14px 16px; }
  .jobs button { display:flex; justify-content:space-between; gap:8px; width:100%; text-align:left; padding:7px 9px; margin-bottom:4px;
                 background:none; border:1px solid transparent; border-radius:7px; color:var(--text); cursor:pointer; font:inherit; }
  .jobs button:hover { border-color:var(--border); }
  .jobs button.active { background:var(--primary-bg); border-color:var(--primary); }
  .badge { font-size:11px; padding:0 6px; border-radius:9px; white-space:nowrap; align-self:center; }
  .badge.done { background:var(--ok-bg); color:var(--ok); }
  .badge.todo { color:var(--faint); border:1px solid var(--border); }
  h2 { font-size:16px; margin:0 0 2px; }
  .meta { color:var(--muted); font-size:13px; margin-bottom:12px; }
  h3 { font-size:13px; color:var(--muted); margin:16px 0 6px; font-weight:600; }
  .row { display:grid; grid-template-columns: 24px minmax(140px, 1fr) 1.3fr; gap:8px; align-items:center; padding:6px 0; border-bottom:1px solid var(--border); }
  .row:last-child { border-bottom:none; }
  .row input[type=text] { width:100%; padding:5px 8px; border:1px solid var(--border); border-radius:6px; background:var(--bg); color:var(--text); font:inherit; }
  .row input[type=text]:disabled { opacity:.35; }
  .row .remove { background:none; border:none; color:var(--faint); cursor:pointer; font:inherit; }
  .chips span { display:inline-flex; align-items:center; gap:4px; margin:0 6px 6px 0; padding:2px 8px; border:1px solid var(--border); border-radius:12px; font-size:13px; }
  .chips button { background:none; border:none; color:var(--primary); cursor:pointer; font-size:12px; padding:0; }
  ul.resp { margin:0; padding-left:18px; color:var(--muted); }
  .add { display:flex; gap:8px; margin-top:8px; }
  .add input { flex:1; padding:5px 8px; border:1px solid var(--border); border-radius:6px; background:var(--bg); color:var(--text); font:inherit; }
  .actions { display:flex; gap:10px; margin-top:16px; flex-wrap:wrap; align-items:center; }
  .btn { padding:7px 14px; border-radius:7px; border:1px solid var(--border); background:var(--card); color:var(--text); cursor:pointer; font:inherit; }
  .btn.primary { background:var(--primary); border-color:var(--primary); color:#fff; }
  .msg { color:var(--ok); font-size:13px; }
  .side h3:first-child { margin-top:0; }
  .side .skill { display:inline-block; margin:0 6px 6px 0; padding:1px 8px; border-radius:10px; background:var(--bg); border:1px solid var(--border); font-size:12px; }
  .side p { margin:0 0 8px; font-size:13px; color:var(--muted); }
</style>
</head>
<body>
<header>
  <h1>差距标注</h1>
  <span id="progress"></span>
  <span class="hint">勾选你真正缺少的技能，别名写模型可能用的说法（用逗号分隔）。只有「已校对」的岗位计入召回率。</span>
</header>
<div class="layout">
  <nav class="card jobs" id="jobs"></nav>
  <main class="card" id="main"></main>
  <aside class="card side" id="side"></aside>
</div>
<script>
let data, current = null, draft = [];

const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const splitAliases = s => s.split(/[,，、]/).map(x => x.trim()).filter(Boolean);
const labelOf = id => data.labels.find(l => l.job_id === id);

async function init() {
  data = await (await fetch("/api/data")).json();
  renderSide();
  select(data.jobs[0].job_id);
}

function renderJobs() {
  const done = data.labels.filter(l => l.reviewed).length;
  document.getElementById("progress").textContent = `已校对 ${done} / ${data.labels.length}`;
  document.getElementById("jobs").innerHTML = data.jobs.map(j => {
    const l = labelOf(j.job_id);
    return `<button class="${j.job_id === current ? "active" : ""}" onclick="select(${j.job_id})">
      <span>${j.job_id}. ${esc(j.title)}</span>
      <span class="badge ${l?.reviewed ? "done" : "todo"}">${l?.reviewed ? "已校对" : "未校对"}</span></button>`;
  }).join("");
}

function renderSide() {
  document.getElementById("side").innerHTML = `
    <h3>你的画像技能</h3>${data.profile_skills.map(s => `<span class="skill">${esc(s)}</span>`).join("")}
    <h3>你的项目</h3>${data.profile_projects.map(p => `<p><b>${esc(p.name)}</b>：${esc(p.description)}</p>`).join("")}`;
}

function select(id) {
  current = id;
  const job = data.jobs.find(j => j.job_id === id);
  const label = labelOf(id);
  const marked = new Map(label.missing.map(m => [m.skill, m.aliases]));
  // 草稿：必需技能逐条列出，草稿里标过的预先勾上；草稿里不属于必需技能的放到「其他差距」
  draft = (job.required_skills || []).map(s => ({ skill: s, checked: marked.has(s), aliases: (marked.get(s) || [s]).join("，"), required: true }));
  label.missing.filter(m => !(job.required_skills || []).includes(m.skill))
    .forEach(m => draft.push({ skill: m.skill, checked: true, aliases: m.aliases.join("，"), required: false }));
  renderJobs();
  renderMain(job);
}

function renderMain(job) {
  const rows = (items) => items.map(({ d, i }) => `
    <div class="row">
      <input type="checkbox" ${d.checked ? "checked" : ""} onchange="draft[${i}].checked=this.checked; draw()" title="是我的差距">
      <span>${esc(d.skill)}</span>
      <span style="display:flex;gap:6px"><input type="text" value="${esc(d.aliases)}" ${d.checked ? "" : "disabled"}
        oninput="draft[${i}].aliases=this.value" placeholder="别名，用逗号分隔">
        ${d.required ? "" : `<button class="remove" onclick="draft.splice(${i},1); draw()" title="删除">删除</button>`}</span>
    </div>`).join("");
  const indexed = draft.map((d, i) => ({ d, i }));
  document.getElementById("main").innerHTML = `
    <h2>${esc(job.title)}</h2>
    <div class="meta">${esc([job.company, job.city, job.experience_required, job.education_required].filter(Boolean).join(" · "))}</div>
    <h3>必需技能：勾选你真正缺少的</h3>${rows(indexed.filter(x => x.d.required)) || '<p class="meta">JD 没有列必需技能</p>'}
    <h3>其他差距（JD 里有、但不在必需技能里的）</h3>${rows(indexed.filter(x => !x.d.required)) || '<p class="meta">暂无</p>'}
    <div class="add"><input id="newSkill" placeholder="手动添加一项差距，如：RAG"><button class="btn" onclick="addSkill()">添加</button></div>
    <h3>加分技能</h3><div class="chips">${(job.preferred_skills || []).map((s, k) =>
      `<span>${esc(s)} <button onclick="addPreferred(${k})">加为差距</button></span>`).join("") || '<span class="meta">无</span>'}</div>
    <h3>职责</h3><ul class="resp">${(job.responsibilities || []).map(r => `<li>${esc(r)}</li>`).join("")}</ul>
    <div class="actions">
      <button class="btn primary" onclick="saveLabel(true)">保存并标为已校对</button>
      <button class="btn" onclick="saveLabel(false)">仅保存（不计入召回率）</button>
      <button class="btn" onclick="next()">下一个</button>
      <span class="msg" id="msg"></span>
    </div>`;
}

const draw = () => renderMain(data.jobs.find(j => j.job_id === current));

function addSkill() {
  const v = document.getElementById("newSkill").value.trim();
  if (v) { draft.push({ skill: v, checked: true, aliases: v, required: false }); draw(); }
}

function addPreferred(k) {
  const s = data.jobs.find(j => j.job_id === current).preferred_skills[k];
  if (!draft.some(d => d.skill === s)) { draft.push({ skill: s, checked: true, aliases: s, required: false }); draw(); }
}

async function saveLabel(reviewed) {
  const missing = draft.filter(d => d.checked).map(d => ({ skill: d.skill, aliases: splitAliases(d.aliases) }));
  const r = await fetch(`/api/labels/${current}`, { method: "POST", headers: { "Content-Type": "application/json" },
                                                   body: JSON.stringify({ missing, reviewed }) });
  if (!r.ok) { document.getElementById("msg").textContent = "保存失败"; return; }
  const saved = await r.json();
  data.labels = data.labels.map(l => l.job_id === current ? saved : l);
  renderJobs();
  document.getElementById("msg").textContent = reviewed ? `已保存，记为已校对（${saved.missing.length} 项差距）` : "已保存";
}

function next() {
  const ids = data.jobs.map(j => j.job_id);
  select(ids[(ids.indexOf(current) + 1) % ids.length]);
}

init();
</script>
</body>
</html>
"""


def main():
    p = argparse.ArgumentParser(description="差距标注界面")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--labels", type=Path, default=DATASET_DIR / "labels.json", help="标注文件路径")
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.labels))
    url = f"http://127.0.0.1:{args.port}"
    print(f"差距标注界面：{url}（标注文件 {args.labels}），按 Ctrl+C 结束")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
