"use client";
import { useEffect, useState } from "react";
import { listResumeProfiles, createMasterFromTemplate, type ResumeProfile, type MasterDetail } from "@/lib/api";

interface Props {
  onCreated?: (master: MasterDetail) => void;
}

export function ResumeTypeChooser({ onCreated }: Props) {
  const [profiles, setProfiles] = useState<ResumeProfile[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [profileName, setProfileName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    listResumeProfiles().then(setProfiles).catch(() => setProfiles([]));
    try { setSelected(localStorage.getItem("resumeProfileId")); } catch {}
  }, []);

  const choose = (id: string, area: string) => {
    try { localStorage.setItem("resumeProfileId", id); } catch {}
    setSelected(id);
    setError("");
    // Pre-fill name with area if empty
    if (!profileName) setProfileName(area);
  };

  const handleConfirm = async () => {
    if (!selected) return;
    const name = profileName.trim();
    if (!name) { setError("Ponle un nombre a este perfil."); return; }
    setCreating(true);
    setError("");
    try {
      const master = await createMasterFromTemplate(selected, name);
      onCreated?.(master);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      setError(err?.response?.data?.detail || err?.message || "No se pudo crear el perfil.");
    } finally {
      setCreating(false);
    }
  };

  if (profiles.length === 0) return null;

  return (
    <div className="mb-2">
      <p className="text-sm font-medium text-gray-700 mb-1">Elige un CV tipo por área</p>
      <p className="text-xs text-gray-400 mb-3">
        Plantillas profesionales por carrera. Al confirmar, se crea tu perfil base —
        luego lo adaptas a cada oferta de trabajo específica.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {profiles.map((p) => {
          const active = selected === p.profile_id;
          const area = p.area || p.title;
          return (
            <button
              key={p.profile_id}
              onClick={() => choose(p.profile_id, area)}
              className={`text-left block border rounded-xl p-4 transition-all ${
                active
                  ? "border-indigo-500 bg-indigo-50/60 ring-1 ring-indigo-200"
                  : "border-gray-200 hover:border-indigo-400 hover:bg-indigo-50/40"
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-gray-800 leading-tight">{area}</div>
                {p.format_type && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-indigo-50 text-indigo-600 border border-indigo-200 font-medium whitespace-nowrap">
                    {p.format_type}
                  </span>
                )}
              </div>
              {p.description && <div className="text-xs text-gray-500 mt-1 leading-snug">{p.description}</div>}
              <div className={`text-xs mt-2 font-medium ${active ? "text-indigo-700" : "text-indigo-400"}`}>
                {active ? "✓ Seleccionado" : "Elegir este"}
              </div>
            </button>
          );
        })}
      </div>

      {selected && onCreated && (
        <div className="mt-4 space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Nombre para este perfil
            </label>
            <input
              type="text"
              className="input w-full"
              placeholder="Ej: Francisco — IT, María — Hospitalidad…"
              value={profileName}
              maxLength={60}
              onChange={(e) => { setProfileName(e.target.value); setError(""); }}
            />
            <p className="text-xs text-gray-400 mt-1">
              Úsalo para identificar a quién pertenece o para qué área es.
            </p>
          </div>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2">
              ⚠️ {error}
            </p>
          )}

          <button
            className="btn-primary w-full py-3 text-sm"
            onClick={handleConfirm}
            disabled={creating}
          >
            {creating ? "⟳ Creando perfil base…" : "✓ Crear perfil →"}
          </button>
          <p className="text-xs text-gray-400 text-center">
            Puedes editar el nombre y configurar roles, skills e industrias desde "Mis Perfiles".
          </p>
        </div>
      )}

      {selected && !onCreated && (
        <p className="text-xs text-emerald-700 mt-3">
          ✓ CV tipo seleccionado. Ahora busca trabajo y adapta tu CV a una oferta para descargarlo.
        </p>
      )}
    </div>
  );
}

