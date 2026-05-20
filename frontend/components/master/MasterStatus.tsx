"use client";
import { type MasterDetail } from "@/lib/api";

const SECTION_LABELS: Record<string, string> = {
  summary: "Summary/Profile",
  skills: "Skills",
  experience: "Experience",
  education: "Education",
  projects: "Projects",
  certifications: "Certifications",
  languages: "Languages",
};

interface Props {
  master: MasterDetail;
  onReplace: () => void;
}

export function MasterStatus({ master, onReplace }: Props) {
  const sections = Object.keys(master.sections || {});

  return (
    <div className="card p-5 border-l-4 border-l-green-500">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-green-600 font-bold">✓ Resume maestro activo</span>
            {master.candidate_name && (
              <span className="badge bg-gray-100 text-gray-600">{master.candidate_name}</span>
            )}
          </div>
          <p className="text-sm text-gray-500 mt-0.5">
            {master.original_filename}
            {master.notes && <span className="ml-2 text-gray-400">· {master.notes}</span>}
          </p>
        </div>
        <button className="btn-secondary text-xs py-1 shrink-0" onClick={onReplace}>
          🔄 Reemplazar
        </button>
      </div>

      {sections.length > 0 && (
        <div className="mt-4">
          <p className="text-xs text-gray-400 mb-2 font-medium">SECCIONES DETECTADAS</p>
          <div className="flex flex-wrap gap-2">
            {sections.map((s) => {
              const isAdaptable = ["summary", "skills", "experience", "projects"].includes(s);
              return (
                <span
                  key={s}
                  className={`badge ${isAdaptable ? "bg-indigo-100 text-indigo-700" : "bg-gray-100 text-gray-500"}`}
                  title={isAdaptable ? "Adaptable según la oferta" : "Nunca se modifica"}
                >
                  {isAdaptable ? "✏️" : "🔒"} {SECTION_LABELS[s] || s}
                </span>
              );
            })}
          </div>
          <p className="text-xs text-gray-400 mt-2">
            ✏️ adaptable según oferta · 🔒 siempre protegido
          </p>
        </div>
      )}
    </div>
  );
}
