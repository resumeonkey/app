import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Resume Adapter",
  description: "Adapt your Canadian resume to any job — without changing the format.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body className="bg-gray-50 min-h-screen antialiased text-gray-900">
        <nav className="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-6 sticky top-0 z-50 shadow-sm">
          <a href="/" className="font-bold text-indigo-600 text-lg flex items-center gap-2">
            <span className="text-xl">📄</span> Resume Adapter
          </a>
          <div className="flex gap-4 text-sm font-medium ml-4">
            <a href="/" className="text-gray-600 hover:text-indigo-600 transition-colors">Adaptar</a>
            <a href="/history" className="text-gray-600 hover:text-indigo-600 transition-colors">Historial</a>
          </div>
        </nav>
        <main className="max-w-5xl mx-auto px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
