"use client";
import { useEffect, useState } from "react";
import {
  listSavedJobs,
  unsaveJob,
  patchSavedJob,
  type SavedJob,
} from "@/lib/api";

export default function SavedJobsPage() {
  const [jobs, setJobs] = useState<SavedJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "applied" | "pending">("all");

  useEffect(() => {
    listSavedJobs()
      .then((data) => setJobs(data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleUnsave = async (id: string) => {
    await unsaveJob(id);
    setJobs((prev) => prev.filter((j) => j.id !== id));
  };

  const handleToggleApplied = async (job: SavedJob) => {
    const updated = await patchSavedJob(job.id, { applied: !job.applied_at });
    setJobs((prev) => prev.map((j) => (j.id === updated.id ? updated : j)));
  };

  const filtered = jobs.filter((j) => {
    if (filter === "applied") return !!j.applied_at;
    if (filter === "pending") return !j.applied_at;
    return true;
  });

  const appliedCount = jobs.filter((j) => !!j.applied_at).length;
  const pendingCount = jobs.filter((j) => !j.applied_at).length;

  return (
    <main className="max-w-3xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">🔖 Ofertas guardadas</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {jobs.length} guardada{jobs.length !== 1 ? "s" : ""} · {appliedCount} postulada{appliedCount !== 1 ? "s" : ""}
          </p>
        </div>
        <a href="/" className="btn-secondary text-sm py-1.5 px-3">
          ← Volver
        </a>
      </div>

      {/* Filter tabs */}
      {jobs.length > 0 && (
        <div className="flex gap-2 mb-4">
          {(["all", "pending", "applied"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`text-sm px-3 py-1.5 rounded-lg border font-medium transition-colors ${
                filter === f
                  ? "bg-indigo-100 text-indigo-700 border-indigo-300"
                  : "bg-white text-gray-500 border-gray-200 hover:border-gray-300"
              }`}
            >
              {f === "all" ? `Todas (${jobs.length})` :
               f === "pending" ? `Por postular (${pendingCount})` :
               `Postuladas (${appliedCount})`}
            </button>
          ))}
        </div>
      )}

      {/* Content */}
      {loading ? (
        <div className="text-center py-16 text-gray-400">
          <p className="text-3xl mb-2 animate-pulse">🔖</p>
          <p>Cargando ofertas guardadas…</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <p className="text-3xl mb-3">🔖</p>
          <p className="font-medium text-gray-500">
            {jobs.length === 0
              ? "No hay ofertas guardadas aún"
              : "No hay ofertas en este filtro"}
          </p>
          {jobs.length === 0 && (
            <p className="text-sm mt-1">
              Usa el botón <span className="font-mono bg-gray-100 px-1 rounded">🔖</span> en los resultados de búsqueda para guardar ofertas.
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((job) => (
            <SavedJobCard
              key={job.id}
              job={job}
              onUnsave={handleUnsave}
              onToggleApplied={handleToggleApplied}
            />
          ))}
        </div>
      )}
    </main>
  );
}


function SavedJobCard({
  job,
  onUnsave,
  onToggleApplied,
}: {
  job: SavedJob;
  onUnsave: (id: string) => void;
  onToggleApplied: (job: SavedJob) => void;
}) {
  const [togglingApplied, setTogglingApplied] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const score = job.compatibility_score;
  const scoreColor =
    score == null        ? "text-gray-500 bg-gray-50 border-gray-200" :
    score >= 80          ? "text-green-600 bg-green-50 border-green-200" :
    score >= 60          ? "text-yellow-600 bg-yellow-50 border-yellow-200" :
                           "text-red-600 bg-red-50 border-red-200";

  const savedDate = new Date(job.created_at).toLocaleDateString("es-CA", {
    day: "numeric", month: "short",
  });

  return (
    <div className={`border rounded-xl p-4 transition-all ${
      job.applied_at
        ? "border-green-300 bg-green-50/30"
        : "border-gray-200 hover:border-gray-300 bg-white"
    }`}>
      <div className="flex items-start gap-3">
        {/* Score badge */}
        <div className="flex-shrink-0">
          <div className={`w-14 h-14 rounded-xl border-2 flex flex-col items-center justify-center ${scoreColor}`}>
            {score != null ? (
              <>
                <span className="text-lg font-bold leading-none">{score}</span>
                <span className="text-[9px] leading-none mt-0.5">%</span>
              </>
            ) : (
              <span className="text-lg">—</span>
            )}
          </div>
        </div>

        {/* Content */}
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
            {/* Actions */}
            <div className="flex gap-2 flex-shrink-0 flex-wrap justify-end">
              <a
                href={job.url}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-secondary text-xs py-1 px-2"
              >
                Ver ↗
              </a>
              <button
                className={`text-xs py-1 px-2 rounded-lg font-medium border transition-colors ${
                  job.applied_at
                    ? "bg-green-100 text-green-700 border-green-300 hover:bg-green-200"
                    : "bg-indigo-100 text-indigo-700 border-indigo-300 hover:bg-indigo-200"
                }`}
                disabled={togglingApplied}
                onClick={async () => {
                  setTogglingApplied(true);
                  await onToggleApplied(job);
                  setTogglingApplied(false);
                }}
              >
                {togglingApplied ? "…" : job.applied_at ? "✓ Postulé" : "Marcar postulado"}
              </button>
              <button
                className="text-xs py-1 px-2 rounded-lg border border-gray-200 text-gray-400 hover:text-red-500 hover:border-red-200 transition-colors"
                title="Quitar de guardados"
                disabled={removing}
                onClick={async () => {
                  setRemoving(true);
                  await onUnsave(job.id);
                }}
              >
                {removing ? "…" : "✕"}
              </button>
            </div>
          </div>

          {/* Badges */}
          <div className="flex flex-wrap items-center gap-2 mt-1.5">
            <span className="text-[10px] text-gray-400">🔖 {savedDate}</span>
            {job.salary && <span className="text-xs text-gray-500">💰 {job.salary}</span>}
            {job.date_posted && <span className="text-xs text-gray-400">{job.date_posted}</span>}
            {job.applied_at && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-100 text-green-700 border border-green-300 font-medium">
                ✅ Postulado {new Date(job.applied_at).toLocaleDateString("es-CA", { day: "numeric", month: "short" })}
              </span>
            )}
            {job.source === "jobbank" && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-50 text-red-600 border border-red-200 font-medium">🍁 Job Bank</span>
            )}
            {job.source === "workopolis" && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-orange-50 text-orange-600 border border-orange-200 font-medium">🇨🇦 Workopolis</span>
            )}
            {job.source === "eluta" && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-teal-50 text-teal-600 border border-teal-200 font-medium">🔍 Eluta</span>
            )}
            {job.lmia_approved && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 font-medium">✅ LMIA</span>
            )}
            {job.ccfta_eligible && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200 font-medium">🇨🇱 CCFTA</span>
            )}
          </div>

          {job.score_summary && (
            <p className="text-xs text-gray-500 mt-1 italic">{job.score_summary}</p>
          )}

          {/* Expand skills */}
          {(job.matched_skills?.length > 0 || job.missing_skills?.length > 0 || job.snippet) && (
            <>
              <button
                onClick={() => setExpanded(!expanded)}
                className="text-xs text-indigo-500 hover:text-indigo-700 mt-1"
              >
                {expanded ? "▲ Menos detalles" : "▼ Ver detalles"}
              </button>
              {expanded && (
                <div className="mt-2 space-y-2">
                  {job.matched_skills?.length > 0 && (
                    <div>
                      <p className="text-[10px] font-medium text-gray-500 uppercase tracking-wide mb-1">Skills coincidentes</p>
                      <div className="flex flex-wrap gap-1">
                        {job.matched_skills.map((s) => (
                          <span key={s} className="badge bg-green-100 text-green-700">{s}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {job.missing_skills?.length > 0 && (
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
            </>
          )}
        </div>
      </div>
    </div>
  );
}
