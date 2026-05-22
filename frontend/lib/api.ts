import axios from "axios";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
});

// ── Types ──────────────────────────────────────────────────────────────────────

export interface MasterSummary {
  id: string;
  original_filename: string;
  candidate_name: string | null;
  is_active: boolean;
  created_at: string;
  notes: string | null;
  sections_detected: string[];
}

export interface MasterDetail extends MasterSummary {
  full_text: string | null;
  sections: Record<string, { raw_text: string; para_indices: number[] }> | null;
}

export interface BlockChanged {
  section: string;
  reason: string;
  original: string;
  adapted: string;
}

export interface JobAnalysis {
  job_title?: string;
  seniority_level?: string;
  industry?: string;
  required_experience_years?: number;
  language_requirements?: string[];
  ats_keywords?: string[];
}

export interface Adaptation {
  id: string;
  master_id: string;
  job_title: string | null;
  company_name: string | null;
  status: "pending" | "processing" | "done" | "error";
  created_at: string;
  sections_changed: string[];
  job_description?: string;
  user_instructions?: string | null;
  job_analysis?: JobAnalysis | null;
  blocks_changed?: BlockChanged[] | null;
  llm_provider: string;
  llm_model: string;
  error_msg?: string | null;
}

// ── Master ─────────────────────────────────────────────────────────────────────

export const getActiveMaster = () =>
  api.get<MasterDetail>("/api/master/active").then((r) => r.data);

export const listMasters = () =>
  api.get<MasterSummary[]>("/api/master/").then((r) => r.data);

export const uploadMaster = (formData: FormData) =>
  api.post<MasterDetail>("/api/master/upload", formData).then((r) => r.data);

export const activateMaster = (id: string) =>
  api.patch<MasterSummary>(`/api/master/${id}/activate`).then((r) => r.data);

export const deleteMaster = (id: string) => api.delete(`/api/master/${id}`);

// ── Adaptations ────────────────────────────────────────────────────────────────

export const createAdaptation = (body: {
  job_description: string;
  user_instructions?: string;
  llm_provider: string;
  llm_model: string;
}) => api.post<Adaptation>("/api/adaptations/", body).then((r) => r.data);

export const listAdaptations = () =>
  api.get<Adaptation[]>("/api/adaptations/").then((r) => r.data);

export const getAdaptation = (id: string) =>
  api.get<Adaptation>(`/api/adaptations/${id}`).then((r) => r.data);

export const deleteAdaptation = (id: string) =>
  api.delete(`/api/adaptations/${id}`);

// ── Context ────────────────────────────────────────────────────────────────────

export interface UserContext {
  id: string;
  title: string;
  content: string;
  is_active: boolean;
  created_at: string;
}

export const listContexts = () =>
  api.get<UserContext[]>("/api/context/").then((r) => r.data);

export const addTextContext = (title: string, content: string) => {
  const fd = new FormData();
  fd.append("title", title);
  fd.append("content", content);
  return api.post<UserContext>("/api/context/text", fd).then((r) => r.data);
};

export const addFileContext = (title: string, file: File) => {
  const fd = new FormData();
  fd.append("title", title);
  fd.append("file", file);
  return api.post<UserContext>("/api/context/file", fd).then((r) => r.data);
};

export const toggleContext = (id: string) =>
  api.patch<UserContext>(`/api/context/${id}/toggle`).then((r) => r.data);

export const deleteContext = (id: string) =>
  api.delete(`/api/context/${id}`);

// ── Export ─────────────────────────────────────────────────────────────────────

export const getDownloadUrl = (adaptationId: string) =>
  `${api.defaults.baseURL}/api/export/${adaptationId}/docx`;
