"use client";
import { useEffect, useState } from "react";
import { listResumeProfiles, type ResumeProfile } from "@/lib/api";

// Pure selector of a career-area resume type. Picking one stores the choice and
// sends the user into the job search. The CV is generated/downloaded later, once
// an offer is ready and adapted — never here.
export function ResumeTypeChooser() {
  const [profiles, setProfiles] = useState<ResumeProfile[]>([]);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    listResumeProfiles().then(setProfiles).catch(() => setProfiles([]));
    try {
      setSelected(localStorage.getItem("resumeProfileId"));
    } catch {}
  }, []);

  const choose = (id: string) => {
    try {
      localStorage.setItem("resumeProfileId", id);
    } catch {}
    setSelected(id);
  };

  if (profiles.length === 0) return null;

  return (
    <div className="mb-2">
      <p className="text-sm font-medium text-gray-700 mb-1">Elige un CV tipo por área</p>
      <p className="text-xs text-gray-400 mb-3">
        Plantillas profesionales por carrera, con el formato correcto para cada área. Elige una y
        luego busca trabajo: tu CV se adaptará y descargará para cada oferta específica.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {profiles.map((p) => {
          const active = selected === p.profile_id;
          return (
            <button
              key={p.profile_id}
              onClick={() => choose(p.profile_id)}
              className={`text-left block border rounded-xl p-4 transition-all ${
                active
                  ? "border-indigo-500 bg-indigo-50/60 ring-1 ring-indigo-200"
                  : "border-gray-200 hover:border-indigo-400 hover:bg-indigo-50/40"
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-gray-800 leading-tight">{p.area || p.title}</div>
                {p.format_type && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-indigo-50 text-indigo-600 border border-indigo-200 font-medium whitespace-nowrap">
                    {p.format_type}
                  </span>
                )}
              </div>
              {p.description && <div className="text-xs text-gray-500 mt-1 leading-snug">{p.description}</div>}
              <div className={`text-xs mt-2 font-medium ${active ? "text-indigo-700" : "text-indigo-600"}`}>
                {active ? "✓ Seleccionado" : "Elegir este"}
              </div>
            </button>
          );
        })}
      </div>
      {selected && (
        <p className="text-xs text-emerald-700 mt-3">
          ✓ CV tipo seleccionado. Ahora busca trabajo y adapta tu CV a una oferta para descargarlo.
        </p>
      )}
    </div>
  );
}
