"use client";
import { useState, useEffect } from "react";
import { suggestSearchParams, type SearchParams } from "@/lib/api";

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
};

interface Props {
  onSearch: (params: SearchParams) => void;
  loading: boolean;
}

export function SearchPanel({ onSearch, loading }: Props) {
  const [params, setParams] = useState<SearchParams>(DEFAULT_PARAMS);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [kwInput, setKwInput] = useState("");
  const [exKwInput, setExKwInput] = useState("");
  const [selectedLLM, setSelectedLLM] = useState(0);
  const [suggesting, setSuggesting] = useState(false);

  // Auto-fill from master profile on mount
  useEffect(() => {
    setSuggesting(true);
    const llm = LLM_OPTIONS[0];
    suggestSearchParams(llm.provider, llm.model)
      .then(({ suggestions }) => {
        if (suggestions.job_title) {
          setParams((p) => ({
            ...p,
            job_title:        suggestions.job_title || p.job_title,
            experience_level: suggestions.experience_level || p.experience_level,
            industries:       suggestions.industries || p.industries,
          }));
        }
      })
      .catch(() => {})
      .finally(() => setSuggesting(false));
  }, []);

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
      {/* ── Job title ─────────────────────────────────────────────────────── */}
      <div>
        <label className="label">
          Puesto que buscas {suggesting && <span className="text-indigo-400 text-xs ml-1">autocompletando…</span>}
        </label>
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

      {/* ── Submit ────────────────────────────────────────────────────────── */}
      <button
        className="btn-primary w-full py-3 text-base"
        onClick={handleSubmit}
        disabled={loading || (!params.job_title.trim() && !params.custom_query.trim())}
      >
        {loading ? "Buscando y analizando ofertas…" : "🔍 Buscar empleos"}
      </button>
    </div>
  );
}
