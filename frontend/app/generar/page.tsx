"use client";
import { ResumeTypeChooser } from "@/components/master/ResumeTypeChooser";

export default function ElegirCVPage() {
  return (
    <main className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">🧬 Elige tu CV tipo</h1>
        <p className="text-gray-500 text-sm mt-1">
          Elige el formato de tu área. Después busca trabajo y adapta tu CV a una oferta específica —
          ahí se genera y descarga, ya optimizado para ese puesto.
        </p>
      </div>
      <ResumeTypeChooser />
    </main>
  );
}
