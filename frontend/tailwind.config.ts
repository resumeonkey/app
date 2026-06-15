import type { Config } from "tailwindcss";

// SoyManada "Iris & Ivory" identity. `indigo` is remapped to the iris purple
// scale so the app's existing indigo-* classes instantly adopt the brand,
// plus dedicated iris/gold/ivory tokens for new work.
const iris = {
  50:  "#F8F5FF",
  100: "#F2EDFD",
  200: "#E2D6FA",
  300: "#C4B0F0",
  400: "#A07DE0",
  500: "#7B4DC8",
  600: "#5B2D9E",
  700: "#3D1A78",
  800: "#2D1057",
  900: "#1E0A3C",
};

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        indigo: iris,
        iris,
        gold: { DEFAULT: "#C9953A", light: "#FDF3E1", border: "#F0D89A" },
        ivory: { DEFAULT: "#FAF8F4", warm: "#F4F0E8", deeper: "#EDE8DC" },
      },
      fontFamily: {
        sans: ["'Plus Jakarta Sans'", "system-ui", "sans-serif"],
        display: ["'Playfair Display'", "Georgia", "serif"],
      },
    },
  },
  plugins: [],
};
export default config;
