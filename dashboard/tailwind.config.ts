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
        bg:     "#0A0A0A",
        panel:  "#111111",
        term:   "#0E0E0E",
        border: "#252525",
        muted:  "#888888",
        dim:    "#AAAAAA",
        text:   "#F0EDE8",
        orange: "#E8751A",
        green:  "#4CAF82",
        red:    "#EF4444",
        yellow: "#FFD166",
        blue:   "#6B8CFF",
      },
      fontFamily: {
        mono:    ["'IBM Plex Mono'", "monospace"],
        display: ["'Bebas Neue'", "sans-serif"],
        body:    ["'Barlow'", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
