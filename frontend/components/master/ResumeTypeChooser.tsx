"use client";
import { useEffect, useState } from "react";
import { listResumeProfiles, type ResumeProfile } from "@/lib/api";

// Lets the user pick a ready-made structured resume type (Nivel 2) instead of
// uploading a Word file. Picking one routes to /generar with it preselected.
export function ResumeTypeChooser() {
  const [profiles, setProfiles] = useState<ResumeProfile[]>([]);

  useEffect(() => {
    listResumeProfiles().then(setProfiles).catch(() => setProfiles([]));
  }, []);

  if (profiles.length === 0) return null;

  return (
    <div className="mb-5">
      <p className="text-sm font-medium text-gray-700 mb-1">Elige un CV tipo por área</p>
      <p className="text-xs text-gray-400 mb-3">
        Plantillas profesionales por carrera, con el formato correcto para cada área. El sistema lo
        adapta a cada oferta — sin romper el diseño. Luego personalizas tu información.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {profiles.map((p) => (
          <a
            key={p.profile_id}
            href={`/generar?profile=${encodeURIComponent(p.profile_id)}`}
            className="block border border-gray-200 rounded-xl p-4 hover:border-indigo-400 hover:bg-indigo-50/40 transition-all"
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
            <div className="text-xs text-indigo-600 mt-2 font-medium">Usar este →</div>
          </a>
        ))}
      </div>
    </div>
  );
}
