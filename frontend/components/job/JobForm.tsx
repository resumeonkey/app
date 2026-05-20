"use client";
import { useState } from "react";
import { createAdaptation, type Adaptation } from "@/lib/api";

const LLM_OPTIONS = [
  { provider: "openai", model: "gpt-4o",       label: "GPT-4o (mejor calidad)" },
  { provider: "openai", model: "gpt-4o-mini",  label: "GPT-4o Mini (más rápido)" },
  { provider: "groq",   model: "llama3-70b-8192", label: "Llama 3 70B via Groq (gratuito)" },
];

interface Props {
  onCreated: (adaptation: Adaptation) => void;
}

export function JobForm({ onCreated }: Props) {
  const [jobDesc, setJobDesc]         = useState("");
  const [instructions, setInstructions] = useState("");
  const [selectedLLM, setSelectedLLM] = useState(0);
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState("");

  const handleSubmit = async () => {
    if (!jobDesc.trim()) { setError("Pega la descripción del trabajo."); return; }
    setError("");
    setLoading(true);
    try {
      const llm = LLM_OPTIONS[selectedLLM];
      const adaptation = await createAdaptation({
        job_description: jobDesc,
        user_instructions: instructions || undefined,
        llm_provider: llm.provider,
        llm_model: llm.model,
      });
      onCreated(adaptation);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      setError(err?.response?.data?.detail || err?.message || "Error al crear la adaptación.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <label className="label">Descripción del trabajo (pega el job posting completo)</label>
        <textarea
          className="textarea h-52 font-mono text-xs"
          placeholder="Pega aquí el texto completo del job description..."
          value={jobDesc}
          onChange={(e) => setJobDesc(e.target.value)}
        />
        {jobDesc && (
          <p className="text-xs text-gray-400 mt-1">{jobDesc.length} caracteres</p>
        )}
      </div>

      <div>
        <label className="label">Instrucciones adicionales (opcional)</label>
        <textarea
          className="textarea h-20"
          placeholder="Ej: Enfatizar experiencia en liderazgo. Empresa de fintech. No cambiar más de 2 secciones."
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
        />
      </div>

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
              <div className="font-medium">{opt.model}</div>
              <div className="text-xs text-gray-400 mt-0.5">{opt.label}</div>
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
        disabled={loading || !jobDesc.trim()}
      >
        {loading ? "Analizando oferta y adaptando resume..." : "🚀 Adaptar resume a esta oferta"}
      </button>
    </div>
  );
}
