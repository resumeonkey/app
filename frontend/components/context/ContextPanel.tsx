"use client";
import { useEffect, useRef, useState } from "react";
import {
  listContexts, addTextContext, addFileContext,
  toggleContext, deleteContext, type UserContext,
} from "@/lib/api";

export function ContextPanel() {
  const [items, setItems]         = useState<UserContext[]>([]);
  const [loading, setLoading]     = useState(true);
  const [mode, setMode]           = useState<"text" | "file" | null>(null);
  const [title, setTitle]         = useState("");
  const [text, setText]           = useState("");
  const [file, setFile]           = useState<File | null>(null);
  const [saving, setSaving]       = useState(false);
  const [error, setError]         = useState("");
  const [expanded, setExpanded]   = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    try { setItems(await listContexts()); }
    catch { /* silent */ }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const reset = () => {
    setMode(null); setTitle(""); setText(""); setFile(null); setError("");
  };

  const handleSave = async () => {
    if (!title.trim()) { setError("Agrega un título."); return; }
    if (mode === "text" && !text.trim()) { setError("El texto no puede estar vacío."); return; }
    if (mode === "file" && !file) { setError("Selecciona un archivo."); return; }
    setSaving(true); setError("");
    try {
      if (mode === "text") await addTextContext(title, text);
      else if (mode === "file" && file) await addFileContext(title, file);
      await load();
      reset();
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg || "Error al guardar.");
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async (id: string) => {
    try {
      const updated = await toggleContext(id);
      setItems((prev) => prev.map((c) => (c.id === id ? updated : c)));
    } catch { /* silent */ }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteContext(id);
      setItems((prev) => prev.filter((c) => c.id !== id));
      if (expanded === id) setExpanded(null);
    } catch { /* silent */ }
  };

  const activeCount = items.filter((c) => c.is_active).length;

  return (
    <div className="card p-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-2 mb-4">
        <div>
          <h2 className="text-base font-semibold text-gray-700">
            🗂 Mi Contexto Laboral
          </h2>
          <p className="text-sm text-gray-400 mt-0.5">
            El LLM usa esta información en cada adaptación.
            {activeCount > 0 && (
              <span className="ml-2 text-indigo-500 font-medium">{activeCount} activo{activeCount !== 1 ? "s" : ""}</span>
            )}
          </p>
        </div>
        {mode === null && (
          <div className="flex gap-2">
            <button className="btn-secondary text-xs" onClick={() => setMode("text")}>
              + Pegar texto
            </button>
            <button className="btn-secondary text-xs" onClick={() => setMode("file")}>
              + Subir archivo
            </button>
          </div>
        )}
      </div>

      {/* Add form */}
      {mode !== null && (
        <div className="bg-gray-50 rounded-xl p-4 mb-4 space-y-3">
          <input
            type="text"
            placeholder={mode === "text" ? "Ej: LinkedIn Bio, Logros, Objetivos…" : "Nombre para este archivo"}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="input w-full text-sm"
          />

          {mode === "text" && (
            <textarea
              rows={6}
              placeholder="Pega aquí tu bio, experiencia extra, objetivos, logros, lo que quieras que el LLM conozca sobre ti…"
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="input w-full text-sm resize-y"
            />
          )}

          {mode === "file" && (
            <div
              className="border-2 border-dashed border-gray-200 rounded-lg p-6 text-center cursor-pointer hover:border-indigo-300 transition-colors"
              onClick={() => fileRef.current?.click()}
            >
              {file ? (
                <p className="text-sm font-medium text-indigo-600">{file.name}</p>
              ) : (
                <>
                  <p className="text-2xl mb-1">📄</p>
                  <p className="text-sm text-gray-400">Haz clic para seleccionar</p>
                  <p className="text-xs text-gray-300 mt-1">.pdf · .docx · .txt</p>
                </>
              )}
              <input
                ref={fileRef}
                type="file"
                accept=".pdf,.docx,.txt"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </div>
          )}

          {error && <p className="text-xs text-red-500">{error}</p>}

          <div className="flex gap-2">
            <button
              className="btn-primary text-sm flex-1"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? "Guardando…" : "Guardar"}
            </button>
            <button className="btn-secondary text-sm" onClick={reset}>
              Cancelar
            </button>
          </div>
        </div>
      )}

      {/* List */}
      {loading ? (
        <p className="text-sm text-gray-400 text-center py-4">Cargando…</p>
      ) : items.length === 0 ? (
        <div className="text-center py-8 text-gray-300">
          <p className="text-3xl mb-2">🗃</p>
          <p className="text-sm">Sin contexto guardado aún.</p>
          <p className="text-xs mt-1">Agrega tu bio de LinkedIn, logros, objetivos de carrera…</p>
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((ctx) => (
            <div
              key={ctx.id}
              className={`rounded-lg border transition-colors ${
                ctx.is_active ? "border-indigo-100 bg-indigo-50/40" : "border-gray-100 bg-gray-50 opacity-60"
              }`}
            >
              <div className="flex items-center gap-3 px-4 py-3">
                {/* Toggle */}
                <button
                  onClick={() => handleToggle(ctx.id)}
                  className={`w-9 h-5 rounded-full transition-colors flex-shrink-0 relative ${
                    ctx.is_active ? "bg-indigo-500" : "bg-gray-300"
                  }`}
                  title={ctx.is_active ? "Desactivar" : "Activar"}
                >
                  <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${
                    ctx.is_active ? "translate-x-4" : "translate-x-0.5"
                  }`} />
                </button>

                {/* Title + preview */}
                <button
                  className="flex-1 text-left min-w-0"
                  onClick={() => setExpanded(expanded === ctx.id ? null : ctx.id)}
                >
                  <p className="text-sm font-medium text-gray-700 truncate">{ctx.title}</p>
                  <p className="text-xs text-gray-400 truncate">{ctx.content.slice(0, 80)}…</p>
                </button>

                {/* Delete */}
                <button
                  onClick={() => handleDelete(ctx.id)}
                  className="text-gray-300 hover:text-red-400 transition-colors text-lg flex-shrink-0"
                  title="Eliminar"
                >
                  ×
                </button>
              </div>

              {/* Expanded content */}
              {expanded === ctx.id && (
                <div className="px-4 pb-3">
                  <pre className="text-xs text-gray-600 bg-white rounded-lg p-3 whitespace-pre-wrap max-h-48 overflow-y-auto border border-gray-100">
                    {ctx.content}
                  </pre>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
