"use client";
import { useCallback, useEffect, useState } from "react";
import {
  getActiveMaster,
  listMasters,
  listAdaptations,
  runJobSearch,
  suggestSearchParams,
  getSavedUrls,
  type MasterDetail,
  type MasterSummary,
  type Adaptation,
  type SearchParams,
  type SearchResponse,
  type SearchRecommendation,
} from "@/lib/api";
// MasterStatus kept for reference — replaced by ProfilesPanel
import { MasterUpload } from "@/components/master/MasterUpload";
import { ProfilesPanel } from "@/components/master/ProfilesPanel";
import { JobForm } from "@/components/job/JobForm";
import { AdaptationResult } from "@/components/result/AdaptationResult";
import { ContextPanel } from "@/components/context/ContextPanel";
import { SearchPanel } from "@/components/search/SearchPanel";
import { SearchResults } from "@/components/search/SearchResults";
import { SearchRecommendations } from "@/components/search/SearchRecommendations";
import { AdaptationHistory } from "@/components/history/AdaptationHistory";

type AppView      = "upload_master" | "adapt" | "result";
type InputMode    = "search" | "manual";
type AdaptedJobsMap = Record<string, Adaptation>;

export default function HomePage() {
  const [master, setMaster]         = useState<MasterDetail | null>(null);
  const [masters, setMasters]       = useState<MasterSummary[]>([]);
  const [loading, setLoading]       = useState(true);
  const [view, setView]             = useState<AppView>("adapt");
  const [adaptationId, setAdaptId]  = useState<string | null>(null);
  const [inputMode, setInputMode]   = useState<InputMode>("manual");

  // Search state
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchResult, setSearchResult]   = useState<SearchResponse | null>(null);
  const [searchError, setSearchError]     = useState("");
  const [lastSearchParams, setLastParams] = useState<SearchParams | null>(null);

  // History: job_url → Adaptation (seeded from DB on mount)
  const [adaptedJobs, setAdaptedJobs] = useState<AdaptedJobsMap>({});

  // Saved jobs: url → saved_job_id
  const [savedUrls, setSavedUrls] = useState<Record<string, string>>({});

  // Personalized search recommendations
  const [recommendations, setRecommendations] = useState<SearchRecommendation[]>([]);
  const [recsLoading, setRecsLoading]         = useState(false);
  const [recsLoaded, setRecsLoaded]           = useState(false);

  // ── Helpers (declared before useEffect so they're in scope) ─────────────────

  const loadRecommendations = useCallback(() => {
    setRecsLoading(true);
    setRecsLoaded(false);
    suggestSearchParams()
      .then(({ recommendations: recs }) => setRecommendations(recs ?? []))
      .catch(() => setRecommendations([]))
      .finally(() => { setRecsLoading(false); setRecsLoaded(true); });
  }, []);

  // ── On mount: load master + history in parallel, then recommendations ────────

  useEffect(() => {
    Promise.all([
      getActiveMaster().catch(() => null),
      listAdaptations().catch((): Adaptation[] => []),
      listMasters().catch((): MasterSummary[] => []),
      getSavedUrls().catch((): Record<string, string> => ({})),
    ]).then(([m, adaptations, allMasters, savedUrlMap]) => {
      setMaster(m);
      setMasters(allMasters);

      // Seed history from DB (only entries that carry a job_url)
      if (adaptations.length > 0) {
        const map: AdaptedJobsMap = {};
        for (const a of adaptations) {
          if (a.job_url) map[a.job_url] = a;
        }
        setAdaptedJobs(map);
      }

      setSavedUrls(savedUrlMap);
      if (m) loadRecommendations();
    }).finally(() => setLoading(false));
  }, [loadRecommendations]);

  // ── Event handlers ───────────────────────────────────────────────────────────

  const handleMasterUploaded = (m: MasterDetail) => {
    setMaster(m);
    // Refresh the profiles list after upload
    listMasters().catch((): MasterSummary[] => []).then(setMasters);
    setView("adapt");
    loadRecommendations();
  };

  const handleProfileActivated = async (id: string) => {
    const [newActive, allMasters] = await Promise.all([
      getActiveMaster().catch(() => null),
      listMasters().catch((): MasterSummary[] => []),
    ]);
    setMaster(newActive);
    setMasters(allMasters);
    if (newActive) loadRecommendations();
  };

  const handleProfileDeleted = (id: string) => {
    setMasters((prev) => prev.filter((m) => m.id !== id));
    // If the deleted profile was active, clear master
    if (master?.id === id) {
      getActiveMaster().catch(() => null).then(setMaster);
    }
  };

  const handleProfileUpdated = (updated: MasterSummary) => {
    setMasters((prev) => prev.map((m) => m.id === updated.id ? { ...m, ...updated } : m));
    if (master?.id === updated.id) {
      setMaster((prev) => prev ? { ...prev, ...updated } : prev);
    }
  };

  const handleAdaptationCreated = (a: Adaptation) => {
    setAdaptId(a.id);
    setView("result");
  };

  const handleJobAdapted = (jobUrl: string, a: Adaptation) => {
    setAdaptedJobs(prev => ({ ...prev, [jobUrl]: a }));
  };

  const handleViewFromHistory = (a: Adaptation) => {
    setAdaptId(a.id);
    setView("result");
  };

  const handleUpdateAdaptation = (a: Adaptation) => {
    if (a.job_url) {
      setAdaptedJobs(prev => ({ ...prev, [a.job_url!]: a }));
    }
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

  // ── Render ───────────────────────────────────────────────────────────────────

  if (loading) {
    return <div className="text-center py-20 text-gray-400">Cargando…</div>;
  }

  return (
    <div className="space-y-6">
      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="text-center space-y-2">
        <h1 className="text-3xl font-bold text-gray-800">🐵 Resumonkey</h1>
        <p className="text-gray-500">
          Adapta tu resume canadiense a cada oferta — sin romper el formato.
        </p>
        <div className="flex justify-center gap-3 pt-1">
          <a href="/saved" className="text-sm text-amber-600 hover:text-amber-700 font-medium flex items-center gap-1">
            🔖 Guardados
            {Object.keys(savedUrls).length > 0 && (
              <span className="bg-amber-100 text-amber-700 border border-amber-300 rounded-full text-[10px] px-1.5 py-0.5 font-bold">
                {Object.keys(savedUrls).length}
              </span>
            )}
          </a>
          <a href="/history" className="text-sm text-gray-400 hover:text-gray-600">
            Historial
          </a>
        </div>
      </div>

      {/* ── Profiles / Master section ───────────────────────────────────────── */}
      {view !== "result" && (
        <>
          {view === "upload_master" ? (
            <div className="card p-6">
              <h2 className="text-base font-semibold text-gray-700 mb-1">
                {master ? "➕ Agregar nuevo perfil" : "1. Carga tu primer resume"}
              </h2>
              <p className="text-sm text-gray-400 mb-5">
                Cada perfil tiene su propio resume y configuración de búsqueda (roles objetivo, exclusiones, industrias).
              </p>
              <MasterUpload onUploaded={handleMasterUploaded} />
              {master && (
                <button className="btn-secondary mt-3 text-sm" onClick={() => setView("adapt")}>
                  ← Cancelar
                </button>
              )}
            </div>
          ) : (
            <ProfilesPanel
              master={master}
              masters={masters}
              onAddProfile={() => setView("upload_master")}
              onProfileActivated={handleProfileActivated}
              onProfileDeleted={handleProfileDeleted}
              onProfileUpdated={handleProfileUpdated}
            />
          )}
        </>
      )}

      {/* ── Personal context repository ──────────────────────────────────────── */}
      {view !== "result" && <ContextPanel />}

      {/* ── Adaptation history (seeded from DB, updates on new adaptations) ─── */}
      {view !== "result" && (
        <AdaptationHistory
          adaptedJobs={adaptedJobs}
          onView={handleViewFromHistory}
          onUpdate={handleUpdateAdaptation}
        />
      )}

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
              {/* Personalized recommendations */}
              <SearchRecommendations
                recommendations={recommendations}
                loading={recsLoading}
                onSearch={handleSearch}
                onRetry={recsLoaded ? loadRecommendations : undefined}
              />

              <SearchPanel
                onSearch={handleSearch}
                loading={searchLoading}
                masters={masters.map((m) => ({
                  id: m.id,
                  profile_name: m.profile_name,
                  original_filename: m.original_filename,
                  is_active: m.is_active,
                }))}
                activeMasterId={master?.id ?? null}
              />

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
                  savedUrls={savedUrls}
                  onSavedChange={(url, id) =>
                    setSavedUrls((prev) => {
                      const next = { ...prev };
                      if (id) next[url] = id; else delete next[url];
                      return next;
                    })
                  }
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
