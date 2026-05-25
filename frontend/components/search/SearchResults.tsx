"use client";
import { useState } from "react";
import { extractJobFromUrl, createAdaptation, type JobResult, type Adaptation } from "@/lib/api";

interface Props {
  results: JobResult[];
  queriesUsed: string[];
  llmProvider: string;
  llmModel: string;
  onAdapted: (adaptation: Adaptation) => void;
}

export function SearchResults({ results, queriesUsed, llmProvider, llmModel, onAdapted }: Props) {
  return (
    <div className="space-y-4">
      {/* Meta */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">
          {results.length} oferta{results.length !== 1 ? "s" : ""} encontrada{results.length !== 1 ? "s" : ""}
        </p>
        <details className="text-xs text-gray-400 cursor-pointer">
          <summary className="hover:text-gray-600">Consultas usadas</summary>
          <ul className="mt-1 space-y-0.5 text-left bg-gray-50 rounded p-2">
            {queriesUsed.map((q, i) => (
              <li key={i} className="font-mono">{q}</li>
            ))}
          </ul>
        </details>
      </div>

      {/* Result cards */}
      {results.map((job) => (
        <JobResultCard
          key={job.id}
          job={job}
          llmProvider={llmProvider}
          llmModel={llmModel}
          onAdapted={onAdapted}
        />
      ))}

      {results.length === 0 && (
        <div className="text-center py-10 text-gray-400">
          <p className="text-2xl mb-2">🔍</p>
          <p>No se encontraron ofertas. Prueba con otros parámetros.</p>
        </div>
      )}
    </div>
  );
}


interface CardProps {
  job: JobResult;
  llmProvider: string;
  llmModel: string;
  onAdapted: (a: Adaptation) => void;
}

function JobResultCard({ job, llmProvider, llmModel, onAdapted }: CardProps) {
  const [expanded, setExpanded] = useState(false);
  const [adapting, setAdapting] = useState(false);
  const [error, setError] = useState("");

  const score = job.compatibility_score;
  const scoreColor =
    score >= 80 ? "text-green-600 bg-green-50 border-green-200" :
    score >= 60 ? "text-yellow-600 bg-yellow-50 border-yellow-200" :
                  "text-red-600 bg-red-50 border-red-200";

  const scoreLabel =
    score >= 80 ? "Alta compatibilidad" :
    score >= 60 ? "Compatibilidad media" :
                  "Baja compatibilidad";

  const handleAdapt = async () => {
    setAdapting(true);
    setError("");
    try {
      // Step 1: extract full job description
      let jobDescription = job.snippet;
      try {
        const extracted = await extractJobFromUrl(job.url, llmProvider, llmModel);
        if (extracted.job_description.length > jobDescription.length) {
          jobDescription = extracted.job_description;
        }
      } catch {
        // Use snippet as fallback
      }

      // Step 2: create adaptation
      const adaptation = await createAdaptation({
        job_description: jobDescription,
        llm_provider: llmProvider,
        llm_model: llmModel,
      });
      onAdapted(adaptation);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      setError(err?.response?.data?.detail || err?.message || "Error al iniciar la adaptación.");
      setAdapting(false);
    }
  };

  return (
    <div className="border border-gray-200 rounded-xl p-4 hover:border-gray-300 transition-all">
      <div className="flex items-start gap-3">
        {/* Score badge */}
        <div className={`flex-shrink-0 w-14 h-14 rounded-xl border-2 flex flex-col items-center justify-center ${scoreColor}`}>
          <span className="text-lg font-bold leading-none">{score}</span>
          <span className="text-[9px] leading-none mt-0.5">%</span>
        </div>

        {/* Main content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h3 className="font-semibold text-gray-800 text-sm leading-tight">
                {job.title || "Puesto sin título"}
              </h3>
              <p className="text-xs text-gray-500 mt-0.5">
                {[job.company, job.location].filter(Boolean).join(" · ") || "Empresa no especificada"}
              </p>
            </div>
            <div className="flex-shrink-0 flex gap-2">
              <a
                href={job.url}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-secondary text-xs py-1 px-2"
              >
                Ver ↗
              </a>
              <button
                className="btn-primary text-xs py-1 px-2"
                onClick={handleAdapt}
                disabled={adapting}
              >
                {adapting ? "…" : "Adaptar →"}
              </button>
            </div>
          </div>

          {/* Score label + salary */}
          <div className="flex items-center gap-3 mt-1.5">
            <span className={`text-[10px] px-2 py-0.5 rounded-full border ${scoreColor}`}>
              {scoreLabel}
            </span>
            {job.salary && (
              <span className="text-xs text-gray-500">💰 {job.salary}</span>
            )}
            {job.date_posted && (
              <span className="text-xs text-gray-400">{job.date_posted}</span>
            )}
          </div>

          {/* Score summary */}
          {job.score_summary && (
            <p className="text-xs text-gray-500 mt-1.5 italic">{job.score_summary}</p>
          )}

          {/* Skills + snippet (expand) */}
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-indigo-500 hover:text-indigo-700 mt-1"
          >
            {expanded ? "▲ Menos detalles" : "▼ Ver detalles"}
          </button>

          {expanded && (
            <div className="mt-2 space-y-2">
              {job.matched_skills.length > 0 && (
                <div>
                  <p className="text-[10px] font-medium text-gray-500 uppercase tracking-wide mb-1">Skills coincidentes</p>
                  <div className="flex flex-wrap gap-1">
                    {job.matched_skills.map((s) => (
                      <span key={s} className="badge bg-green-100 text-green-700">{s}</span>
                    ))}
                  </div>
                </div>
              )}
              {job.missing_skills.length > 0 && (
                <div>
                  <p className="text-[10px] font-medium text-gray-500 uppercase tracking-wide mb-1">Skills faltantes</p>
                  <div className="flex flex-wrap gap-1">
                    {job.missing_skills.map((s) => (
                      <span key={s} className="badge bg-red-100 text-red-700">{s}</span>
                    ))}
                  </div>
                </div>
              )}
              {job.snippet && (
                <div>
                  <p className="text-[10px] font-medium text-gray-500 uppercase tracking-wide mb-1">Descripción</p>
                  <p className="text-xs text-gray-600 leading-relaxed">{job.snippet}</p>
                </div>
              )}
            </div>
          )}

          {error && (
            <p className="text-xs text-red-600 mt-1">⚠️ {error}</p>
          )}
        </div>
      </div>
    </div>
  );
}
