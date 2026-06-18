"use client";
import { useRouter } from "next/navigation";
import { ResumeTypeChooser } from "@/components/master/ResumeTypeChooser";

export default function ElegirCVPage() {
  const router = useRouter();
  return (
    <main className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">🧬 Elige tu CV tipo</h1>
        <p className="text-gray-500 text-sm mt-1">
          Elige el formato de tu área. Al confirmar, se crea tu perfil base y puedes
          adaptar tu CV a cada oferta específica.
        </p>
      </div>
      <ResumeTypeChooser onCreated={() => router.push("/")} />
    </main>
  );
}
