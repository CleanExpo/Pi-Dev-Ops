// tailwind.config.ts — Bloomberg terminal design tokens (CSS variable–backed for theming)
import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg:     "var(--c-bg)",
        panel:  "var(--c-panel)",
        term:   "var(--c-term)",
        border: "var(--c-border)",
        text:   "var(--c-text)",
        cream:  "var(--c-cream)",
        muted:  "var(--c-muted)",
        dim:    "var(--c-dim)",
        chrome: "var(--c-chrome)",
        orange: "var(--c-orange)",
        green:  "#4ADE80",
        red:    "#F87171",
        yellow: "#FFD166",
        blue:   "#6B8CFF",
      },
      fontFamily: {
        mono:         ["'IBM Plex Mono'", "monospace"],
        display:      ["'Bebas Neue'", "sans-serif"],
        body:         ["'Barlow'", "sans-serif"],
        condensed:    ["'Barlow Condensed'", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
