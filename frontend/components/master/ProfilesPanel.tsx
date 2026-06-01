"use client";
import { useRef, useState } from "react";
import {
  type MasterDetail,
  type MasterSummary,
  type ProfilePreferences,
  updateMasterPreferences,
  activateMaster,
  deleteMaster,
} from "@/lib/api";

// ── Templates ─────────────────────────────────────────────────────────────────

const COMMON_EXCLUDED = [
  "Construction", "Civil", "MEP", "Superintendent", "Field Safety",
  "Safety Coordinator", "Site Coordinator", "Heavy Equipment",
  "Electrician", "Plumber", "Carpenter", "Concrete", "Crusher Operator",
  "Batch Plant", "Red Seal", "EIT",
];

interface Template {
  key: string; label: string; icon: string;
  target_roles: string; profile_tags: string;
  industry_experience: string; target_industries: string; excluded_roles: string;
}

const TEMPLATES: Template[] = [
  { key: "tech", label: "Tecnología / IT", icon: "💻",
    target_roles: "Software Developer, QA Analyst, Business Systems Analyst, Implementation Specialist, Technical Support Analyst, Product Owner",
    profile_tags: "QA, Testing, SQL, APIs, Software, Agile, Requirements",
    industry_experience: "Technology, Software",
    target_industries: "Technology, Software SaaS, Fintech",
    excluded_roles: COMMON_EXCLUDED.join(", ") },
  { key: "business", label: "Business / Análisis", icon: "📊",
    target_roles: "Business Analyst, Operations Analyst, Project Coordinator, Process Analyst, Data Analyst",
    profile_tags: "Business Analysis, Process Improvement, Stakeholder Management, Excel, Reporting",
    industry_experience: "Business, Consulting",
    target_industries: "Technology, Consulting, Finance",
    excluded_roles: COMMON_EXCLUDED.join(", ") },
  { key: "product", label: "Product Management", icon: "🚀",
    target_roles: "Product Owner, Product Manager, Product Specialist, Technical Product Manager",
    profile_tags: "Product Management, Agile, Scrum, Roadmapping, User Stories",
    industry_experience: "Technology, SaaS",
    target_industries: "Technology, SaaS, Fintech",
    excluded_roles: COMMON_EXCLUDED.join(", ") },
  { key: "hospitality", label: "Hospitalidad", icon: "🏨",
    target_roles: "Hotel Manager, Guest Services Manager, Operations Manager, Front Office Manager, Food & Beverage Manager",
    profile_tags: "Customer Service, Operations, Team Leadership, Scheduling, Guest Relations",
    industry_experience: "Hospitality, Tourism, Food & Beverage",
    target_industries: "Hospitality, Tourism",
    excluded_roles: "Software Developer, Data Engineer, " + COMMON_EXCLUDED.join(", ") },
  { key: "operations", label: "Operaciones / Logística", icon: "📦",
    target_roles: "Operations Coordinator, Logistics Coordinator, Workforce Coordinator, Scheduling Coordinator, Service Coordinator",
    profile_tags: "Operations, Scheduling, Logistics, Documentation, Process Improvement, Excel",
    industry_experience: "Operations, Logistics",
    target_industries: "Logistics, Operations, Facilities Management",
    excluded_roles: COMMON_EXCLUDED.join(", ") },
  { key: "finance", label: "Finanzas / Contabilidad", icon: "💰",
    target_roles: "Accountant, Financial Analyst, Bookkeeper, Accounts Payable, Payroll Specialist",
    profile_tags: "Accounting, Financial Analysis, Excel, Reconciliation, Reporting",
    industry_experience: "Finance, Accounting",
    target_industries: "Finance, Insurance, Banking",
    excluded_roles: COMMON_EXCLUDED.join(", ") },
  { key: "healthcare", label: "Salud / Admin", icon: "🏥",
    target_roles: "Healthcare Administrator, Medical Office Coordinator, Patient Services Coordinator",
    profile_tags: "Healthcare Administration, Scheduling, Patient Coordination, Documentation",
    industry_experience: "Healthcare",
    target_industries: "Healthcare, Healthcare Technology",
    excluded_roles: COMMON_EXCLUDED.join(", ") },
  { key: "marketing", label: "Marketing", icon: "📣",
    target_roles: "Marketing Coordinator, Digital Marketing Specialist, Content Specialist, Social Media Manager",
    profile_tags: "Marketing, Content, Social Media, Analytics, SEO",
    industry_experience: "Marketing, Media",
    target_industries: "Technology, Media, E-commerce",
    excluded_roles: COMMON_EXCLUDED.join(", ") },
];

const ENGLISH_LEVELS: { val: MasterSummary["english_level"]; label: string }[] = [
  { val: "any", label: "Sin definir" },
  { val: "basic", label: "Básico · A2–B1" },
  { val: "conversational", label: "Conversacional · B1–B2" },
  { val: "professional", label: "Profesional · B2–C1" },
  { val: "fluent", label: "Fluido · C1–C2" },
];

const CHIP_STYLES: Record<string, string> = {
  green:  "bg-green-100 border-green-300 text-green-700",
  red:    "bg-red-100 border-red-300 text-red-700",
  indigo: "bg-indigo-100 border-indigo-300 text-indigo-700",
  blue:   "bg-blue-100 border-blue-300 text-blue-700",
  purple: "bg-purple-100 border-purple-300 text-purple-700",
};

// ── TagsField (reusable) ──────────────────────────────────────────────────────

function TagsField({
  label, hint, value, onChange, max, chipColor, quickAdd,
}: {
  label: string; hint?: string; value: string; onChange: (v: string) => void;
  max: number; chipColor: keyof typeof CHIP_STYLES; quickAdd?: string[];
}) {
  const tags = value.split(",").map((t) => t.trim()).filter(Boolean);
  const removeTag = (tag: string) =>
    onChange(tags.filter((t) => t !== tag).join(", "));
  const addTag = (tag: string) => {
    if (tags.some((t) => t.toLowerCase() === tag.toLowerCase())) return;
    onChange(tags.length ? tags.join(", ") + ", " + tag : tag);
  };

  return (
    <div>
      <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-0.5">
        {label}
      </label>
      {hint && <p className="text-[10px] text-gray-400 mb-1">{hint}</p>}
      <input
        type="text"
        value={value}
        maxLength={max}
        onChange={(e) => onChange(e.target.value.slice(0, max))}
        placeholder="Separa con comas…"
        className={`input w-full text-sm ${value.length >= max ? "border-amber-400" : ""}`}
      />
      <div className="flex justify-end mt-0.5">
        <span className={`text-[10px] tabular-nums ${value.length >= max ? "text-amber-500" : "text-gray-300"}`}>
          {value.length}/{max}
        </span>
      </div>
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1">
          {tags.map((tag) => (
            <span key={tag}
              className={`flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-medium ${CHIP_STYLES[chipColor]}`}>
              {tag}
              <button onClick={() => removeTag(tag)} className="opacity-50 hover:opacity-100 leading-none">×</button>
            </span>
          ))}
        </div>
      )}
      {quickAdd && (
        <div className="flex flex-wrap gap-1 mt-1.5">
          {quickAdd.filter((q) => !tags.some((t) => t.toLowerCase() === q.toLowerCase())).slice(0, 12).map((q) => (
            <button key={q} onClick={() => addTag(q)}
              className="px-2 py-0.5 rounded-full border border-gray-200 text-gray-500 text-[11px] hover:border-indigo-300 hover:text-indigo-600 transition-all">
              + {q}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── ProfileCard (one per master) ──────────────────────────────────────────────

interface ProfileCardProps {
  profile: MasterSummary;
  isActive: boolean;
  onActivate: () => void;
  onDelete: () => void;
  onUpdated: (m: MasterSummary) => void;
}

function ProfileCard({ profile, isActive, onActivate, onDelete, onUpdated }: ProfileCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  // Local state mirrors DB (syncs on save)
  const [name, setName]       = useState(profile.profile_name ?? "");
  const [tags, setTags]       = useState(profile.profile_tags ?? "");
  const [targetRoles, setTR]  = useState(profile.target_roles ?? "");
  const [excluded, setExcl]   = useState(profile.excluded_roles ?? "");
  const [indExp, setIndExp]   = useState(profile.industry_experience ?? "");
  const [tgtInds, setTgtInds] = useState(profile.target_industries ?? "");
  const [engLevel, setEngLvl] = useState<MasterSummary["english_level"]>(profile.english_level ?? "any");

  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const saveField = (field: keyof ProfilePreferences, value: string, delay = 700) => {
    if (timers.current[field]) clearTimeout(timers.current[field]);
    timers.current[field] = setTimeout(async () => {
      setSaving(true);
      try {
        const updated = await updateMasterPreferences(profile.id, { [field]: value });
        onUpdated(updated);
      } finally { setSaving(false); }
    }, delay);
  };

  const applyTemplate = async (t: Template) => {
    setName(t.label); setTags(t.profile_tags); setTR(t.target_roles);
    setExcl(t.excluded_roles); setIndExp(t.industry_experience); setTgtInds(t.target_industries);
    setSaving(true);
    try {
      const updated = await updateMasterPreferences(profile.id, {
        profile_name: t.label, profile_tags: t.profile_tags, target_roles: t.target_roles,
        excluded_roles: t.excluded_roles, industry_experience: t.industry_experience,
        target_industries: t.target_industries,
      });
      onUpdated(updated);
    } finally { setSaving(false); }
  };

  const handleDelete = async () => {
    setDeleting(true);
    setDeleteError("");
    try {
      await deleteMaster(profile.id);
      onDelete();
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } }; message?: string })
        ?.response?.data?.detail ?? (e as { message?: string })?.message ?? "Error al eliminar";
      setDeleteError(msg);
      setDeleting(false);
      // keep confirmDelete open so user sees the error
    }
  };

  const displayName = name || profile.original_filename;
  const hasConfig = !!(targetRoles || tags || excluded);

  return (
    <div className={`rounded-xl border transition-all ${
      isActive
        ? "border-indigo-300 bg-indigo-50/30"
        : "border-gray-200 bg-white"
    }`}>
      {/* Card header */}
      <div className="flex items-center gap-3 px-4 py-3">
        {/* Active indicator */}
        <div className={`w-2 h-2 rounded-full flex-shrink-0 ${isActive ? "bg-green-500" : "bg-gray-300"}`} />

        {/* Name + resume file */}
        <button className="flex-1 text-left min-w-0" onClick={() => setExpanded(!expanded)}>
          <p className="text-sm font-medium text-gray-800 truncate">
            {displayName}
            {saving && <span className="ml-2 text-[10px] text-indigo-400">Guardando…</span>}
          </p>
          <p className="text-[11px] text-gray-400 truncate">{profile.original_filename}</p>
          {hasConfig && !expanded && (
            <div className="flex gap-1 mt-1 flex-wrap">
              {targetRoles && <span className="text-[10px] bg-green-100 text-green-700 px-1.5 py-0.5 rounded">✅ Roles</span>}
              {excluded && <span className="text-[10px] bg-red-100 text-red-700 px-1.5 py-0.5 rounded">🚫 Exclusiones</span>}
              {tags && <span className="text-[10px] bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded">🔧 Skills</span>}
            </div>
          )}
        </button>

        {/* Actions */}
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {!isActive && (
            <button onClick={onActivate}
              className="text-xs px-2.5 py-1 rounded-lg border border-indigo-200 text-indigo-600 hover:bg-indigo-50 transition-all">
              Activar
            </button>
          )}
          {isActive && (
            <span className="text-[10px] px-2 py-1 rounded-lg bg-green-100 text-green-700 font-medium border border-green-200">
              ✓ Activo
            </span>
          )}
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-gray-400 hover:text-gray-600 text-lg leading-none px-1">
            {expanded ? "▲" : "▼"}
          </button>
          {/* Delete — always visible, two-click confirmation */}
          {!confirmDelete ? (
            <button
              onClick={() => { setConfirmDelete(true); setDeleteError(""); }}
              className="text-gray-300 hover:text-red-400 transition-colors text-xl leading-none px-1"
              title="Eliminar perfil">
              ×
            </button>
          ) : (
            <div className="flex flex-col items-end gap-0.5">
              <div className="flex items-center gap-1">
                <span className="text-[10px] text-red-500">¿Eliminar?</span>
                <button onClick={handleDelete} disabled={deleting}
                  className="text-[10px] px-1.5 py-0.5 rounded bg-red-500 text-white hover:bg-red-600 disabled:opacity-50">
                  {deleting ? "…" : "Sí"}
                </button>
                <button onClick={() => { setConfirmDelete(false); setDeleteError(""); }}
                  className="text-[10px] text-gray-400 hover:text-gray-600">
                  No
                </button>
              </div>
              {deleteError && (
                <span className="text-[9px] text-red-400 max-w-[140px] text-right">{deleteError}</span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Expanded configuration */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-gray-100 pt-3 space-y-4">
          {/* Templates */}
          <div>
            <p className="text-[11px] text-gray-400 font-semibold uppercase tracking-wide mb-1.5">
              Plantilla rápida
            </p>
            <div className="flex flex-wrap gap-1.5">
              {TEMPLATES.map((t) => (
                <button key={t.key} onClick={() => applyTemplate(t)}
                  className="px-2.5 py-1 rounded-lg border border-gray-200 text-gray-600 text-[11px] hover:border-indigo-300 hover:bg-indigo-50 transition-all">
                  {t.icon} {t.label}
                </button>
              ))}
            </div>
          </div>

          {/* Profile name */}
          <div>
            <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-0.5">
              Nombre del perfil
            </label>
            <input type="text" value={name} maxLength={60}
              onChange={(e) => { setName(e.target.value); saveField("profile_name", e.target.value); }}
              placeholder="Ej: Tech / QA, Hospitalidad, Operaciones…"
              className="input w-full text-sm" />
          </div>

          <TagsField label="✅ Roles objetivo"
            hint="Los puestos que SÍ quieres encontrar."
            value={targetRoles} onChange={(v) => { setTR(v); saveField("target_roles", v); }}
            max={400} chipColor="green" />

          <TagsField label="🚫 Roles excluidos"
            hint="Se filtran ANTES de mostrar resultados."
            value={excluded} onChange={(v) => { setExcl(v); saveField("excluded_roles", v); }}
            max={400} chipColor="red" quickAdd={COMMON_EXCLUDED} />

          <TagsField label="🔧 Palabras clave / habilidades"
            hint="Tu expertise principal."
            value={tags} onChange={(v) => { setTags(v); saveField("profile_tags", v); }}
            max={250} chipColor="indigo" />

          <TagsField label="🏢 Industrias con experiencia"
            hint="Dónde YA tienes experiencia."
            value={indExp} onChange={(v) => { setIndExp(v); saveField("industry_experience", v); }}
            max={200} chipColor="blue" />

          <TagsField label="🎯 Industrias objetivo"
            hint="Dónde quieres trabajar."
            value={tgtInds} onChange={(v) => { setTgtInds(v); saveField("target_industries", v); }}
            max={200} chipColor="purple" />

          {/* English level */}
          <div>
            <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
              🗣️ Nivel de inglés
            </label>
            <div className="flex flex-wrap gap-2">
              {ENGLISH_LEVELS.map(({ val, label }) => (
                <button key={val}
                  onClick={async () => {
                    setEngLvl(val);
                    const updated = await updateMasterPreferences(profile.id, { english_level: val });
                    onUpdated(updated);
                  }}
                  className={`px-3 py-1 rounded-full text-xs border transition-all ${
                    engLevel === val
                      ? "bg-indigo-100 border-indigo-400 text-indigo-700 font-medium"
                      : "border-gray-200 text-gray-500 hover:border-indigo-300"
                  }`}>{label}
                </button>
              ))}
            </div>
          </div>

        </div>
      )}
    </div>
  );
}

// ── ProfilesPanel (main export) ───────────────────────────────────────────────

interface Props {
  master: MasterDetail | null;
  masters: MasterSummary[];
  onAddProfile: () => void;          // opens upload flow
  onProfileActivated: (id: string) => void;
  onProfileDeleted: (id: string) => void;
  onProfileUpdated: (m: MasterSummary) => void;
}

export function ProfilesPanel({
  master, masters, onAddProfile, onProfileActivated, onProfileDeleted, onProfileUpdated,
}: Props) {
  const handleActivate = async (id: string) => {
    await activateMaster(id);
    onProfileActivated(id);
  };

  return (
    <div className="card p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-semibold text-gray-700">👤 Mis Perfiles</h2>
          <p className="text-xs text-gray-400 mt-0.5">
            Cada perfil tiene su propio resume y configuración de búsqueda.
          </p>
        </div>
        <button
          onClick={onAddProfile}
          className="btn-primary text-xs py-1.5 px-3 flex items-center gap-1">
          + Nuevo perfil
        </button>
      </div>

      {masters.length === 0 ? (
        <div className="text-center py-8 text-gray-300">
          <p className="text-3xl mb-2">📄</p>
          <p className="text-sm">No hay perfiles todavía.</p>
          <button onClick={onAddProfile} className="btn-primary text-sm mt-3">
            Crear primer perfil
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          {masters.map((p) => (
            <ProfileCard
              key={p.id}
              profile={p}
              isActive={p.id === master?.id}
              onActivate={() => handleActivate(p.id)}
              onDelete={() => onProfileDeleted(p.id)}
              onUpdated={onProfileUpdated}
            />
          ))}
        </div>
      )}
    </div>
  );
}
