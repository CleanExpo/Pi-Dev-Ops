// tailwind.config.ts — Bloomberg terminal design tokens
import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#0A0A0A",
        panel: "#0F0F0F",
        term: "#0C0C0C",
        border: "#1A1A1A",
        muted: "#444444",
        dim: "#666666",
        text: "#F0EDE8",
        orange: "#E8751A",
        green: "#4CAF82",
        red: "#EF4444",
        yellow: "#FFD166",
        blue: "#6B8CFF",
      },
      fontFamily: {
        mono: ["'IBM Plex Mono'", "monospace"],
        display: ["'Bebas Neue'", "sans-serif"],
        body: ["'Barlow'", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
