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
      /* ── Bloomberg terminal tokens ── */
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
        /* shadcn semantic tokens */
        background:  "hsl(var(--background))",
        foreground:  "hsl(var(--foreground))",
        card: {
          DEFAULT:     "hsl(var(--card))",
          foreground:  "hsl(var(--card-foreground))",
        },
        popover: {
          DEFAULT:     "hsl(var(--popover))",
          foreground:  "hsl(var(--popover-foreground))",
        },
        primary: {
          DEFAULT:     "hsl(var(--primary))",
          foreground:  "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT:     "hsl(var(--secondary))",
          foreground:  "hsl(var(--secondary-foreground))",
        },
        accent: {
          DEFAULT:     "hsl(var(--accent))",
          foreground:  "hsl(var(--accent-foreground))",
        },
        destructive: {
          DEFAULT:     "hsl(var(--destructive))",
          foreground:  "hsl(var(--destructive-foreground))",
        },
        input:  "hsl(var(--input))",
        ring:   "hsl(var(--ring))",
      },
      borderRadius: {
        lg:  "var(--radius)",
        md:  "var(--radius)",
        sm:  "var(--radius)",
      },
      fontFamily: {
        mono:         ["'IBM Plex Mono'", "monospace"],
        display:      ["'Bebas Neue'", "sans-serif"],
        body:         ["'Barlow'", "sans-serif"],
        condensed:    ["'Barlow Condensed'", "sans-serif"],
        sans:         ["'Barlow'", "sans-serif"],  /* shadcn default font */
      },
      backgroundImage: {
        "ambient-glow": "radial-gradient(ellipse at 0% 0%, rgba(232,117,26,0.04) 0%, transparent 50%)",
      },
      keyframes: {
        "fade-in": {
          "0%":   { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-orange": {
          "0%, 100%": { opacity: "1" },
          "50%":      { opacity: "0.5" },
        },
      },
      animation: {
        "fade-in":      "fade-in 0.3s ease-out",
        "pulse-orange": "pulse-orange 2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
