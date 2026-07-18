import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: "#0D1117",
        elevated: "#11161D",
        card: "#161B22",
        active: "#21262D",
        panel: "#1C222B",
        line: "#30363D",
        primary: "#E6EDF3",
        secondary: "#8B949E",
        muted: "#6E7681",
        accent: "#3B82F6",
        accentHover: "#2563EB",
        accentSoft: "#60A5FA",
        success: "#22C55E",
        warning: "#F59E0B",
        danger: "#EF4444",
        twitch: "#3B82F6",
      },
      boxShadow: {
        soft: "0 12px 32px rgba(0, 0, 0, 0.22)",
      },
    },
  },
  plugins: [],
};

export default config;
