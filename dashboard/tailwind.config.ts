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
        term:   "#0C0C0C",
        border: "#2A2727",
        text:   "#F0EDE8",
        cream:  "#E8E4DE",
        muted:  "#C8C5C0",
        dim:    "#A8A5A0",
        chrome: "#888480",
        orange: "#E8751A",
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
