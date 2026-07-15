import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#18181b",
        panel: "#ffffff",
        twitch: "#7047eb",
      },
      boxShadow: {
        soft: "0 16px 50px rgba(24, 24, 27, 0.08)",
      },
    },
  },
  plugins: [],
};

export default config;

