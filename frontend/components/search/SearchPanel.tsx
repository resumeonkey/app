"use client";
import { useState } from "react";
import { type SearchParams } from "@/lib/api";

const PROVINCES = [
  "Alberta", "British Columbia", "Manitoba", "New Brunswick",
  "Newfoundland and Labrador", "Northwest Territories", "Nova Scotia",
  "Nunavut", "Ontario", "Prince Edward Island", "Quebec",
  "Saskatchewan", "Yukon",
];

const INDUSTRIES = [
  "Technology", "Software / SaaS", "Finance / Fintech", "Healthcare / Medtech",
  "E-commerce / Retail", "Education / Edtech", "Government / Public Sector",
  "Non-profit", "Consulting", "Manufacturing", "Media / Entertainment",
  "Real Estate", "Energy / Cleantech", "Telecommunications", "Logistics / Supply Chain",
];

const LLM_OPTIONS = [
  { provider: "anthropic", model: "claude-haiku-4-5",        label: "Claude Haiku · Anthropic" },
  { provider: "groq",      model: "llama-3.3-70b-versatile", label: "Llama 3.3 70B · Groq (gratis)" },
  { provider: "gemini",    model: "gemini-2.0-flash",        label: "Gemini 2.0 Flash · Google (gratis)" },
];

const DEFAULT_PARAMS: SearchParams = {
  master_id: null,
  job_title: "",
  custom_query: "",
  country: "Canada",
  province: "",
  city: "",
  remote: "any",
  job_type: [],
  experience_level: [],
  salary_min: null,
  salary_max: null,
  salary_currency: "CAD",
  company_type: [],
  company_size: [],
  include_keywords: [],
  exclude_keywords: [],
  languages: ["english"],
  date_posted: "any",
  industries: [],
  num_results: 8,
  llm_provider: "anthropic",
  llm_model: "claude-haiku-4-5",
  lmia_only: false,
  bilingual_spanish: false,
  ccfta_check: false,
  english_level: "any",
};

interface MasterOption {
  id: string;
  profile_name: string;
  original_filename: string;
  is_active: boolean;
}

interface Props {
  onSearch: (params: SearchParams) => void;
  loading: boolean;
  masters?: MasterOption[];          // available profiles to search with
  activeMasterId?: string | null;    // currently active master id
}

export function SearchPanel({ onSearch, loading, masters = [], activeMasterId = null }: Props) {
  const [params, setParams] = useState<SearchParams>({
    ...DEFAULT_PARAMS,
    master_id: activeMasterId,
  });
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [kwInput, setKwInput] = useState("");
  const [exKwInput, setExKwInput] = useState("");
  const [selectedLLM, setSelectedLLM] = useState(0);

  const set = <K extends keyof SearchParams>(key: K, value: SearchParams[K]) =>
    setParams((p) => ({ ...p, [key]: value }));

  const toggleList = (key: keyof SearchParams, value: string) => {
    const current = (params[key] as string[]) || [];
    set(key as any, current.includes(value)
      ? current.filter((x) => x !== value)
      : [...current, value]
    );
  };

  const addKeyword = (type: "include" | "exclude") => {
    if (type === "include" && kwInput.trim()) {
      set("include_keywords", [...params.include_keywords, kwInput.trim()]);
      setKwInput("");
    }
    if (type === "exclude" && exKwInput.trim()) {
      set("exclude_keywords", [...params.exclude_keywords, exKwInput.trim()]);
      setExKwInput("");
    }
  };

  const handleLLMChange = (i: number) => {
    setSelectedLLM(i);
    set("llm_provider", LLM_OPTIONS[i].provider);
    set("llm_model", LLM_OPTIONS[i].model);
  };

  const handleSubmit = () => {
    if (!params.job_title.trim() && !params.custom_query.trim()) return;
    onSearch(params);
  };

  // ── Build direct URLs for each job board ─────────────────────────────────
  const buildExternalUrls = () => {
    const query  = encodeURIComponent((params.custom_query || params.job_title).trim());
    const loc    = encodeURIComponent([params.city, params.province, params.country].filter(Boolean).join(", ") || "Canada");
    const locCA  = encodeURIComponent([params.city, params.province].filter(Boolean).join(", ") || "Canada");

    // LinkedIn remote filter
    const liRemote = params.remote === "remote" ? "&f_WT=2"
                   : params.remote === "hybrid"  ? "&f_WT=3"
                   : params.remote === "onsite"  ? "&f_WT=1" : "";
    // LinkedIn date posted
    const liDate   = params.date_posted === "24h" ? "&f_TPR=r86400"
                   : params.date_posted === "3d"  ? "&f_TPR=r259200"
                   : params.date_posted === "7d"  ? "&f_TPR=r604800"
                   : params.date_posted === "30d" ? "&f_TPR=r2592000" : "";

    return [
      {
        id:    "linkedin",
        label: "LinkedIn",
        icon:  "💼",
        color: "hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700",
        url:   `https://www.linkedin.com/jobs/search/?keywords=${query}&location=${loc}${liRemote}${liDate}`,
      },
      {
        id:    "jobbank",
        label: "Job Bank",
        icon:  "🍁",
        color: "hover:border-red-300 hover:bg-red-50 hover:text-red-700",
        url:   `https://www.jobbank.gc.ca/jobsearch/jobsearch?searchstring=${query}&locationstring=${locCA}${params.lmia_only ? "&mid=" : ""}`,
      },
      {
        id:    "workopolis",
        label: "Workopolis",
        icon:  "🇨🇦",
        color: "hover:border-orange-300 hover:bg-orange-50 hover:text-orange-700",
        url:   `https://www.workopolis.com/jobsearch/find-jobs?q=${query}&l=${locCA}`,
      },
      {
        id:    "eluta",
        label: "Eluta",
        icon:  "🔍",
        color: "hover:border-teal-300 hover:bg-teal-50 hover:text-teal-700",
        url:   `https://www.eluta.ca/search?q=${query}&l=${loc}`,
      },
      {
        id:    "indeed",
        label: "Indeed",
        icon:  "🔎",
        color: "hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700",
        url:   `https://ca.indeed.com/jobs?q=${query}&l=${locCA}${params.remote === "remote" ? "&remotejob=1" : ""}`,
      },
      {
        id:    "glassdoor",
        label: "Glassdoor",
        icon:  "🪟",
        color: "hover:border-green-300 hover:bg-green-50 hover:text-green-700",
        url:   `https://www.glassdoor.ca/Job/jobs.htm?sc.keyword=${query}&locT=N`,
      },
    ];
  };

  const ToggleChip = ({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) => (
    <button
      onClick={onClick}
      className={`px-3 py-1 rounded-full text-xs border transition-all ${
        active
          ? "bg-indigo-100 border-indigo-400 text-indigo-700 font-medium"
          : "border-gray-200 text-gray-500 hover:border-gray-400"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="space-y-5">
      {/* ── Profile selector (only when 2+ profiles exist) ─────────────────── */}
      {masters.length > 1 && (
        <div>
          <label className="label">Buscar con el perfil</label>
          <div className="flex flex-wrap gap-2">
            {masters.map((m) => {
              const selected = (params.master_id ?? activeMasterId) === m.id;
              const name = m.profile_name || m.original_filename;
              return (
                <button
                  key={m.id}
                  onClick={() => set("master_id", m.id)}
                  className={`px-3 py-1.5 rounded-lg border text-xs transition-all ${
                    selected
                      ? "border-indigo-500 bg-indigo-50 text-indigo-700 font-medium"
                      : "border-gray-200 text-gray-500 hover:border-indigo-300"
                  }`}
                  title={m.original_filename}
                >
                  {name}{m.is_active && <span className="ml-1 text-[9px] opacity-60">(activo)</span>}
                </button>
              );
            })}
          </div>
          <p className="text-[11px] text-gray-400 mt-1">
            Cada perfil usa sus propios roles objetivo, exclusiones e industrias.
          </p>
        </div>
      )}

      {/* ── Job title ─────────────────────────────────────────────────────── */}
      <div>
        <label className="label">Puesto que buscas</label>
        <input
          className="input"
          placeholder="Ej: Senior Software Engineer, Data Analyst, Project Manager…"
          value={params.job_title}
          onChange={(e) => set("job_title", e.target.value)}
        />
      </div>

      {/* ── Location ──────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <label className="label">País</label>
          <select
            className="input"
            value={params.country}
            onChange={(e) => set("country", e.target.value)}
          >
            <option value="Canada">Canadá</option>
            <option value="United States">Estados Unidos</option>
            <option value="Mexico">México</option>
            <option value="Colombia">Colombia</option>
            <option value="Argentina">Argentina</option>
            <option value="Chile">Chile</option>
            <option value="Spain">España</option>
          </select>
        </div>
        {params.country === "Canada" && (
          <div>
            <label className="label">Provincia</label>
            <select
              className="input"
              value={params.province}
              onChange={(e) => set("province", e.target.value)}
            >
              <option value="">Cualquier provincia</option>
              {PROVINCES.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
        )}
        <div>
          <label className="label">Ciudad</label>
          <input
            className="input"
            placeholder="Ej: Vancouver, Toronto…"
            value={params.city}
            onChange={(e) => set("city", e.target.value)}
          />
        </div>
      </div>

      {/* ── Modalidad ─────────────────────────────────────────────────────── */}
      <div>
        <label className="label">Modalidad de trabajo</label>
        <div className="flex flex-wrap gap-2">
          {(["any", "remote", "hybrid", "onsite"] as const).map((opt) => (
            <ToggleChip
              key={opt}
              label={{ any: "Cualquiera", remote: "🌐 Remoto", hybrid: "🏠 Híbrido", onsite: "🏢 Presencial" }[opt]}
              active={params.remote === opt}
              onClick={() => set("remote", opt)}
            />
          ))}
        </div>
      </div>

      {/* ── Experience level ──────────────────────────────────────────────── */}
      <div>
        <label className="label">Nivel de experiencia</label>
        <div className="flex flex-wrap gap-2">
          {[
            { val: "entry", label: "Junior / Entry" },
            { val: "mid",   label: "Mid-level" },
            { val: "senior", label: "Senior" },
            { val: "lead",  label: "Lead / Staff" },
            { val: "executive", label: "Director / VP" },
          ].map(({ val, label }) => (
            <ToggleChip
              key={val}
              label={label}
              active={params.experience_level.includes(val)}
              onClick={() => toggleList("experience_level", val)}
            />
          ))}
        </div>
      </div>

      {/* ── Industries ────────────────────────────────────────────────────── */}
      <div>
        <label className="label">Industria (multi-selección)</label>
        <div className="flex flex-wrap gap-2">
          {INDUSTRIES.map((ind) => (
            <ToggleChip
              key={ind}
              label={ind}
              active={params.industries.includes(ind)}
              onClick={() => toggleList("industries", ind)}
            />
          ))}
        </div>
      </div>

      {/* ── Advanced toggle ───────────────────────────────────────────────── */}
      <button
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="text-sm text-indigo-600 hover:text-indigo-800 flex items-center gap-1"
      >
        {showAdvanced ? "▲" : "▼"} Parámetros avanzados
      </button>

      {showAdvanced && (
        <div className="space-y-5 border-t border-gray-100 pt-4">
          {/* Job type */}
          <div>
            <label className="label">Tipo de empleo</label>
            <div className="flex flex-wrap gap-2">
              {[
                { val: "full-time",   label: "Tiempo completo" },
                { val: "part-time",   label: "Medio tiempo" },
                { val: "contract",    label: "Contrato" },
                { val: "internship",  label: "Pasantía / Co-op" },
              ].map(({ val, label }) => (
                <ToggleChip
                  key={val}
                  label={label}
                  active={params.job_type.includes(val)}
                  onClick={() => toggleList("job_type", val)}
                />
              ))}
            </div>
          </div>

          {/* Salary */}
          <div>
            <label className="label">Rango salarial ({params.salary_currency})</label>
            <div className="flex items-center gap-3">
              <input
                type="number"
                className="input w-32"
                placeholder="Mínimo"
                value={params.salary_min ?? ""}
                onChange={(e) => set("salary_min", e.target.value ? parseInt(e.target.value) : null)}
              />
              <span className="text-gray-400">–</span>
              <input
                type="number"
                className="input w-32"
                placeholder="Máximo"
                value={params.salary_max ?? ""}
                onChange={(e) => set("salary_max", e.target.value ? parseInt(e.target.value) : null)}
              />
              <select
                className="input w-24"
                value={params.salary_currency}
                onChange={(e) => set("salary_currency", e.target.value as "CAD" | "USD")}
              >
                <option value="CAD">CAD</option>
                <option value="USD">USD</option>
              </select>
            </div>
          </div>

          {/* Company type */}
          <div>
            <label className="label">Tipo de empresa</label>
            <div className="flex flex-wrap gap-2">
              {[
                { val: "startup",    label: "Startup" },
                { val: "mid-size",   label: "Mediana empresa" },
                { val: "enterprise", label: "Gran empresa" },
                { val: "non-profit", label: "ONG / Non-profit" },
                { val: "government", label: "Gobierno / Público" },
              ].map(({ val, label }) => (
                <ToggleChip
                  key={val}
                  label={label}
                  active={params.company_type.includes(val)}
                  onClick={() => toggleList("company_type", val)}
                />
              ))}
            </div>
          </div>

          {/* Company size */}
          <div>
            <label className="label">Tamaño de empresa</label>
            <div className="flex flex-wrap gap-2">
              {[
                { val: "small",      label: "1–50 empleados" },
                { val: "medium",     label: "51–200" },
                { val: "large",      label: "201–1,000" },
                { val: "enterprise", label: "1,000+" },
              ].map(({ val, label }) => (
                <ToggleChip
                  key={val}
                  label={label}
                  active={params.company_size.includes(val)}
                  onClick={() => toggleList("company_size", val)}
                />
              ))}
            </div>
          </div>

          {/* Keywords */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="label">Palabras clave (incluir)</label>
              <div className="flex gap-2">
                <input
                  className="input flex-1"
                  placeholder="Ej: React, AWS…"
                  value={kwInput}
                  onChange={(e) => setKwInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && addKeyword("include")}
                />
                <button className="btn-secondary px-3" onClick={() => addKeyword("include")}>+</button>
              </div>
              <div className="flex flex-wrap gap-1 mt-2">
                {params.include_keywords.map((kw) => (
                  <span
                    key={kw}
                    className="badge bg-green-100 text-green-700 cursor-pointer"
                    onClick={() => set("include_keywords", params.include_keywords.filter((k) => k !== kw))}
                  >
                    {kw} ×
                  </span>
                ))}
              </div>
            </div>
            <div>
              <label className="label">Palabras clave (excluir)</label>
              <div className="flex gap-2">
                <input
                  className="input flex-1"
                  placeholder="Ej: PHP, Salesforce…"
                  value={exKwInput}
                  onChange={(e) => setExKwInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && addKeyword("exclude")}
                />
                <button className="btn-secondary px-3" onClick={() => addKeyword("exclude")}>+</button>
              </div>
              <div className="flex flex-wrap gap-1 mt-2">
                {params.exclude_keywords.map((kw) => (
                  <span
                    key={kw}
                    className="badge bg-red-100 text-red-700 cursor-pointer"
                    onClick={() => set("exclude_keywords", params.exclude_keywords.filter((k) => k !== kw))}
                  >
                    {kw} ×
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Language */}
          <div>
            <label className="label">Idioma del puesto</label>
            <div className="flex flex-wrap gap-2">
              {[
                { val: "english",   label: "English" },
                { val: "french",    label: "Français" },
                { val: "spanish",   label: "Español" },
                { val: "bilingual", label: "Bilingual" },
              ].map(({ val, label }) => (
                <ToggleChip
                  key={val}
                  label={label}
                  active={params.languages.includes(val)}
                  onClick={() => toggleList("languages", val)}
                />
              ))}
            </div>
          </div>

          {/* Date posted */}
          <div>
            <label className="label">Fecha de publicación</label>
            <div className="flex flex-wrap gap-2">
              {[
                { val: "24h",  label: "Últimas 24h" },
                { val: "3d",   label: "Últimos 3 días" },
                { val: "7d",   label: "Última semana" },
                { val: "30d",  label: "Último mes" },
                { val: "any",  label: "Cualquier fecha" },
              ].map(({ val, label }) => (
                <ToggleChip
                  key={val}
                  label={label}
                  active={params.date_posted === val}
                  onClick={() => set("date_posted", val as SearchParams["date_posted"])}
                />
              ))}
            </div>
          </div>

          {/* Custom query override */}
          <div>
            <label className="label">Consulta personalizada (sobreescribe generación automática)</label>
            <input
              className="input font-mono text-xs"
              placeholder='Ej: "product manager" remote Canada site:linkedin.com'
              value={params.custom_query}
              onChange={(e) => set("custom_query", e.target.value)}
            />
          </div>

          {/* Num results */}
          <div>
            <label className="label">Número de resultados (máx. 20)</label>
            <input
              type="range"
              min={3}
              max={20}
              step={1}
              value={params.num_results}
              onChange={(e) => set("num_results", parseInt(e.target.value))}
              className="w-full"
            />
            <p className="text-xs text-gray-400 mt-0.5">{params.num_results} resultados</p>
          </div>
        </div>
      )}

      {/* ── Inmigrante / Hispanohablante ─────────────────────────────────── */}
      <div className="border border-indigo-100 rounded-xl p-4 bg-indigo-50/40 space-y-3">
        <p className="text-xs font-semibold text-indigo-700 uppercase tracking-wide">
          🇨🇱 Perfil inmigrante / Hispanohablante
        </p>
        <div className="space-y-2">
          <label className="flex items-start gap-3 cursor-pointer group">
            <input
              type="checkbox"
              className="mt-0.5 accent-indigo-600"
              checked={params.lmia_only}
              onChange={(e) => set("lmia_only", e.target.checked)}
            />
            <div>
              <p className="text-sm font-medium text-gray-700 group-hover:text-indigo-700">
                Solo empleos con LMIA aprobado
              </p>
              <p className="text-xs text-gray-400">
                El empleador ya tiene permiso oficial para contratar trabajadores extranjeros
              </p>
            </div>
          </label>
          <label className="flex items-start gap-3 cursor-pointer group">
            <input
              type="checkbox"
              className="mt-0.5 accent-indigo-600"
              checked={params.bilingual_spanish}
              onChange={(e) => set("bilingual_spanish", e.target.checked)}
            />
            <div>
              <p className="text-sm font-medium text-gray-700 group-hover:text-indigo-700">
                Priorizar empleos bilingüe / Español
              </p>
              <p className="text-xs text-gray-400">
                Busca roles donde el español sea una ventaja competitiva
              </p>
            </div>
          </label>
          <label className="flex items-start gap-3 cursor-pointer group">
            <input
              type="checkbox"
              className="mt-0.5 accent-indigo-600"
              checked={params.ccfta_check}
              onChange={(e) => set("ccfta_check", e.target.checked)}
            />
            <div>
              <p className="text-sm font-medium text-gray-700 group-hover:text-indigo-700">
                Evaluar elegibilidad CCFTA
              </p>
              <p className="text-xs text-gray-400">
                Tratado Chile-Canadá: ciertos roles no requieren LMIA para ciudadanos chilenos
              </p>
            </div>
          </label>
        </div>

        <p className="text-[11px] text-indigo-400 pt-1">
          💡 El nivel de inglés se configura en tu perfil de resume maestro.
        </p>
      </div>

      {/* ── Model selector ────────────────────────────────────────────────── */}
      <div>
        <label className="label">Modelo de IA para análisis</label>
        <div className="flex flex-wrap gap-2">
          {LLM_OPTIONS.map((opt, i) => (
            <button
              key={i}
              onClick={() => handleLLMChange(i)}
              className={`px-3 py-1.5 rounded-lg border text-xs transition-all ${
                selectedLLM === i
                  ? "border-indigo-500 bg-indigo-50 text-indigo-700 font-medium"
                  : "border-gray-200 text-gray-500 hover:border-gray-300"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Num results ───────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <label className="label mb-0">Número de ofertas</label>
        <div className="flex gap-1.5">
          {[8, 12, 20, 30].map((n) => (
            <button
              key={n}
              onClick={() => set("num_results", n)}
              className={`w-10 py-1 rounded-lg border text-xs font-medium transition-all ${
                params.num_results === n
                  ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                  : "border-gray-200 text-gray-500 hover:border-gray-300"
              }`}
            >
              {n}
            </button>
          ))}
        </div>
      </div>

      {/* ── Submit ────────────────────────────────────────────────────────── */}
      <button
        className="btn-primary w-full py-3 text-base"
        onClick={handleSubmit}
        disabled={loading || (!params.job_title.trim() && !params.custom_query.trim())}
      >
        {loading ? "Buscando y analizando ofertas…" : "🔍 Buscar empleos"}
      </button>

      {/* ── Manual fallback links ─────────────────────────────────────────── */}
      <div>
        <p className="text-[11px] text-gray-400 uppercase tracking-wide font-medium mb-2">
          También buscar directamente en:
        </p>
        <div className="flex flex-wrap gap-2">
          {buildExternalUrls().map((board) => (
            <a
              key={board.id}
              href={board.url}
              target="_blank"
              rel="noopener noreferrer"
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200
                         text-xs text-gray-500 bg-white font-medium transition-all ${board.color}`}
              title={`Buscar en ${board.label} con tus parámetros actuales`}
            >
              <span>{board.icon}</span>
              {board.label}
              <span className="opacity-50">↗</span>
            </a>
          ))}
        </div>
        <p className="text-[10px] text-gray-400 mt-1.5">
          Abre el portal con tu búsqueda actual — útil cuando el scraping no devuelve resultados de esa fuente.
        </p>
      </div>
    </div>
  );
}
