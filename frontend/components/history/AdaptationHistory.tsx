"use client";
import { type Adaptation } from "@/lib/api";

interface Props {
  adaptedJobs: Record<string, Adaptation>;
  onView: (adaptation: Adaptation) => void;
}

export function AdaptationHistory({ adaptedJobs, onView }: Props) {
  const entries = Object.values(adaptedJobs).sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  if (entries.length === 0) return null;

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-base font-semibold text-gray-700">
          📋 Historial de esta sesión
        </h2>
        <span className="text-xs text-gray-400">
          {entries.length} resume{entries.length !== 1 ? "s" : ""} generado{entries.length !== 1 ? "s" : ""}
        </span>
      </div>

      <div className="space-y-2">
        {entries.map((a) => {
          const isApplied = !!a.applied_at;
          return (
            <div
              key={a.id}
              className={`flex items-center gap-3 rounded-xl border px-3 py-2.5 transition-all ${
                isApplied
                  ? "border-green-200 bg-green-50/40"
                  : "border-gray-100 bg-gray-50/60 hover:border-indigo-200 hover:bg-indigo-50/20"
              }`}
            >
              {/* Status icon */}
              <div className="flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-base
                              bg-white border border-gray-200 shadow-sm">
                {isApplied ? "✅" : "📄"}
              </div>

              {/* Job info */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">
                  {a.job_title || "Rol sin título"}
                </p>
                <p className="text-xs text-gray-500 truncate">
                  {a.company_name || "Empresa desconocida"}
                  {isApplied && (
                    <span className="ml-2 text-green-600 font-medium">· Postulado ✓</span>
                  )}
                </p>
              </div>

              {/* Time */}
              <span className="flex-shrink-0 text-[10px] text-gray-400 hidden sm:block">
                {formatTime(a.created_at)}
              </span>

              {/* Actions */}
              <div className="flex-shrink-0 flex items-center gap-1.5">
                {a.job_url && (
                  <a
                    href={a.job_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[11px] px-2 py-1 rounded-lg border border-gray-200 text-gray-500
                               hover:text-gray-700 hover:border-gray-300 transition-colors"
                    title="Ver oferta"
                  >
                    ↗
                  </a>
                )}
                <button
                  onClick={() => onView(a)}
                  className="text-[11px] px-2.5 py-1 rounded-lg border border-indigo-200 bg-indigo-50
                             text-indigo-600 hover:bg-indigo-100 font-medium transition-colors"
                >
                  Ver resume
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    const now = new Date();
    const diffMin = Math.round((now.getTime() - d.getTime()) / 60000);
    if (diffMin < 1)  return "ahora";
    if (diffMin < 60) return `hace ${diffMin} min`;
    const diffH = Math.floor(diffMin / 60);
    if (diffH < 24)   return `hace ${diffH}h`;
    return d.toLocaleDateString("es-CL", { day: "numeric", month: "short" });
  } catch {
    return "";
  }
}
