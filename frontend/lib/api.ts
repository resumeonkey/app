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
  profile_name: string;
  english_level: "any" | "basic" | "conversational" | "professional" | "fluent";
  profile_tags: string;
  target_roles: string;
  excluded_roles: string;
  industry_experience: string;
  target_industries: string;
  citizenship: string;
  education_level: "none" | "technical" | "university";
  prioritize_treaty: boolean;
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
  // Application tracking
  job_url?: string | null;
  applied_at?: string | null;
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

export interface ProfilePreferences {
  profile_name?: string;
  english_level?: MasterSummary["english_level"];
  profile_tags?: string;
  target_roles?: string;
  excluded_roles?: string;
  industry_experience?: string;
  target_industries?: string;
  citizenship?: string;
  education_level?: MasterSummary["education_level"];
  prioritize_treaty?: boolean;
}

export const updateMasterPreferences = (id: string, prefs: ProfilePreferences) =>
  api.patch<MasterSummary>(`/api/master/${id}/preferences`, prefs).then((r) => r.data);

// ── Adaptations ────────────────────────────────────────────────────────────────

export const createAdaptation = (body: {
  job_description: string;
  user_instructions?: string;
  llm_provider: string;
  llm_model: string;
  job_url?: string;
}) => api.post<Adaptation>("/api/adaptations/", body).then((r) => r.data);

export const toggleApplied = (id: string) =>
  api.patch<Adaptation>(`/api/adaptations/${id}/applied`).then((r) => r.data);

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

// ── Job Search ─────────────────────────────────────────────────────────────────

export interface SearchParams {
  master_id?: string | null;   // which profile to search with; null = active
  job_title: string;
  custom_query: string;
  country: string;
  province: string;
  city: string;
  remote: "remote" | "hybrid" | "onsite" | "any";
  job_type: string[];
  experience_level: string[];
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: "CAD" | "USD";
  company_type: string[];
  company_size: string[];
  include_keywords: string[];
  exclude_keywords: string[];
  languages: string[];
  date_posted: "24h" | "3d" | "7d" | "30d" | "any";
  industries: string[];
  num_results: number;
  llm_provider: string;
  llm_model: string;
  // Filtros para inmigrantes / hispanohablantes
  lmia_only: boolean;
  bilingual_spanish: boolean;
  ccfta_check: boolean;
  // Nivel de inglés del candidato
  english_level: "any" | "basic" | "conversational" | "professional" | "fluent";
}

export interface JobResult {
  id: string;
  title: string;
  company: string;
  location: string;
  url: string;
  snippet: string;
  salary: string | null;
  date_posted: string | null;
  compatibility_score: number;
  treaty_boost?: number;
  matched_skills: string[];
  missing_skills: string[];
  score_summary: string;
  // Source + immigration fields
  source: "linkedin" | "jobbank" | "workopolis" | "eluta";
  lmia_approved: boolean;
  ccfta_eligible: boolean;
  cptpp_eligible: boolean;
  immigration_support: "yes" | "mentioned" | "no";
  bilingual_advantage: boolean;
  // English level fields
  english_barrier: boolean;
  english_required: "none" | "basic" | "conversational" | "professional" | "fluent" | "unknown";
  // Structured assessment
  confidence: "low" | "medium" | "high";
  blockers: string[];
  why_relevant: string[];
}

export interface SearchResponse {
  results: JobResult[];
  queries_used: string[];
  excluded_count?: number;
  scrape_failed?: boolean;
  profile_used?: string;
  english_level_used?: string;
}

export interface ExtractResponse {
  url: string;
  job_description: string;
  compatibility_score?: number;
  job_title?: string;
  company?: string;
  location?: string;
  salary?: string | null;
  matched_skills?: string[];
  missing_skills?: string[];
  score_summary?: string;
}

export interface SearchRecommendation {
  title: string;
  keywords: string;
  experience_level: string[];
  industries: string[];
  remote: "remote" | "hybrid" | "onsite" | "any";
  why: string;
  icon: string;
}

export const suggestSearchParams = (llm_provider = "anthropic", llm_model = "claude-haiku-4-5") =>
  api
    .get<{
      suggestions: Partial<SearchParams> & { skills_highlight?: string };
      recommendations: SearchRecommendation[];
    }>(
      `/api/search/suggest?llm_provider=${llm_provider}&llm_model=${llm_model}`
    )
    .then((r) => r.data);

export const runJobSearch = (params: SearchParams) =>
  api.post<SearchResponse>("/api/search/run", params).then((r) => r.data);

export const extractJobFromUrl = (url: string, llm_provider = "anthropic", llm_model = "claude-haiku-4-5") =>
  api
    .post<ExtractResponse>("/api/search/extract", { url, llm_provider, llm_model })
    .then((r) => r.data);

// ── Saved Jobs ─────────────────────────────────────────────────────────────────

export interface SavedJob {
  id: string;
  created_at: string;
  url: string;
  title: string | null;
  company: string | null;
  location: string | null;
  snippet: string | null;
  salary: string | null;
  date_posted: string | null;
  source: string | null;
  compatibility_score: number | null;
  matched_skills: string[];
  missing_skills: string[];
  score_summary: string | null;
  confidence: string | null;
  blockers: string[];
  why_relevant: string[];
  lmia_approved: boolean;
  ccfta_eligible: boolean;
  cptpp_eligible: boolean;
  immigration_support: string | null;
  bilingual_advantage: boolean;
  english_barrier: boolean;
  english_required: string | null;
  notes: string | null;
  applied_at: string | null;
}

export const listSavedJobs = () =>
  api.get<{ saved_jobs: SavedJob[] }>("/api/jobs/saved").then((r) => r.data.saved_jobs);

export const getSavedUrls = () =>
  api.get<{ urls: Record<string, string> }>("/api/jobs/saved/urls").then((r) => r.data.urls);

export const saveJob = (job: JobResult) =>
  api.post<SavedJob>("/api/jobs/saved", {
    url:                 job.url,
    title:               job.title,
    company:             job.company,
    location:            job.location,
    snippet:             job.snippet,
    salary:              job.salary,
    date_posted:         job.date_posted,
    source:              job.source,
    compatibility_score: job.compatibility_score,
    matched_skills:      job.matched_skills,
    missing_skills:      job.missing_skills,
    score_summary:       job.score_summary,
    confidence:          job.confidence,
    blockers:            job.blockers,
    why_relevant:        job.why_relevant,
    lmia_approved:       job.lmia_approved,
    ccfta_eligible:      job.ccfta_eligible,
    cptpp_eligible:      job.cptpp_eligible,
    immigration_support: job.immigration_support,
    bilingual_advantage: job.bilingual_advantage,
    english_barrier:     job.english_barrier,
    english_required:    job.english_required,
  }).then((r) => r.data);

export const unsaveJob = (id: string) =>
  api.delete(`/api/jobs/saved/${id}`);

export const unsaveJobByUrl = (url: string) =>
  api.delete("/api/jobs/saved/by-url", { data: { url } });

export const patchSavedJob = (id: string, patch: { notes?: string; applied?: boolean }) =>
  api.patch<SavedJob>(`/api/jobs/saved/${id}`, patch).then((r) => r.data);

// ── Resume v2 (data-driven, clean generation) ────────────────────────────────

export interface ResumeProfile {
  profile_id: string;
  name: string;
  title: string;
}

export const listResumeProfiles = () =>
  api.get<{ profiles: ResumeProfile[] }>("/api/resume/profiles").then((r) => r.data.profiles);

export interface GenerateResumeBody {
  profile_id: string;
  template: "classic" | "iris";
  job_description?: string;
  user_instructions?: string;
  llm_provider?: string;
  llm_model?: string;
}

// Generates the DOCX server-side and triggers a browser download.
export const generateAndDownloadResume = async (body: GenerateResumeBody) => {
  const res = await api.post("/api/resume/generate", body, { responseType: "blob" });
  const blob = new Blob([res.data], {
    type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${body.profile_id}_resume.docx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
};
