/** @type {import('next').NextConfig} */
const nextConfig = {
  // output: 'export' removed — Vercel handles Next.js natively (no static export needed)
  // For local dev: run `npm run dev` (port 3000) + uvicorn (port 8000) separately
  images: { unoptimized: true },
};
export default nextConfig;
