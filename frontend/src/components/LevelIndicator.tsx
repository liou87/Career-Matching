type Level = "high" | "medium" | "low";

function normalizeLevel(value: string): Level {
  if (value === "高" || value === "high") return "high";
  if (value === "中" || value === "medium") return "medium";
  return "low";
}

const dotClass: Record<Level, string> = { high: "dot-high", medium: "dot-mid", low: "dot-low" };
const tagClass: Record<Level, string> = { high: "tag-level-high", medium: "tag-level-medium", low: "tag-level-low" };

export function LevelDot({ value }: { value: string }) {
  return <div className={`priority-dot ${dotClass[normalizeLevel(value)]}`} />;
}

export function LevelTag({ value, label }: { value: string; label?: string }) {
  return <span className={`tag ${tagClass[normalizeLevel(value)]}`}>{label ?? value}</span>;
}
