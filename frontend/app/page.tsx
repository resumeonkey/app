"use client";
import { useEffect, useState } from "react";
import { getActiveMaster, runJobSearch, type MasterDetail, type Adaptation, type SearchParams, type SearchResponse } from "@/lib/api";
// job_url → Adaptation map for this session
type AdaptedJobsMap = Record<string, Adaptation>;
import { MasterUpload } from "@/components/master/MasterUpload";
import { MasterStatus } from "@/components/master/MasterStatus";
import { JobForm } from "@/components/job/JobForm";
import { AdaptationResult } from "@/components/result/AdaptationResult";
import { ContextPanel } from "@/components/context/ContextPanel";
import { SearchPanel } from "@/components/search/SearchPanel";
import { SearchResults } from "@/components/search/SearchResults";

type AppView   = "upload_master" | "adapt" | "result";
type InputMode = "search" | "manual";

export default function HomePage() {
  const [master, setMaster]         = useState<MasterDetail | null>(null);
  const [loading, setLoading]       = useState(true);
  const [view, setView]             = useState<AppView>("adapt");
  const [adaptationId, setAdaptId]  = useState<string | null>(null);
  const [inputMode, setInputMode]   = useState<InputMode>("manual");

  // Search state
  const [searchLoading, setSearchLoading]   = useState(false);
  const [searchResult, setSearchResult]     = useState<SearchResponse | null>(null);
  const [searchError, setSearchError]       = useState("");
  const [lastSearchParams, setLastParams]   = useState<SearchParams | null>(null);
  // Tracks which job URLs have been adapted in this session
  const [adaptedJobs, setAdaptedJobs]       = useState<AdaptedJobsMap>({});

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

  const handleJobAdapted = (jobUrl: string, a: Adaptation) => {
    setAdaptedJobs(prev => ({ ...prev, [jobUrl]: a }));
  };

  const handleSearch = async (params: SearchParams) => {
    setSearchLoading(true);
    setSearchError("");
    setSearchResult(null);
    setLastParams(params);
    try {
      const result = await runJobSearch(params);
      setSearchResult(result);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      setSearchError(err?.response?.data?.detail || err?.message || "Error al buscar empleos.");
    } finally {
      setSearchLoading(false);
    }
  };

  if (loading) {
    return <div className="text-center py-20 text-gray-400">Cargando…</div>;
  }

  return (
    <div className="space-y-6">
      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="text-center space-y-2">
        <h1 className="text-3xl font-bold text-gray-800">📄 Resume Adapter</h1>
        <p className="text-gray-500">
          Adapta tu resume canadiense a cada oferta — sin romper el formato.
        </p>
      </div>

      {/* ── Master section ───────────────────────────────────────────────────── */}
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

      {/* ── Personal context repository ──────────────────────────────────────── */}
      {view !== "result" && <ContextPanel />}

      {/* ── Job input section ────────────────────────────────────────────────── */}
      {view === "adapt" && master && (
        <div className="card p-6">
          <div className="flex items-start justify-between mb-1">
            <h2 className="text-base font-semibold text-gray-700">2. Nueva oferta laboral</h2>
            {/* Mode switcher */}
            <div className="flex gap-1 p-1 bg-gray-100 rounded-xl">
              <button
                onClick={() => { setInputMode("search"); setSearchResult(null); }}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                  inputMode === "search"
                    ? "bg-white shadow-sm text-indigo-700"
                    : "text-gray-500 hover:text-gray-700"
                }`}
              >
                🔍 Buscar empleos
              </button>
              <button
                onClick={() => setInputMode("manual")}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                  inputMode === "manual"
                    ? "bg-white shadow-sm text-gray-800"
                    : "text-gray-500 hover:text-gray-700"
                }`}
              >
                ✍️ Agregar oferta
              </button>
            </div>
          </div>

          <p className="text-sm text-gray-400 mb-5">
            {inputMode === "search"
              ? "Busca ofertas según tu perfil y parámetros. El sistema las analiza y puntúa por compatibilidad."
              : "Pega el texto de la oferta o extráela desde una URL. El sistema adaptará tu resume."}
          </p>

          {/* ── Search mode ─────────────────────────────────────────────── */}
          {inputMode === "search" && (
            <div className="space-y-5">
              <SearchPanel onSearch={handleSearch} loading={searchLoading} />

              {searchError && (
                <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2">
                  ⚠️ {searchError}
                </p>
              )}

              {searchResult && (
                <SearchResults
                  results={searchResult.results}
                  queriesUsed={searchResult.queries_used}
                  llmProvider={lastSearchParams?.llm_provider ?? "anthropic"}
                  llmModel={lastSearchParams?.llm_model ?? "claude-haiku-4-5"}
                  onAdapted={handleAdaptationCreated}
                  adaptedJobs={adaptedJobs}
                  onJobAdapted={handleJobAdapted}
                />
              )}
            </div>
          )}

          {/* ── Manual mode ─────────────────────────────────────────────── */}
          {inputMode === "manual" && (
            <JobForm onCreated={handleAdaptationCreated} />
          )}
        </div>
      )}

      {view === "adapt" && !master && (
        <div className="card p-6 text-center text-gray-400 py-12">
          <p className="text-3xl mb-3">👆</p>
          <p>Primero carga tu resume maestro canadiense para poder adaptar.</p>
        </div>
      )}

      {/* ── Result view ─────────────────────────────────────────────────────── */}
      {view === "result" && adaptationId && (
        <AdaptationResult
          adaptationId={adaptationId}
          onReset={() => { setView("adapt"); setAdaptId(null); }}
        />
      )}
    </div>
  );
}
