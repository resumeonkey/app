"use client";
import { useEffect, useState } from "react";
import { getActiveMaster, type MasterDetail, type Adaptation } from "@/lib/api";
import { MasterUpload } from "@/components/master/MasterUpload";
import { MasterStatus } from "@/components/master/MasterStatus";
import { JobForm } from "@/components/job/JobForm";
import { AdaptationResult } from "@/components/result/AdaptationResult";
import { ContextPanel } from "@/components/context/ContextPanel";

type AppView = "upload_master" | "adapt" | "result";

export default function HomePage() {
  const [master, setMaster]       = useState<MasterDetail | null>(null);
  const [loading, setLoading]     = useState(true);
  const [view, setView]           = useState<AppView>("adapt");
  const [adaptationId, setAdaptId] = useState<string | null>(null);

  useEffect(() => {
    getActiveMaster()
      .then(setMaster)
      .catch(() => setMaster(null))
      .finally(() => setLoading(false));
  }, []);

  const handleMasterUploaded = (m: MasterDetail) => {
    setMaster(m);
    setView("adapt");
  };

  const handleAdaptationCreated = (a: Adaptation) => {
    setAdaptId(a.id);
    setView("result");
  };

  if (loading) {
    return <div className="text-center py-20 text-gray-400">Cargando…</div>;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="text-center space-y-2">
        <h1 className="text-3xl font-bold text-gray-800">📄 Resume Adapter</h1>
        <p className="text-gray-500">
          Adapta tu resume canadiense a cada oferta — sin romper el formato.
        </p>
      </div>

      {/* Master section */}
      {view !== "result" && (
        <>
          {!master || view === "upload_master" ? (
            <div className="card p-6">
              <h2 className="text-base font-semibold text-gray-700 mb-1">
                {master ? "🔄 Reemplazar resume maestro" : "1. Carga tu resume maestro canadiense"}
              </h2>
              <p className="text-sm text-gray-400 mb-5">
                Este documento es la fuente única de verdad. Todas las adaptaciones se generan a partir de él.
              </p>
              <MasterUpload onUploaded={handleMasterUploaded} />
              {master && (
                <button className="btn-secondary mt-3 text-sm" onClick={() => setView("adapt")}>
                  ← Cancelar
                </button>
              )}
            </div>
          ) : (
            <MasterStatus master={master} onReplace={() => setView("upload_master")} />
          )}
        </>
      )}

      {/* Personal context repository */}
      {view !== "result" && <ContextPanel />}

      {/* Job input / Result */}
      {view === "adapt" && master && (
        <div className="card p-6">
          <h2 className="text-base font-semibold text-gray-700 mb-1">2. Nueva oferta laboral</h2>
          <p className="text-sm text-gray-400 mb-5">
            El sistema adaptará solo el contenido necesario del resume maestro para esta oferta.
          </p>
          <JobForm onCreated={handleAdaptationCreated} />
        </div>
      )}

      {view === "adapt" && !master && (
        <div className="card p-6 text-center text-gray-400 py-12">
          <p className="text-3xl mb-3">👆</p>
          <p>Primero carga tu resume maestro canadiense para poder adaptar.</p>
        </div>
      )}

      {view === "result" && adaptationId && (
        <AdaptationResult
          adaptationId={adaptationId}
          onReset={() => { setView("adapt"); setAdaptId(null); }}
        />
      )}
    </div>
  );
}
