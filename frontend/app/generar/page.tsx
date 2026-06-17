"use client";
import { useEffect, useState } from "react";
import {
  listResumeProfiles,
  generateAndDownloadResume,
  extractJobFromUrl,
  type ResumeProfile,
} from "@/lib/api";

const LLM_OPTIONS = [
  { provider: "groq", model: "llama-3.3-70b-versatile", label: "Llama 3.3 70B · Groq (gratis)" },
  { provider: "anthropic", model: "claude-sonnet-4-6", label: "Claude Sonnet · Anthropic" },
  { provider: "gemini", model: "gemini-2.0-flash", label: "Gemini 2.0 Flash · Google" },
];

export default function GenerarPage() {
  const [profiles, setProfiles] = useState<ResumeProfile[]>([]);
  const [profileId, setProfileId] = useState("hr_technology");
  const [template, setTemplate] = useState<"classic" | "iris">("classic");
  const [jobDesc, setJobDesc] = useState("");
  const [jobUrl, setJobUrl] = useState("");
  const [extracting, setExtracting] = useState(false);
  const [instructions, setInstructions] = useState("");
  const [llm, setLlm] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleExtractLink = async () => {
    if (!jobUrl.trim()) return;
    setExtracting(true);
    setError(null);
    try {
      const res = await extractJobFromUrl(
        jobUrl.trim(),
        LLM_OPTIONS[llm].provider,
        LLM_OPTIONS[llm].model,
      );
      setJobDesc(res.job_description || "");
      if (!res.job_description) setError("No se pudo leer la oferta desde ese link. Pega el texto manualmente.");
    } catch {
      setError("No se pudo leer la oferta desde ese link. Pega el texto manualmente.");
    } finally {
      setExtracting(false);
    }
  };

  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get("profile");
    listResumeProfiles()
      .then((p) => {
        setProfiles(p);
        if (fromUrl && p.find((x) => x.profile_id === fromUrl)) setProfileId(fromUrl);
        else if (p.length && !p.find((x) => x.profile_id === profileId)) setProfileId(p[0].profile_id);
      })
      .catch(() => setProfiles([]));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    try {
      await generateAndDownloadResume({
        profile_id: profileId,
        template,
        job_description: jobDesc.trim(),
        user_instructions: instructions.trim(),
        llm_provider: LLM_OPTIONS[llm].provider,
        llm_model: LLM_OPTIONS[llm].model,
      });
    } catch (e) {
      setError("No se pudo generar el CV. Reintenta en unos segundos.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">🧬 Generar CV</h1>
        <p className="text-gray-500 text-sm mt-1">
          Crea tu CV desde una plantilla limpia. Si pegas una oferta, lo adapta a ese puesto —
          sin romper el formato, porque el documento se genera desde cero.
        </p>
      </div>

      <div className="card p-5 space-y-5">
        {/* Profile */}
        <div>
          <label className="label">Perfil</label>
          <select className="input" value={profileId} onChange={(e) => setProfileId(e.target.value)}>
            {profiles.length === 0 && <option value="hr_technology">HR Technology</option>}
            {profiles.map((p) => (
              <option key={p.profile_id} value={p.profile_id}>
                {p.name} — {p.title}
              </option>
            ))}
          </select>
        </div>

        {/* Template */}
        <div>
          <label className="label">Plantilla</label>
          <div className="flex gap-2">
            {([
              { val: "classic", label: "Classic (azul)" },
              { val: "iris", label: "Iris (SoyManada)" },
            ] as const).map((t) => (
              <button
                key={t.val}
                onClick={() => setTemplate(t.val)}
                className={`px-4 py-2 rounded-lg border text-sm transition-all ${
                  template === t.val
                    ? "bg-indigo-100 border-indigo-400 text-indigo-700 font-medium"
                    : "border-gray-200 text-gray-500 hover:border-indigo-300"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* Job link → extract */}
        <div>
          <label className="label">Link de la oferta (opcional)</label>
          <div className="flex gap-2">
            <input
              className="input flex-1"
              placeholder="https://… (LinkedIn, Job Bank, careers…)"
              value={jobUrl}
              onChange={(e) => setJobUrl(e.target.value)}
            />
            <button className="btn-secondary text-sm px-3" disabled={extracting} onClick={handleExtractLink}>
              {extracting ? "Leyendo…" : "Leer link"}
            </button>
          </div>
        </div>

        {/* Job description */}
        <div>
          <label className="label">Texto de la oferta</label>
          <textarea
            className="textarea h-32"
            placeholder="Pega el texto completo de la oferta (o usa 'Leer link' arriba). El CV se adapta a este puesto. Déjalo vacío para descargar el CV tipo tal cual."
            value={jobDesc}
            onChange={(e) => setJobDesc(e.target.value)}
          />
        </div>

        {/* Instructions */}
        <div>
          <label className="label">Instrucciones extra (opcional)</label>
          <input
            className="input"
            placeholder="Ej: enfatiza la experiencia en SuccessFactors reporting"
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
          />
        </div>

        {/* Model */}
        <div>
          <label className="label">Modelo de IA (para adaptar)</label>
          <div className="flex flex-wrap gap-2">
            {LLM_OPTIONS.map((opt, i) => (
              <button
                key={i}
                onClick={() => setLlm(i)}
                className={`px-3 py-1.5 rounded-lg border text-xs transition-all ${
                  llm === i
                    ? "border-indigo-500 bg-indigo-50 text-indigo-700 font-medium"
                    : "border-gray-200 text-gray-500 hover:border-gray-300"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2">
            ⚠️ {error}
          </p>
        )}

        <button className="btn-primary w-full justify-center" disabled={loading} onClick={handleGenerate}>
          {loading
            ? "Generando…"
            : jobDesc.trim()
            ? "🧬 Adaptar y descargar CV"
            : "⬇ Descargar CV maestro"}
        </button>
      </div>
    </main>
  );
}
