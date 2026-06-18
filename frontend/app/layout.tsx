import type { Metadata } from "next";
import "./globals.css";
import { NavBar } from "@/components/NavBar";

export const metadata: Metadata = {
  title: "Resumonkey",
  description: "Adapta tu resume canadiense a cada oferta — sin romper el formato. Una app de SoyManada.",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body className="bg-ivory min-h-screen antialiased text-gray-900">
        <NavBar />
        <main className="max-w-5xl mx-auto px-4 py-6 sm:py-8">{children}</main>
      </body>
    </html>
  );
}
