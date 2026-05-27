"use client";
import { useEffect, useState } from "react";
import { listAdaptations, deleteAdaptation, getDownloadUrl, type Adaptation } from "@/lib/api";
import { formatDistanceToNow, parseISO } from "date-fns";
import { es } from "date-fns/locale";
import Link from "next/link";

function jobFallbackTitle(a: Adaptation): string {
  if (a.job_url) {
    try { return new URL(a.job_url).hostname.replace("www.", ""); } catch { /* fallthrough */ }
  }
  return "Sin título";
}

const STATUS_COLORS = {
  pending:    "bg-gray-100 text-gray-500",
  processing: "bg-indigo-100 text-indigo-600",
  done:       "bg-green-100 text-green-700",
  error:      "bg-red-100 text-red-600",
};

export default function HistoryPage() {
  const [adaptations, setAdaptations] = useState<Adaptation[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try { setAdaptations(await listAdaptations()); } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.preventDefault();
    if (!confirm("¿Eliminar esta adaptación?")) return;
    await deleteAdaptation(id);
    load();
  };

  if (loading) return <div className="text-center py-20 text-gray-400">Cargando…</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-800">📂 Historial de adaptaciones</h1>
        <Link href="/" className="btn-primary">+ Nueva adaptación</Link>
      </div>

      {adaptations.length === 0 ? (
        <div className="card p-12 text-center text-gray-400">
          <p className="text-4xl mb-3">📭</p>
          <p>No hay adaptaciones todavía. <Link href="/" className="text-indigo-500 hover:underline">Crea la primera.</Link></p>
        </div>
      ) : (
        <div className="space-y-3">
          {adaptations.map((a) => (
            <div key={a.id} className="card p-4 flex items-center justify-between gap-4 flex-wrap">
              <div className="min-w-0">
                <p className="font-semibold text-gray-800">
                  {a.job_title || jobFallbackTitle(a)}
                  {a.company_name && (
                    <span className="ml-2 text-gray-400 font-normal">· {a.company_name}</span>
                  )}
                </p>
                <p className="text-xs text-gray-400 mt-0.5">
                  {formatDistanceToNow(
                    new Date(a.created_at.endsWith("Z") ? a.created_at : a.created_at + "Z"),
                    { addSuffix: true, locale: es }
                  )}
                  {a.sections_changed.length > 0 && (
                    <span className="ml-2">· {a.sections_changed.join(", ")} adaptado(s)</span>
                  )}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className={`badge ${STATUS_COLORS[a.status]}`}>{a.status}</span>
                {a.status === "done" && (
                  <a
                    href={getDownloadUrl(a.id)}
                    className="btn-primary text-xs py-1"
                    target="_blank"
                  >
                    ⬇️ .docx
                  </a>
                )}
                <button
                  className="text-gray-400 hover:text-red-500 transition-colors p-1"
                  onClick={(e) => handleDelete(a.id, e)}
                  title="Eliminar"
                >
                  🗑️
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
