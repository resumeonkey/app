"use client";
import { useState } from "react";
import { createAdaptation, extractJobFromUrl, type Adaptation } from "@/lib/api";

const LLM_OPTIONS = [
  { provider: "anthropic", model: "claude-haiku-4-5",        label: "Claude Haiku · Anthropic", tag: "" },
  { provider: "groq",      model: "llama-3.3-70b-versatile", label: "Llama 3.3 70B · Groq",     tag: "gratis" },
  { provider: "gemini",    model: "gemini-2.0-flash",        label: "Gemini 2.0 Flash · Google", tag: "gratis" },
  { provider: "openai",    model: "gpt-4o-mini",             label: "GPT-4o Mini · OpenAI",      tag: "créditos" },
  { provider: "openai",    model: "gpt-4o",                  label: "GPT-4o · OpenAI",           tag: "créditos" },
];

type Tab = "text" | "url";

interface Props {
  onCreated: (adaptation: Adaptation) => void;
}

export function JobForm({ onCreated }: Props) {
  const [tab, setTab]                   = useState<Tab>("text");

  // Text tab
  const [jobDesc, setJobDesc]           = useState("");
  const [instructions, setInstructions] = useState("");

  // URL tab
  const [url, setUrl]                   = useState("");
  const [extracted, setExtracted]       = useState<{ text: string; score?: number; title?: string } | null>(null);
  const [extracting, setExtracting]     = useState(false);
  const [extractError, setExtractError] = useState("");

  const [selectedLLM, setSelectedLLM]   = useState(0);
  const [loading, setLoading]           = useState(false);
  const [error, setError]               = useState("");

  const llm = LLM_OPTIONS[selectedLLM];

  // ── URL extraction ─────────────────────────────────────────────────────────
  const handleExtract = async () => {
    if (!url.trim()) return;
    setExtractError("");
    setExtracted(null);
    setExtracting(true);
    try {
      const data = await extractJobFromUrl(url.trim(), llm.provider, llm.model);
      setExtracted({
        text:  data.job_description,
        score: data.compatibility_score,
        title: data.job_title,
      });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      setExtractError(err?.response?.data?.detail || err?.message || "No se pudo extraer la oferta.");
    } finally {
      setExtracting(false);
    }
  };

  // ── Submit ─────────────────────────────────────────────────────────────────
  const handleSubmit = async () => {
    const desc = tab === "url" ? extracted?.text : jobDesc;
    if (!desc?.trim()) {
      setError(tab === "url" ? "Primero extrae la oferta desde la URL." : "Pega la descripción del trabajo.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const adaptation = await createAdaptation({
        job_description:   desc,
        user_instructions: instructions || undefined,
        llm_provider:      llm.provider,
        llm_model:         llm.model,
      });
      onCreated(adaptation);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      setError(err?.response?.data?.detail || err?.message || "Error al crear la adaptación.");
    } finally {
      setLoading(false);
    }
  };

  const isReady = tab === "text" ? !!jobDesc.trim() : !!extracted?.text;

  return (
    <div className="space-y-5">
      {/* ── Tab switcher ──────────────────────────────────────────────────── */}
      <div className="flex gap-1 p-1 bg-gray-100 rounded-xl w-fit">
        <button
          onClick={() => setTab("text")}
          className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
            tab === "text" ? "bg-white shadow-sm text-gray-800" : "text-gray-500 hover:text-gray-700"
          }`}
        >
          📄 Pegar texto
        </button>
        <button
          onClick={() => setTab("url")}
          className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
            tab === "url" ? "bg-white shadow-sm text-gray-800" : "text-gray-500 hover:text-gray-700"
          }`}
        >
          🔗 Desde URL
        </button>
      </div>

      {/* ── Text tab ──────────────────────────────────────────────────────── */}
      {tab === "text" && (
        <div>
          <label className="label">Descripción del trabajo (pega el job posting completo)</label>
          <textarea
            className="textarea h-52 font-mono text-xs"
            placeholder="Pega aquí el texto completo del job description…"
            value={jobDesc}
            onChange={(e) => setJobDesc(e.target.value)}
          />
          {jobDesc && (
            <p className="text-xs text-gray-400 mt-1">{jobDesc.length} caracteres</p>
          )}
        </div>
      )}

      {/* ── URL tab ───────────────────────────────────────────────────────── */}
      {tab === "url" && (
        <div className="space-y-3">
          <div>
            <label className="label">URL de la oferta</label>
            <div className="flex gap-2">
              <input
                className="input flex-1"
                placeholder="https://www.linkedin.com/jobs/view/… o cualquier job posting"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleExtract()}
              />
              <button
                className="btn-secondary px-4"
                onClick={handleExtract}
                disabled={extracting || !url.trim()}
              >
                {extracting ? "Extrayendo…" : "Extraer"}
              </button>
            </div>
          </div>

          {extractError && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2">
              ⚠️ {extractError}
            </p>
          )}

          {extracted && (
            <div className="border border-green-200 rounded-xl p-4 bg-green-50 space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-green-700">✅ Oferta extraída</p>
                {extracted.score !== undefined && (
                  <span className={`badge text-xs ${
                    extracted.score >= 80 ? "bg-green-200 text-green-800" :
                    extracted.score >= 60 ? "bg-yellow-200 text-yellow-800" :
                                            "bg-red-200 text-red-800"
                  }`}>
                    {extracted.score}% compatibilidad
                  </span>
                )}
              </div>
              {extracted.title && (
                <p className="text-xs text-green-800 font-medium">{extracted.title}</p>
              )}
              <p className="text-xs text-green-700">{extracted.text.length} caracteres extraídos</p>
              <button
                className="text-xs text-green-600 hover:text-green-800 underline"
                onClick={() => { setTab("text"); setJobDesc(extracted.text); }}
              >
                Ver / editar texto completo →
              </button>
            </div>
          )}
        </div>
      )}

      {/* ── Instructions ──────────────────────────────────────────────────── */}
      <div>
        <label className="label">Instrucciones adicionales (opcional)</label>
        <textarea
          className="textarea h-20"
          placeholder="Ej: Enfatizar experiencia en liderazgo. Empresa de fintech. No cambiar más de 2 secciones."
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
        />
      </div>

      {/* ── LLM selector ──────────────────────────────────────────────────── */}
      <div>
        <label className="label">Modelo de IA</label>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {LLM_OPTIONS.map((opt, i) => (
            <button
              key={i}
              onClick={() => setSelectedLLM(i)}
              className={`rounded-xl border-2 p-3 text-left transition-all text-sm
                ${selectedLLM === i
                  ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                  : "border-gray-200 hover:border-gray-300 text-gray-600"
                }`}
            >
              <div className="flex items-center justify-between gap-1">
                <span className="font-medium truncate">{opt.label}</span>
                {opt.tag && (
                  <span className={`text-xs px-1.5 py-0.5 rounded-full flex-shrink-0 ${
                    opt.tag === "gratis"
                      ? "bg-green-100 text-green-700"
                      : "bg-orange-100 text-orange-700"
                  }`}>{opt.tag}</span>
                )}
              </div>
              <div className="text-xs text-gray-400 mt-0.5">{opt.model}</div>
            </button>
          ))}
        </div>
      </div>

      {error && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2">⚠️ {error}</p>
      )}

      <button
        className="btn-primary w-full py-3 text-base"
        onClick={handleSubmit}
        disabled={loading || !isReady}
      >
        {loading ? "Analizando oferta y adaptando resume…" : "🚀 Adaptar resume a esta oferta"}
      </button>
    </div>
  );
}
