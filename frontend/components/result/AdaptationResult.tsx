"use client";
import { useEffect, useRef, useState } from "react";
import { getAdaptation, getDownloadUrl, type Adaptation, type BlockChanged, type JobAnalysis } from "@/lib/api";

const SECTION_NAMES: Record<string, string> = {
  summary: "Summary / Profile",
  skills: "Skills",
  experience: "Experience",
  projects: "Projects",
};

const STATUS_UI = {
  pending:    { label: "En cola…",           color: "bg-gray-100 text-gray-500",   spin: false },
  processing: { label: "Procesando con IA…", color: "bg-indigo-100 text-indigo-600", spin: true },
  done:       { label: "Listo",              color: "bg-green-100 text-green-700", spin: false },
  error:      { label: "Error",              color: "bg-red-100 text-red-600",     spin: false },
};

interface Props {
  adaptationId: string;
  onReset: () => void;
}

export function AdaptationResult({ adaptationId, onReset }: Props) {
  const [adaptation, setAdaptation] = useState<Adaptation | null>(null);
  const [activeBlock, setActiveBlock] = useState(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetch = async () => {
    const a = await getAdaptation(adaptationId);
    setAdaptation(a);
    if (a.status === "done" || a.status === "error") {
      if (pollRef.current) clearInterval(pollRef.current);
    }
  };

  useEffect(() => {
    fetch();
    pollRef.current = setInterval(fetch, 2500);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [adaptationId]);

  if (!adaptation) return <div className="text-center py-12 text-gray-400">Cargando…</div>;

  const ui = STATUS_UI[adaptation.status];
  const blocks = adaptation.blocks_changed || [];
  const analysis: JobAnalysis = adaptation.job_analysis || {};

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="card p-5">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-lg font-bold text-gray-800">
              {adaptation.job_title || "Adaptación en proceso"}
              {adaptation.company_name && (
                <span className="ml-2 text-gray-400 font-normal text-base">
                  · {adaptation.company_name}
                </span>
              )}
            </h2>
            <span className={`badge mt-1 ${ui.color}`}>
              {ui.spin && <span className="mr-1 animate-spin inline-block">⟳</span>}
              {ui.label}
            </span>
          </div>
          <button className="btn-secondary text-xs" onClick={onReset}>
            ← Nueva adaptación
          </button>
        </div>

        {/* Processing stages indicator */}
        {(adaptation.status === "pending" || adaptation.status === "processing") && (
          <div className="mt-4 space-y-2">
            {[
              "Analizando la oferta laboral…",
              "Decidiendo qué secciones adaptar…",
              "Reescribiendo secciones seleccionadas…",
              "Generando el .docx adaptado…",
            ].map((step, i) => (
              <div key={i} className="flex items-center gap-2 text-sm text-gray-500">
                <span className="animate-pulse">⟳</span> {step}
              </div>
            ))}
          </div>
        )}

        {adaptation.status === "error" && (
          <p className="mt-3 text-sm text-red-600 bg-red-50 rounded-lg p-3">
            ⚠️ {adaptation.error_msg}
          </p>
        )}
      </div>

      {/* Job analysis summary */}
      {adaptation.status === "done" && analysis.job_title && (
        <div className="card p-5">
          <h3 className="font-semibold text-gray-700 mb-3">🔍 Análisis de la oferta</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: "Seniority",       value: analysis.seniority_level ?? "—" },
              { label: "Industria",       value: analysis.industry ?? "—" },
              { label: "Años requeridos", value: analysis.required_experience_years != null ? `${analysis.required_experience_years}+` : "—" },
              { label: "Idiomas",         value: analysis.language_requirements?.join(", ") || "—" },
            ].map((item) => (
              <div key={item.label} className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-400 font-medium">{item.label}</p>
                <p className="text-sm font-semibold text-gray-700 mt-0.5">{item.value}</p>
              </div>
            ))}
          </div>

          {(analysis.ats_keywords?.length ?? 0) > 0 && (
            <div className="mt-4">
              <p className="text-xs text-gray-400 mb-2 font-medium">KEYWORDS ATS INCORPORADOS</p>
              <div className="flex flex-wrap gap-1.5">
                {analysis.ats_keywords!.map((kw) => (
                  <span key={kw} className="badge bg-indigo-50 text-indigo-600">{kw}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Changed blocks */}
      {adaptation.status === "done" && blocks.length > 0 && (
        <div className="card overflow-hidden">
          <div className="border-b border-gray-100 flex overflow-x-auto">
            {blocks.map((block, i) => (
              <button
                key={i}
                onClick={() => setActiveBlock(i)}
                className={`px-5 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors
                  ${activeBlock === i
                    ? "border-indigo-500 text-indigo-600"
                    : "border-transparent text-gray-500 hover:text-gray-700"
                  }`}
              >
                ✏️ {SECTION_NAMES[block.section] || block.section}
              </button>
            ))}
          </div>

          <div className="p-5">
            <BlockDiff block={blocks[activeBlock]} />
          </div>
        </div>
      )}

      {adaptation.status === "done" && blocks.length === 0 && (
        <div className="card p-6 text-center text-gray-500">
          <p className="text-2xl mb-2">✅</p>
          <p>El resume ya estaba bien alineado con esta oferta. No se realizaron cambios.</p>
        </div>
      )}

      {/* Download */}
      {adaptation.status === "done" && (
        <div className="card p-5 flex items-center justify-between gap-4 flex-wrap">
          <div>
            <p className="font-semibold text-gray-800">Resume listo para postular</p>
            <p className="text-sm text-gray-400 mt-0.5">
              Mismo formato canadiense · {blocks.length} sección(es) adaptada(s)
            </p>
          </div>
          <a
            href={getDownloadUrl(adaptation.id)}
            className="btn-primary px-6 py-3 text-base"
            target="_blank"
            rel="noopener noreferrer"
          >
            ⬇️ Descargar .docx
          </a>
        </div>
      )}
    </div>
  );
}


function BlockDiff({ block }: { block: BlockChanged }) {
  const [view, setView] = useState<"diff" | "original" | "adapted">("diff");

  return (
    <div className="space-y-3">
      <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:justify-between">
        <p className="text-xs text-gray-500 italic">
          <span className="font-medium text-gray-700">Razón:</span> {block.reason}
        </p>
        <div className="flex rounded-lg overflow-hidden border border-gray-200 text-xs self-start sm:self-auto">
          {(["diff", "original", "adapted"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`px-3 py-1 ${view === v ? "bg-indigo-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50"}`}
            >
              {v === "diff" ? "Cambios" : v === "original" ? "Original" : "Adaptado"}
            </button>
          ))}
        </div>
      </div>

      {view === "diff" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <p className="text-xs font-semibold text-red-500 mb-1.5">ORIGINAL</p>
            <pre className="text-xs text-gray-700 bg-red-50 rounded-lg p-3 whitespace-pre-wrap border border-red-100 max-h-64 overflow-y-auto leading-relaxed">
              {block.original}
            </pre>
          </div>
          <div>
            <p className="text-xs font-semibold text-green-600 mb-1.5">ADAPTADO</p>
            <pre className="text-xs text-gray-700 bg-green-50 rounded-lg p-3 whitespace-pre-wrap border border-green-100 max-h-64 overflow-y-auto leading-relaxed">
              {block.adapted}
            </pre>
          </div>
        </div>
      )}

      {view === "original" && (
        <pre className="text-sm text-gray-700 bg-gray-50 rounded-lg p-4 whitespace-pre-wrap max-h-96 overflow-y-auto">
          {block.original}
        </pre>
      )}

      {view === "adapted" && (
        <pre className="text-sm text-gray-700 bg-indigo-50 rounded-lg p-4 whitespace-pre-wrap max-h-96 overflow-y-auto">
          {block.adapted}
        </pre>
      )}
    </div>
  );
}
