export interface Education { degree: string; school: string; major: string; year: string; }
export interface Experience { title: string; company: string; duration: string; description: string; }
export interface Project { name: string; description: string; tech_stack: string[]; }

export interface ProfileData {
  name: string;
  education: Education[];
  skills: string[];
  experiences: Experience[];
  projects: Project[];
  target_roles: string[];
  target_cities: string[];
  target_companies: string[];
}

export interface Job {
  id: number;
  raw_jd?: string;
  title: string | null;
  company: string | null;
  city: string | null;
  salary_min: number | null;
  salary_max: number | null;
  required_skills: string[];
  preferred_skills?: string[];
  experience_required: string | null;
  education_required: string | null;
  responsibilities?: string[];
  source_url?: string | null;
  status?: string;
  parsed_at?: string;
}

export interface Gap { gap: string; importance: string; suggestion: string; }
export interface ActionItem { item: string; why_valuable?: string; priority: string; resource?: string; }
export interface ScoreBreakdown { skills: number; experience: number; education: number; other: number; }

export interface Analysis {
  id: number;
  job_id: number;
  match_score: number;
  score_breakdown?: ScoreBreakdown | null;
  matched_skills: string[];
  missing_skills: string[];
  strengths: string[];
  gaps: Gap[];
  action_items: ActionItem[];
  summary: string;
}

export interface SkillRankingItem {
  skill: string;
  job_count: number;
  category: string;
  originals: string[];
}

export type BatchStatus = "pending" | "running" | "done" | "failed";

export interface BatchAnalysis {
  id: number;
  status: BatchStatus;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  job_count: number;
  success_count: number;
  ranking?: SkillRankingItem[] | null;
  error?: string | null;
}

export interface AgentMessage {
  role: "user" | "assistant";
  content: string;
  tool_calls?: string[];   // 这条回答过程中调用过的工具名
}

/** 等待用户确认的写操作 */
export interface PendingAction {
  name: string;
  args: Record<string, unknown>;
  description?: string;
}

export interface AgentThread {
  thread_id: string;
  messages: AgentMessage[];
  pending: PendingAction[];
}

export interface Memory {
  id: string;
  content: string;
  updated_at: string;
}

/** /api/agent/chat 和 /api/agent/resume 的 SSE 事件 */
export type AgentEvent =
  | { type: "thread"; thread_id: string }
  | { type: "token"; text: string }
  | { type: "tool_call"; name: string; args: Record<string, unknown> }
  | { type: "tool_result"; name: string }
  | { type: "interrupt"; actions: PendingAction[] }
  | { type: "done"; thread_id: string }
  | { type: "error"; code: string; detail: string };

export interface ChecklistItem {
  id: number;
  content: string;
  importance: string | null;
  suggestion: string | null;
  status: "todo" | "done";
  category: "gap" | "action";
  created_at: string;
}

export interface InterviewQuestion {
  jd_requirement: string;
  question: string;
  category: string;
  relation: "strength" | "gap" | "neutral";
  answer_points: string[];
}

export interface InterviewPrep {
  id: number;
  job_id: number;
  questions: InterviewQuestion[];
  created_at: string;
}
