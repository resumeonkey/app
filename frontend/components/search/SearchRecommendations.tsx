"use client";
import { type SearchRecommendation, type SearchParams } from "@/lib/api";

interface Props {
  recommendations: SearchRecommendation[];
  loading: boolean;
  onSearch: (params: Partial<SearchParams>) => void;
}

const DEFAULT_PARAMS: Partial<SearchParams> = {
  country: "Canada",
  province: "",
  city: "",
  remote: "any",
  job_type: [],
  salary_min: null,
  salary_max: null,
  salary_currency: "CAD",
  company_type: [],
  company_size: [],
  include_keywords: [],
  exclude_keywords: [],
  languages: ["english"],
  date_posted: "any",
  num_results: 8,
  lmia_only: false,
  bilingual_spanish: false,
  ccfta_check: false,
};

export function SearchRecommendations({ recommendations, loading, onSearch }: Props) {
  if (loading) {
    return (
      <div>
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
          💡 Búsquedas recomendadas para tu perfil
        </p>
        <div className="flex gap-3 overflow-x-auto pb-1">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="flex-shrink-0 w-52 h-28 rounded-xl border border-gray-100 bg-gray-50 animate-pulse"
            />
          ))}
        </div>
      </div>
    );
  }

  if (!recommendations.length) return null;

  const handleSelect = (rec: SearchRecommendation) => {
    onSearch({
      ...DEFAULT_PARAMS,
      job_title: rec.title,
      custom_query: rec.keywords,
      experience_level: rec.experience_level,
      industries: rec.industries,
      remote: (rec.remote as SearchParams["remote"]) ?? "any",
    });
  };

  return (
    <div>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
        💡 Búsquedas recomendadas para tu perfil
      </p>
      <div className="flex gap-3 overflow-x-auto pb-2 -mx-1 px-1">
        {recommendations.map((rec, i) => (
          <button
            key={i}
            onClick={() => handleSelect(rec)}
            className="flex-shrink-0 w-56 text-left rounded-xl border border-gray-200 bg-white p-3
                       hover:border-indigo-300 hover:shadow-sm transition-all group"
          >
            {/* Icon + title */}
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-xl leading-none">{rec.icon || "🔍"}</span>
              <span className="font-semibold text-gray-800 text-sm leading-tight group-hover:text-indigo-700 transition-colors">
                {rec.title}
              </span>
            </div>

            {/* Why recommended */}
            <p className="text-[11px] text-gray-500 italic leading-snug mb-2 line-clamp-2">
              {rec.why}
            </p>

            {/* Industries */}
            {rec.industries?.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-2">
                {rec.industries.slice(0, 2).map((ind) => (
                  <span
                    key={ind}
                    className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-600 border border-indigo-100"
                  >
                    {ind}
                  </span>
                ))}
                {rec.remote !== "any" && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-50 text-green-600 border border-green-100">
                    {rec.remote === "remote" ? "🌐 Remote" : "🏢 Hybrid"}
                  </span>
                )}
              </div>
            )}

            {/* CTA */}
            <p className="text-[10px] text-indigo-500 font-medium group-hover:text-indigo-700">
              Buscar →
            </p>
          </button>
        ))}
      </div>
    </div>
  );
}
