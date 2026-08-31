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
export interface ActionItem { item: string; priority: string; resource?: string; }
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

export interface ChecklistItem {
  id: number;
  content: string;
  importance: string | null;
  suggestion: string | null;
  status: "todo" | "done";
  created_at: string;
}
