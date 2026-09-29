## README 与 Markdown 规范

### 颜色
- README 里不出现任何硬编码颜色。颜色由 GitHub 主题决定
- 提示框用 GitHub 原生 alerts：`> [!NOTE]` / `[!TIP]` / `[!IMPORTANT]` / `[!WARNING]` / `[!CAUTION]`
  不要手写 `> ⚠️ **注意**` 这种
- Mermaid 图里禁止出现 `fill:`、`classDef`、`%%{init: theme}%%`
  需要分组用 subgraph
- 禁止 `<span style="color:">` 和 `$\color{}$`
- 徽章最多 4 个，全部 `?style=flat-square`，颜色统一

### 结构（Google Markdown Style Guide）
- 一个 H1，与文件名一致；ATX 风格标题（`##`），不用下划线式
- 标题必须具体：写 "CareerMatch 架构" 而不是 "架构"，不用 "Summary"/"Example" 这类泛称
- 代码块必须用三个反引号且标注语言
- 表格只用于需要快速横向扫视的数据。三行两列的东西写成列表
- 正文 80 字符换行（链接、表格、标题、代码块除外）
- 标题前后留空行

### 内容
- 最小可用文档优先：A small set of fresh and accurate docs is better than a
  sprawling, loose assembly
- README 不超过 150 行，细节移到 docs/ 并链接
- 标题不带 emoji，正文不用 emoji
