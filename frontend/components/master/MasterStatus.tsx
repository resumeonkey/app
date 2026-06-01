"use client";
import { useRef, useState } from "react";
import {
  type MasterDetail,
  type MasterSummary,
  type ProfilePreferences,
  updateMasterPreferences,
} from "@/lib/api";

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

// Generic exclusions that apply to MOST office/professional profiles.
// Physical trades that almost no desk-job seeker wants to compete in.
const COMMON_EXCLUDED = [
  "Construction", "Civil", "MEP", "Superintendent", "Field Safety",
  "Safety Coordinator", "Site Coordinator", "Heavy Equipment",
  "Electrician", "Plumber", "Carpenter", "Concrete", "Crusher Operator",
  "Batch Plant", "Red Seal", "EIT",
];

// Industry templates — generic starting points the user then edits.
// These are PLATFORM data, not tied to any specific candidate.
interface Template {
  key: string;
  label: string;
  icon: string;
  target_roles: string;
  profile_tags: string;
  industry_experience: string;
  target_industries: string;
  excluded_roles: string;
}

const TEMPLATES: Template[] = [
  {
    key: "tech", label: "Tecnología / IT", icon: "💻",
    target_roles: "Software Developer, QA Analyst, Business Systems Analyst, Implementation Specialist, Technical Support Analyst, Product Owner",
    profile_tags: "QA, Testing, SQL, APIs, Software, Agile, Requirements",
    industry_experience: "Technology, Software",
    target_industries: "Technology, Software SaaS, Fintech",
    excluded_roles: COMMON_EXCLUDED.join(", "),
  },
  {
    key: "business", label: "Business / Análisis", icon: "📊",
    target_roles: "Business Analyst, Operations Analyst, Project Coordinator, Process Analyst, Data Analyst",
    profile_tags: "Business Analysis, Process Improvement, Stakeholder Management, Excel, Reporting",
    industry_experience: "Business, Consulting",
    target_industries: "Technology, Consulting, Finance",
    excluded_roles: COMMON_EXCLUDED.join(", "),
  },
  {
    key: "product", label: "Product Management", icon: "🚀",
    target_roles: "Product Owner, Product Manager, Product Specialist, Technical Product Manager",
    profile_tags: "Product Management, Agile, Scrum, Roadmapping, User Stories, Stakeholder Management",
    industry_experience: "Technology, SaaS",
    target_industries: "Technology, SaaS, Fintech",
    excluded_roles: COMMON_EXCLUDED.join(", "),
  },
  {
    key: "hospitality", label: "Hospitalidad", icon: "🏨",
    target_roles: "Hotel Manager, Guest Services Manager, Operations Manager, Front Office Manager, Food & Beverage Manager",
    profile_tags: "Customer Service, Operations, Team Leadership, Scheduling, Guest Relations",
    industry_experience: "Hospitality, Tourism, Food & Beverage",
    target_industries: "Hospitality, Tourism",
    excluded_roles: "Software Developer, Data Engineer, " + COMMON_EXCLUDED.join(", "),
  },
  {
    key: "operations", label: "Operaciones / Logística", icon: "📦",
    target_roles: "Operations Coordinator, Logistics Coordinator, Workforce Coordinator, Scheduling Coordinator, Service Coordinator",
    profile_tags: "Operations, Scheduling, Logistics, Documentation, Process Improvement, Excel",
    industry_experience: "Operations, Logistics",
    target_industries: "Logistics, Operations, Facilities Management",
    excluded_roles: COMMON_EXCLUDED.join(", "),
  },
  {
    key: "finance", label: "Finanzas / Contabilidad", icon: "💰",
    target_roles: "Accountant, Financial Analyst, Bookkeeper, Accounts Payable, Payroll Specialist",
    profile_tags: "Accounting, Financial Analysis, Excel, Reconciliation, Reporting, QuickBooks",
    industry_experience: "Finance, Accounting",
    target_industries: "Finance, Insurance, Banking",
    excluded_roles: COMMON_EXCLUDED.join(", "),
  },
  {
    key: "healthcare", label: "Salud / Admin", icon: "🏥",
    target_roles: "Healthcare Administrator, Medical Office Coordinator, Patient Services Coordinator, Health Records Specialist",
    profile_tags: "Healthcare Administration, Scheduling, Patient Coordination, Documentation, Compliance",
    industry_experience: "Healthcare",
    target_industries: "Healthcare, Healthcare Technology",
    excluded_roles: COMMON_EXCLUDED.join(", "),
  },
  {
    key: "marketing", label: "Marketing", icon: "📣",
    target_roles: "Marketing Coordinator, Digital Marketing Specialist, Content Specialist, Social Media Manager, Marketing Analyst",
    profile_tags: "Marketing, Content, Social Media, Analytics, SEO, Campaign Management",
    industry_experience: "Marketing, Media",
    target_industries: "Technology, Media, E-commerce",
    excluded_roles: COMMON_EXCLUDED.join(", "),
  },
];

interface Props {
  master: MasterDetail;
  onReplace: () => void;
  onMasterUpdated?: (m: MasterSummary) => void;
}

export function MasterStatus({ master, onReplace, onMasterUpdated }: Props) {
  const sections = Object.keys(master.sections || {});

  // ── State for each editable field ─────────────────────────────────────────
  const [profileName, setProfileName] = useState(master.profile_name ?? "");
  const [englishLevel, setEnglishLevel] = useState<MasterSummary["english_level"]>(
    master.english_level ?? "any"
  );
  const [tags, setTags] = useState(master.profile_tags ?? "");
  const [targetRoles, setTargetRoles] = useState(master.target_roles ?? "");
  const [excludedRoles, setExcludedRoles] = useState(master.excluded_roles ?? "");
  const [industryExp, setIndustryExp] = useState(master.industry_experience ?? "");
  const [targetInds, setTargetInds] = useState(master.target_industries ?? "");

  const [savingField, setSavingField] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  // Debounced save for a single preference field
  const saveField = (field: keyof ProfilePreferences, value: string, delay = 800) => {
    if (timers.current[field]) clearTimeout(timers.current[field]);
    timers.current[field] = setTimeout(async () => {
      setSavingField(field);
      try {
        const updated = await updateMasterPreferences(master.id, { [field]: value });
        onMasterUpdated?.(updated);
      } catch {
        /* keep local value */
      } finally {
        setSavingField(null);
      }
    }, delay);
  };

  const handleEnglishLevelChange = async (val: MasterSummary["english_level"]) => {
    setEnglishLevel(val);
    setSavingField("english_level");
    try {
      const updated = await updateMasterPreferences(master.id, { english_level: val });
      onMasterUpdated?.(updated);
    } catch {
      setEnglishLevel(englishLevel);
    } finally {
      setSavingField(null);
    }
  };

  // Apply a template — fills all fields and saves them
  const applyTemplate = async (t: Template) => {
    setProfileName(t.label);
    setTags(t.profile_tags);
    setTargetRoles(t.target_roles);
    setExcludedRoles(t.excluded_roles);
    setIndustryExp(t.industry_experience);
    setTargetInds(t.target_industries);
    setSavingField("template");
    try {
      const updated = await updateMasterPreferences(master.id, {
        profile_name: t.label,
        profile_tags: t.profile_tags,
        target_roles: t.target_roles,
        excluded_roles: t.excluded_roles,
        industry_experience: t.industry_experience,
        target_industries: t.target_industries,
      });
      onMasterUpdated?.(updated);
    } catch {
      /* ignore */
    } finally {
      setSavingField(null);
    }
  };

  return (
    <div className="card p-5 border-l-4 border-l-green-500">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-green-600 font-bold">✓ Perfil activo</span>
            {master.profile_name ? (
              <span className="badge bg-indigo-100 text-indigo-700 font-medium">{master.profile_name}</span>
            ) : master.candidate_name ? (
              <span className="badge bg-gray-100 text-gray-600">{master.candidate_name}</span>
            ) : null}
          </div>
          <p className="text-sm text-gray-500 mt-0.5 truncate">
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
        </div>
      )}

      {/* ── Toggle: configure search profile ─────────────────────────────────── */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="mt-4 text-sm text-indigo-600 hover:text-indigo-800 flex items-center gap-1 font-medium"
      >
        {expanded ? "▲" : "▼"} 🎯 Configurar perfil de búsqueda
        {savingField && <span className="text-[10px] text-indigo-400 ml-2">Guardando…</span>}
      </button>

      {expanded && (
        <div className="mt-3 space-y-4 border-t border-gray-100 pt-4">
          {/* Templates */}
          <div>
            <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
              Plantillas rápidas (luego puedes editar)
            </label>
            <div className="flex flex-wrap gap-1.5">
              {TEMPLATES.map((t) => (
                <button
                  key={t.key}
                  onClick={() => applyTemplate(t)}
                  className="px-2.5 py-1 rounded-lg border border-gray-200 text-gray-600 text-[11px] hover:border-indigo-300 hover:bg-indigo-50 transition-all"
                >
                  {t.icon} {t.label}
                </button>
              ))}
            </div>
          </div>

          {/* Profile name */}
          <div>
            <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1">
              Nombre del perfil
            </label>
            <input
              type="text"
              value={profileName}
              maxLength={60}
              onChange={(e) => { setProfileName(e.target.value); saveField("profile_name", e.target.value); }}
              placeholder="Ej: Tech / Implementation, Hospitalidad, Operaciones…"
              className="input w-full text-sm"
            />
          </div>

          {/* Target roles */}
          <TagsField
            label="✅ Roles objetivo"
            hint="Los puestos que SÍ quieres encontrar. El buscador basa las queries en estos."
            value={targetRoles}
            onChange={(v) => { setTargetRoles(v); saveField("target_roles", v); }}
            max={400}
            chipColor="green"
          />

          {/* Excluded roles */}
          <TagsField
            label="🚫 Roles excluidos"
            hint="Términos que NO quieres ver. Se filtran ANTES de mostrar resultados."
            value={excludedRoles}
            onChange={(v) => { setExcludedRoles(v); saveField("excluded_roles", v); }}
            max={400}
            chipColor="red"
            quickAdd={COMMON_EXCLUDED}
          />

          {/* Technical keywords */}
          <TagsField
            label="🔧 Palabras clave / habilidades"
            hint="Tu expertise principal. Señal prioritaria para el scoring."
            value={tags}
            onChange={(v) => { setTags(v); saveField("profile_tags", v); }}
            max={250}
            chipColor="indigo"
          />

          {/* Industry experience */}
          <TagsField
            label="🏢 Industrias con experiencia"
            hint="Dónde YA tienes experiencia. Evita falsos 'industry gap' en el scoring."
            value={industryExp}
            onChange={(v) => { setIndustryExp(v); saveField("industry_experience", v); }}
            max={200}
            chipColor="blue"
          />

          {/* Target industries */}
          <TagsField
            label="🎯 Industrias objetivo"
            hint="Dónde quieres trabajar. Influye en las queries generadas."
            value={targetInds}
            onChange={(v) => { setTargetInds(v); saveField("target_industries", v); }}
            max={200}
            chipColor="purple"
          />

          {/* English level */}
          <div>
            <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
              🗣️ Nivel de inglés
            </label>
            <div className="flex flex-wrap gap-2">
              {ENGLISH_LEVELS.map(({ val, label, desc }) => (
                <button
                  key={val}
                  title={desc}
                  onClick={() => handleEnglishLevelChange(val)}
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
          </div>
        </div>
      )}
    </div>
  );
}

// ── Reusable comma-separated tags field ──────────────────────────────────────

const CHIP_STYLES: Record<string, string> = {
  green:  "bg-green-100 border-green-300 text-green-700",
  red:    "bg-red-100 border-red-300 text-red-700",
  indigo: "bg-indigo-100 border-indigo-300 text-indigo-700",
  blue:   "bg-blue-100 border-blue-300 text-blue-700",
  purple: "bg-purple-100 border-purple-300 text-purple-700",
};

interface TagsFieldProps {
  label: string;
  hint: string;
  value: string;
  onChange: (v: string) => void;
  max: number;
  chipColor: keyof typeof CHIP_STYLES;
  quickAdd?: string[];
}

function TagsField({ label, hint, value, onChange, max, chipColor, quickAdd }: TagsFieldProps) {
  const tags = value.split(",").map((t) => t.trim()).filter(Boolean);

  const removeTag = (tag: string) => {
    onChange(tags.filter((t) => t !== tag).join(", "));
  };

  const addTag = (tag: string) => {
    if (tags.some((t) => t.toLowerCase() === tag.toLowerCase())) return;
    onChange(tags.length ? tags.join(", ") + ", " + tag : tag);
  };

  return (
    <div>
      <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-0.5">
        {label}
      </label>
      <p className="text-[10px] text-gray-400 mb-1.5">{hint}</p>
      <input
        type="text"
        value={value}
        maxLength={max}
        onChange={(e) => onChange(e.target.value.slice(0, max))}
        placeholder="Separa con comas…"
        className={`input w-full text-sm ${value.length >= max ? "border-amber-400 ring-1 ring-amber-300" : ""}`}
      />
      <div className="flex justify-end mt-0.5">
        <span className={`text-[10px] tabular-nums ${value.length >= max ? "text-amber-500" : "text-gray-300"}`}>
          {value.length}/{max}
        </span>
      </div>

      {/* Current tags */}
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-1">
          {tags.map((tag) => (
            <span
              key={tag}
              className={`flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-medium ${CHIP_STYLES[chipColor]}`}
            >
              {tag}
              <button onClick={() => removeTag(tag)} className="opacity-50 hover:opacity-100 leading-none">×</button>
            </span>
          ))}
        </div>
      )}

      {/* Quick-add suggestions */}
      {quickAdd && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {quickAdd
            .filter((q) => !tags.some((t) => t.toLowerCase() === q.toLowerCase()))
            .slice(0, 16)
            .map((q) => (
              <button
                key={q}
                onClick={() => addTag(q)}
                className="px-2 py-0.5 rounded-full border border-gray-200 text-gray-500 text-[11px] hover:border-indigo-300 hover:text-indigo-600 transition-all"
              >
                + {q}
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
