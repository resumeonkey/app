"use client";
import { useRef, useState } from "react";
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
  { val: "any",            label: "Sin definir",            desc: "No aplica filtro de inglés" },
  { val: "basic",          label: "Básico · A2–B1",         desc: "Lee y escribe oraciones simples" },
  { val: "conversational", label: "Conversacional · B1–B2", desc: "Puede comunicarse con esfuerzo" },
  { val: "professional",   label: "Profesional · B2–C1",    desc: "Inglés de negocios completo" },
  { val: "fluent",         label: "Fluido · C1–C2",         desc: "Nivel nativo o casi nativo" },
];

// Suggested tags shown as quick-add chips (user can click to append)
const SUGGESTED_TAGS = [
  "QA", "Testing", "SQL", "APIs", "Postman", "Product Owner",
  "Implementation", "Configuration", "Business Analyst", "Systems Analyst",
  "Technical Support", "Telecom", "Scrum", "JIRA", "Data Validation",
  "Requirements", "Agile", "Software", "SaaS", "Onboarding",
];

interface Props {
  master: MasterDetail;
  onReplace: () => void;
  onMasterUpdated?: (m: MasterSummary) => void;
}

export function MasterStatus({ master, onReplace, onMasterUpdated }: Props) {
  const sections = Object.keys(master.sections || {});

  // English level
  const [englishLevel, setEnglishLevel] = useState<MasterSummary["english_level"]>(
    master.english_level ?? "any"
  );
  const [saving, setSaving] = useState(false);

  // Profile tags — live input state
  const [tagsInput, setTagsInput] = useState<string>(master.profile_tags ?? "");
  const [tagsSaving, setTagsSaving] = useState(false);
  const saveTagsTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleEnglishLevelChange = async (val: MasterSummary["english_level"]) => {
    setEnglishLevel(val);
    setSaving(true);
    try {
      const updated = await updateMasterPreferences(master.id, { english_level: val });
      onMasterUpdated?.(updated);
    } catch {
      setEnglishLevel(englishLevel);
    } finally {
      setSaving(false);
    }
  };

  // Tags: auto-save 800ms after the user stops typing
  const handleTagsChange = (value: string) => {
    setTagsInput(value);
    if (saveTagsTimer.current) clearTimeout(saveTagsTimer.current);
    saveTagsTimer.current = setTimeout(() => saveTags(value), 800);
  };

  const saveTags = async (value: string) => {
    setTagsSaving(true);
    try {
      const updated = await updateMasterPreferences(master.id, { profile_tags: value });
      onMasterUpdated?.(updated);
    } catch {
      // silent — value stays in input
    } finally {
      setTagsSaving(false);
    }
  };

  // Append a suggested tag if not already present
  const addSuggestedTag = (tag: string) => {
    const current = tagsInput.split(",").map((t) => t.trim()).filter(Boolean);
    if (current.some((t) => t.toLowerCase() === tag.toLowerCase())) return;
    const newVal = current.length > 0 ? current.join(", ") + ", " + tag : tag;
    setTagsInput(newVal);
    if (saveTagsTimer.current) clearTimeout(saveTagsTimer.current);
    saveTagsTimer.current = setTimeout(() => saveTags(newVal), 800);
  };

  // Parse current tags for display
  const currentTags = tagsInput.split(",").map((t) => t.trim()).filter(Boolean);

  const removeTag = (tag: string) => {
    const updated = currentTags.filter((t) => t !== tag).join(", ");
    setTagsInput(updated);
    if (saveTagsTimer.current) clearTimeout(saveTagsTimer.current);
    saveTagsTimer.current = setTimeout(() => saveTags(updated), 800);
  };

  return (
    <div className="card p-5 border-l-4 border-l-green-500">
      {/* Header */}
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

      {/* Sections detected */}
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

      {/* ── Profile tags ────────────────────────────────────────────────────── */}
      <div className="mt-5 border-t border-gray-100 pt-4">
        <div className="flex items-center gap-2 mb-1.5">
          <p className="text-xs text-gray-500 font-semibold uppercase tracking-wide">
            🎯 Mi perfil técnico
          </p>
          {tagsSaving && <span className="text-[10px] text-indigo-400">Guardando…</span>}
        </div>
        <p className="text-[11px] text-gray-400 mb-2">
          Escribe tus habilidades separadas por coma. El buscador las usa como señal prioritaria
          para encontrar los roles correctos y calcular la compatibilidad real.
        </p>

        {/* Text input */}
        <input
          type="text"
          value={tagsInput}
          onChange={(e) => handleTagsChange(e.target.value)}
          placeholder="QA, Testing, SQL, Product Owner, Implementation, Telecom, APIs…"
          className="input w-full text-sm"
        />

        {/* Current tags as chips */}
        {currentTags.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {currentTags.map((tag) => (
              <span
                key={tag}
                className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-indigo-100 border border-indigo-300 text-indigo-700 text-[11px] font-medium"
              >
                {tag}
                <button
                  onClick={() => removeTag(tag)}
                  className="text-indigo-400 hover:text-indigo-700 leading-none"
                  title="Quitar"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}

        {/* Suggested tags to quick-add */}
        <div className="mt-2.5">
          <p className="text-[10px] text-gray-400 mb-1">Sugerencias — haz clic para agregar:</p>
          <div className="flex flex-wrap gap-1.5">
            {SUGGESTED_TAGS.filter(
              (t) => !currentTags.some((ct) => ct.toLowerCase() === t.toLowerCase())
            ).map((tag) => (
              <button
                key={tag}
                onClick={() => addSuggestedTag(tag)}
                className="px-2 py-0.5 rounded-full border border-gray-200 text-gray-500 text-[11px] hover:border-indigo-300 hover:text-indigo-600 hover:bg-indigo-50 transition-all"
              >
                + {tag}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── English level ────────────────────────────────────────────────────── */}
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
            Las búsquedas usarán este nivel por defecto.
          </p>
        )}
      </div>
    </div>
  );
}
