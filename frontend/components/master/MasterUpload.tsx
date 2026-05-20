"use client";
import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { uploadMaster, type MasterDetail } from "@/lib/api";

interface Props {
  onUploaded: (master: MasterDetail) => void;
}

export function MasterUpload({ onUploaded }: Props) {
  const [file, setFile]   = useState<File | null>(null);
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState("");

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted[0]) setFile(accepted[0]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
      "application/pdf": [".pdf"],
    },
    maxFiles: 1,
  });

  const handleUpload = async () => {
    if (!file) { setError("Selecciona un archivo."); return; }
    setError("");
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (notes) fd.append("notes", notes);
      const master = await uploadMaster(fd);
      onUploaded(master);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      setError(err?.response?.data?.detail || err?.message || "Error al subir el archivo.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-5">
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors
          ${isDragActive ? "border-indigo-500 bg-indigo-50" : "border-gray-300 hover:border-indigo-400 hover:bg-gray-50"}
          ${file ? "border-green-400 bg-green-50" : ""}
        `}
      >
        <input {...getInputProps()} />
        {file ? (
          <div className="space-y-1">
            <p className="text-3xl">✅</p>
            <p className="font-semibold text-green-700">{file.name}</p>
            <p className="text-xs text-gray-400">{(file.size / 1024).toFixed(0)} KB</p>
            <button
              className="text-xs text-red-500 hover:underline mt-1"
              onClick={(e) => { e.stopPropagation(); setFile(null); }}
            >
              Quitar
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            <p className="text-4xl">📄</p>
            <p className="font-medium text-gray-700">
              {isDragActive ? "Suelta aquí" : "Arrastra tu resume canadiense o haz clic"}
            </p>
            <p className="text-xs text-gray-400">DOCX o PDF · máx 20 MB</p>
            <p className="text-xs text-indigo-500 font-medium mt-1">
              💡 Recomendado: DOCX — preserva el formato exacto al exportar
            </p>
          </div>
        )}
      </div>

      <div>
        <label className="label">Notas opcionales (contexto de este resume)</label>
        <textarea
          className="textarea h-16"
          placeholder="Ej: Versión en inglés, enfocada en roles de producto, actualizada mayo 2025"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </div>

      {error && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2">⚠️ {error}</p>
      )}

      <button className="btn-primary w-full py-3" onClick={handleUpload} disabled={loading || !file}>
        {loading ? "Procesando y guardando..." : "💾 Guardar como resume maestro"}
      </button>
    </div>
  );
}
