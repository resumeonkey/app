"use client";
import { useState } from "react";

export function NavBar() {
  const [open, setOpen] = useState(false);

  return (
    <nav className="bg-white border-b border-gray-200 sticky top-0 z-50 shadow-sm">
      <div className="px-4 py-3 flex items-center justify-between gap-4">
        <a href="/" className="font-bold text-indigo-600 text-lg flex items-center gap-2 flex-shrink-0">
          <span className="text-xl">🐵</span> Resumonkey
        </a>
        {/* Desktop nav */}
        <div className="hidden sm:flex gap-4 text-sm font-medium">
          <a href="/" className="text-gray-600 hover:text-indigo-600 transition-colors">Adaptar</a>
          <a href="/generar" className="text-gray-600 hover:text-indigo-600 transition-colors">Elegir CV tipo</a>
          <a href="/history" className="text-gray-600 hover:text-indigo-600 transition-colors">Historial</a>
        </div>
        {/* Mobile hamburger */}
        <button
          className="sm:hidden p-2 rounded-lg text-gray-600 hover:text-indigo-600 hover:bg-gray-100 transition-colors"
          onClick={() => setOpen(!open)}
          aria-label="Abrir menú"
        >
          <span className="text-xl leading-none select-none">{open ? "✕" : "☰"}</span>
        </button>
      </div>
      {/* Mobile dropdown */}
      {open && (
        <div className="sm:hidden border-t border-gray-100 bg-white px-4 py-3 flex flex-col gap-1">
          <a
            href="/"
            className="text-gray-700 hover:text-indigo-600 hover:bg-gray-50 px-3 py-2 rounded-lg transition-colors font-medium"
            onClick={() => setOpen(false)}
          >
            Adaptar
          </a>
          <a
            href="/generar"
            className="text-gray-700 hover:text-indigo-600 hover:bg-gray-50 px-3 py-2 rounded-lg transition-colors font-medium"
            onClick={() => setOpen(false)}
          >
            Elegir CV tipo
          </a>
          <a
            href="/history"
            className="text-gray-700 hover:text-indigo-600 hover:bg-gray-50 px-3 py-2 rounded-lg transition-colors font-medium"
            onClick={() => setOpen(false)}
          >
            Historial
          </a>
        </div>
      )}
    </nav>
  );
}
