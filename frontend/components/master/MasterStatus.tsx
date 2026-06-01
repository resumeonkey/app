"use client";
import { useState } from "react";
import { type MasterDetail, type MasterSummary, updateMasterPreferences } from "@/lib/api";

const SECTION_LABELS: Record<string, string> = {
  summary: "Summary/Profile",
  skills: "Skills",
  experience: "Experience",
  education: "Education",
  projects: "Projects",
  certifications: "Certifications",
  languages: "Languages",
};

const ENGLISH_LEVELS: { val: MasterSummary["english_level"]; label: string; desc: string }[] = [
  { val: "any",            label: "Sin definir",         desc: "No aplica filtro de inglés" },
  { val: "basic",          label: "Básico · A2–B1",      desc: "Lee y escribe oraciones simples" },
  { val: "conversational", label: "Conversacional · B1–B2", desc: "Puede comunicarse con esfuerzo" },
  { val: "professional",   label: "Profesional · B2–C1", desc: "Inglés de negocios completo" },
  { val: "fluent",         label: "Fluido · C1–C2",      desc: "Nivel nativo o casi nativo" },
];

interface Props {
  master: MasterDetail;
  onReplace: () => void;
  onMasterUpdated?: (m: MasterSummary) => void;
}

export function MasterStatus({ master, onReplace, onMasterUpdated }: Props) {
  const sections = Object.keys(master.sections || {});
  const [englishLevel, setEnglishLevel] = useState<MasterSummary["english_level"]>(
    master.english_level ?? "any"
  );
  const [saving, setSaving] = useState(false);

  const handleEnglishLevelChange = async (val: MasterSummary["english_level"]) => {
    setEnglishLevel(val);
    setSaving(true);
    try {
      const updated = await updateMasterPreferences(master.id, { english_level: val });
      onMasterUpdated?.(updated);
    } catch {
      // revert on failure
      setEnglishLevel(englishLevel);
    } finally {
      setSaving(false);
    }
  };

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

      {/* ── English level — candidate profile preference ────────────────────── */}
      <div className="mt-5 border-t border-gray-100 pt-4">
        <div className="flex items-center gap-2 mb-2">
          <p className="text-xs text-gray-400 font-medium uppercase tracking-wide">
            🗣️ Mi nivel de inglés
          </p>
          {saving && <span className="text-[10px] text-indigo-400">Guardando…</span>}
        </div>
        <div className="flex flex-wrap gap-2">
          {ENGLISH_LEVELS.map(({ val, label, desc }) => (
            <button
              key={val}
              title={desc}
              onClick={() => handleEnglishLevelChange(val)}
              disabled={saving}
              className={`px-3 py-1 rounded-full text-xs border transition-all ${
                englishLevel === val
                  ? "bg-indigo-100 border-indigo-400 text-indigo-700 font-medium"
                  : "border-gray-200 text-gray-500 hover:border-indigo-300"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        {englishLevel !== "any" && (
          <p className="text-[11px] text-gray-400 mt-1.5">
            Las búsquedas usarán este nivel por defecto — puedes cambiarlo en cada búsqueda individual.
          </p>
        )}
      </div>
    </div>
  );
}
