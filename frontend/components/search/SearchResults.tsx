"use client";
import { useState } from "react";
import {
  extractJobFromUrl,
  createAdaptation,
  toggleApplied,
  saveJob,
  unsaveJob,
  type JobResult,
  type Adaptation,
} from "@/lib/api";

interface Props {
  results: JobResult[];
  queriesUsed: string[];
  llmProvider: string;
  llmModel: string;
  onAdapted: (adaptation: Adaptation) => void;
  // job_url → adaptation for jobs already adapted this session
  adaptedJobs?: Record<string, Adaptation>;
  onJobAdapted?: (jobUrl: string, adaptation: Adaptation) => void;
  // url → saved_job_id for jobs already saved
  savedUrls?: Record<string, string>;
  onSavedChange?: (url: string, savedId: string | null) => void;
}

export function SearchResults({
  results,
  queriesUsed,
  llmProvider,
  llmModel,
  onAdapted,
  adaptedJobs = {},
  onJobAdapted,
  savedUrls = {},
  onSavedChange,
}: Props) {
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
          existingAdaptation={adaptedJobs[job.url] ?? null}
          onJobAdapted={onJobAdapted}
          savedId={savedUrls[job.url] ?? null}
          onSavedChange={onSavedChange}
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
  existingAdaptation: Adaptation | null;
  onJobAdapted?: (jobUrl: string, adaptation: Adaptation) => void;
  savedId: string | null;
  onSavedChange?: (url: string, savedId: string | null) => void;
}

function JobResultCard({
  job,
  llmProvider,
  llmModel,
  onAdapted,
  existingAdaptation,
  onJobAdapted,
  savedId: initialSavedId,
  onSavedChange,
}: CardProps) {
  const [expanded, setExpanded] = useState(false);
  const [adapting, setAdapting] = useState(false);
  const [error, setError] = useState("");
  const [adaptation, setAdaptation] = useState<Adaptation | null>(existingAdaptation);
  const [applied, setApplied] = useState<boolean>(!!existingAdaptation?.applied_at);
  const [togglingApplied, setTogglingApplied] = useState(false);
  // Instructions panel — closed until user clicks "Adaptar →"
  const [showInstructions, setShowInstructions] = useState(false);
  const [instructions, setInstructions] = useState("");
  // Two-step adapt: first click opens panel, second click (Confirmar) runs it
  const [awaitingConfirm, setAwaitingConfirm] = useState(false);
  // Saved state
  const [savedId, setSavedId] = useState<string | null>(initialSavedId);
  const [saving, setSaving] = useState(false);

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

      // Step 2: create adaptation (store job_url for tracking)
      const newAdaptation = await createAdaptation({
        job_description: jobDescription,
        llm_provider: llmProvider,
        llm_model: llmModel,
        job_url: job.url,
        user_instructions: instructions.trim() || undefined,
      });
      setAdaptation(newAdaptation);
      setApplied(false); // new adaptation resets applied status
      onJobAdapted?.(job.url, newAdaptation);
      onAdapted(newAdaptation);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      setError(err?.response?.data?.detail || err?.message || "Error al iniciar la adaptación.");
      setAdapting(false);
    }
  };

  const handleToggleSave = async () => {
    setSaving(true);
    try {
      if (savedId) {
        await unsaveJob(savedId);
        setSavedId(null);
        onSavedChange?.(job.url, null);
      } else {
        const saved = await saveJob(job);
        setSavedId(saved.id);
        onSavedChange?.(job.url, saved.id);
      }
    } catch {
      // ignore
    } finally {
      setSaving(false);
    }
  };

  const handleToggleApplied = async () => {
    if (!adaptation) return;
    setTogglingApplied(true);
    try {
      const updated = await toggleApplied(adaptation.id);
      setApplied(!!updated.applied_at);
      setAdaptation(updated);
    } catch {
      // ignore
    } finally {
      setTogglingApplied(false);
    }
  };

  return (
    <div className={`border rounded-xl p-4 transition-all ${
      applied
        ? "border-green-300 bg-green-50/30"
        : adaptation
        ? "border-indigo-200 bg-indigo-50/20"
        : (job.cptpp_eligible || job.ccfta_eligible)
        ? "border-emerald-300 bg-emerald-50/20 ring-1 ring-emerald-200"
        : "border-gray-200 hover:border-gray-300"
    }`}>
      {/* Visa-eligibility banner — most relevant signal for the candidate */}
      {(job.cptpp_eligible || job.ccfta_eligible) && (
        <div className="flex items-center gap-2 mb-2 -mt-1">
          <span className="text-[10px] font-bold uppercase tracking-wide text-emerald-700">
            ✅ Apto para visa de tratado
          </span>
          {job.cptpp_eligible && (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-300 font-bold">
              🌏 CPTPP
            </span>
          )}
          {job.ccfta_eligible && (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 border border-blue-300 font-bold">
              🇨🇱 CCFTA
            </span>
          )}
        </div>
      )}
      <div className="flex items-start gap-3">
        {/* Score badge */}
        <div className="flex-shrink-0 flex flex-col items-center gap-1">
          <div className={`w-14 h-14 rounded-xl border-2 flex flex-col items-center justify-center ${scoreColor}`}>
            <span className="text-lg font-bold leading-none">{score}</span>
            <span className="text-[9px] leading-none mt-0.5">%</span>
          </div>
          {/* Confidence indicator under score */}
          <span className={`text-[9px] font-medium px-1 rounded ${
            job.confidence === "high"   ? "text-green-600" :
            job.confidence === "medium" ? "text-amber-500" :
                                          "text-gray-400"
          }`}>
            {job.confidence === "high" ? "● alta conf." :
             job.confidence === "medium" ? "● media conf." :
                                           "○ baja conf."}
          </span>
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
            <div className="flex-shrink-0 flex gap-2 flex-wrap justify-end">
              {/* Bookmark button */}
              <button
                onClick={handleToggleSave}
                disabled={saving}
                title={savedId ? "Quitar de guardados" : "Guardar oferta"}
                className={`text-xs py-1 px-2 rounded-lg border font-medium transition-colors ${
                  savedId
                    ? "bg-amber-100 text-amber-700 border-amber-300 hover:bg-amber-200"
                    : "btn-secondary hover:border-amber-300 hover:text-amber-600"
                }`}
              >
                {saving ? "…" : savedId ? "🔖 Guardado" : "🔖"}
              </button>

              <a
                href={job.url}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-secondary text-xs py-1 px-2"
              >
                Ver ↗
              </a>

              {adaptation ? (
                <>
                  {/* View the generated resume */}
                  <button
                    className="btn-secondary text-xs py-1 px-2 border-indigo-300 text-indigo-600 hover:bg-indigo-50"
                    onClick={() => onAdapted(adaptation)}
                    title="Ver el resume generado para esta oferta"
                  >
                    📄 Ver resume
                  </button>

                  {/* Instructions toggle for re-adaptation */}
                  <button
                    className={`text-xs py-1 px-2 rounded-lg border font-medium transition-colors ${
                      showInstructions
                        ? "bg-amber-100 text-amber-700 border-amber-300"
                        : "btn-secondary"
                    }`}
                    onClick={() => { setShowInstructions(!showInstructions); setAwaitingConfirm(false); }}
                    title="Agregar instrucciones antes de re-adaptar"
                  >
                    {showInstructions ? "📝 Ocultar" : "📝 + Instrucciones"}
                  </button>

                  {/* Re-adapt */}
                  <button
                    className="btn-secondary text-xs py-1 px-2"
                    onClick={handleAdapt}
                    disabled={adapting}
                    title="Generar un nuevo resume adaptado"
                  >
                    {adapting ? "…" : "↻ Re-adaptar"}
                  </button>

                  {/* Mark as applied toggle */}
                  <button
                    className={`text-xs py-1 px-2 rounded-lg font-medium transition-colors ${
                      applied
                        ? "bg-green-100 text-green-700 border border-green-300 hover:bg-green-200"
                        : "bg-indigo-100 text-indigo-700 border border-indigo-300 hover:bg-indigo-200"
                    }`}
                    onClick={handleToggleApplied}
                    disabled={togglingApplied}
                  >
                    {togglingApplied ? "…" : applied ? "✓ Postulé" : "Marcar postulado"}
                  </button>
                </>
              ) : (
                <div className="flex gap-2">
                  <button
                    className="btn-primary text-xs py-1 px-2"
                    onClick={() => { setShowInstructions(true); setAwaitingConfirm(true); }}
                    disabled={adapting || awaitingConfirm}
                  >
                    Adaptar →
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Instructions panel — shown when user clicks Adaptar → */}
          {showInstructions && (
            <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-2.5">
              <p className="text-[11px] font-medium text-amber-700 mb-1.5">
                📝 Instrucciones para la adaptación{" "}
                <span className="font-normal text-amber-500">(opcional)</span>
              </p>
              <textarea
                autoFocus
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
                placeholder={
                  "Pega aquí el análisis de tu agente IA, cambios específicos que quieres, " +
                  "o cualquier nota para guiar la adaptación del resume.\n\n" +
                  "Ej: «Enfatiza más la experiencia de configuración en Entel. " +
                  "El summary debe mencionar implementación de software. " +
                  "Evita resaltar habilidades de testing puro.»"
                }
                rows={5}
                className="w-full text-xs font-mono rounded border border-amber-300 bg-white
                           p-2 resize-y focus:outline-none focus:border-amber-500
                           placeholder:text-gray-400 placeholder:font-sans"
              />
              {/* Only show confirm buttons on first-time adapt (not re-adapt toggle) */}
              {awaitingConfirm && (
                <div className="flex items-center gap-2 mt-2">
                  <button
                    className="btn-primary text-xs py-1.5 px-3"
                    onClick={() => { setAwaitingConfirm(false); setShowInstructions(false); handleAdapt(); }}
                    disabled={adapting}
                  >
                    {adapting ? "Adaptando…" : "✓ Confirmar y adaptar"}
                  </button>
                  <button
                    className="text-xs text-gray-400 hover:text-gray-600 underline underline-offset-2"
                    onClick={() => { setInstructions(""); setAwaitingConfirm(false); setShowInstructions(false); handleAdapt(); }}
                    disabled={adapting}
                  >
                    Saltar instrucciones
                  </button>
                  <button
                    className="text-xs text-gray-400 hover:text-gray-600 ml-auto"
                    onClick={() => { setAwaitingConfirm(false); setShowInstructions(false); }}
                  >
                    ✕ Cancelar
                  </button>
                </div>
              )}
              {!awaitingConfirm && (
                <p className="text-[10px] text-amber-600 mt-1">
                  El LLM usará esto como guía prioritaria al reescribir las secciones de tu resume.
                </p>
              )}
            </div>
          )}

          {/* Confidence + blockers + why_relevant — structured assessment */}
          {(job.blockers?.length > 0 || job.why_relevant?.length > 0) && (
            <div className="mt-2 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 space-y-1.5">
              {/* Confidence indicator */}
              {job.confidence === "low" && (
                <p className="text-[10px] text-amber-600 font-medium">
                  ⚠️ Confianza baja — solo título disponible, sin descripción completa
                </p>
              )}
              {/* Blockers */}
              {job.blockers?.length > 0 && (
                <div>
                  <p className="text-[10px] font-semibold text-red-600 uppercase tracking-wide mb-0.5">
                    🚫 Brechas principales
                  </p>
                  <ul className="space-y-0.5">
                    {job.blockers.map((b, i) => (
                      <li key={i} className="text-[11px] text-red-700 flex gap-1">
                        <span className="opacity-50">•</span>{b}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {/* Why relevant */}
              {job.why_relevant?.length > 0 && (
                <div>
                  <p className="text-[10px] font-semibold text-green-700 uppercase tracking-wide mb-0.5">
                    ✅ Por qué aplica
                  </p>
                  <ul className="space-y-0.5">
                    {job.why_relevant.map((w, i) => (
                      <li key={i} className="text-[11px] text-green-800 flex gap-1">
                        <span className="opacity-50">•</span>{w}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Score label + salary + badges */}
          <div className="flex flex-wrap items-center gap-2 mt-1.5">
            <span className={`text-[10px] px-2 py-0.5 rounded-full border ${scoreColor}`}>
              {scoreLabel}
            </span>
            {job.salary && (
              <span className="text-xs text-gray-500">💰 {job.salary}</span>
            )}
            {job.date_posted && (
              <span className="text-xs text-gray-400">{job.date_posted}</span>
            )}
            {/* Applied badge */}
            {applied && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-100 text-green-700 border border-green-300 font-medium">
                ✅ Postulado
              </span>
            )}
            {adaptation && !applied && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700 border border-indigo-300 font-medium">
                📄 Resume listo
              </span>
            )}
            {/* Source badge */}
            {job.source === "jobbank" && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-50 text-red-600 border border-red-200 font-medium">
                🍁 Job Bank
              </span>
            )}
            {job.source === "workopolis" && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-orange-50 text-orange-600 border border-orange-200 font-medium">
                🇨🇦 Workopolis
              </span>
            )}
            {job.source === "eluta" && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-teal-50 text-teal-600 border border-teal-200 font-medium">
                🔍 Eluta
              </span>
            )}
            {/* Immigration badges */}
            {job.lmia_approved && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 font-medium">
                ✅ LMIA
              </span>
            )}
            {/* CCFTA/CPTPP shown in the top visa banner — not repeated here */}
            {job.immigration_support === "yes" && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-200 font-medium">
                ✈️ Apoya migración
              </span>
            )}
            {job.bilingual_advantage && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200 font-medium">
                🗣️ Bilingüe+
              </span>
            )}
            {/* English barrier warning */}
            {job.english_barrier && (
              <span
                className="text-[10px] px-1.5 py-0.5 rounded bg-orange-50 text-orange-700 border border-orange-200 font-medium"
                title={`Este puesto requiere inglés ${job.english_required ?? "avanzado"}`}
              >
                🇬🇧 Inglés {job.english_required ?? "avanzado"} requerido
              </span>
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
