// tailwind.config.ts — Zinc design tokens + Inter / JetBrains Mono typography (CSS variable–backed)
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
        background:   "var(--background)",
        panel:        "var(--panel)",
        "panel-hover": "var(--panel-hover)",
        border:       "var(--border)",
        "border-subtle": "var(--border-subtle)",
        text: {
          DEFAULT: "var(--text)",
          muted:   "var(--text-muted)",
          dim:     "var(--text-dim)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          subtle:  "var(--accent-subtle)",
        },
        success: "var(--success)",
        warning: "var(--warning)",
        error:   "var(--error)",
        info:    "var(--info)",
        /* Keep legacy aliases so any remaining Bloomberg refs don't hard-break */
        "c-orange": "var(--accent)",
        "c-border": "var(--border)",
        "c-panel":  "var(--panel)",
        "c-bg":     "var(--background)",
        "c-text":   "var(--text)",
        "c-chrome": "var(--text-dim)",
        "c-muted":  "var(--text-muted)",
      },
      borderRadius: {
        lg:   "var(--radius)",
        md:   "var(--radius)",
        sm:   "calc(var(--radius) - 2px)",
        full: "9999px",
      },
      fontFamily: {
        sans:      ["var(--font-sans)", "system-ui", "sans-serif"],
        mono:      ["var(--font-mono)", "'JetBrains Mono'", "'IBM Plex Mono'", "monospace"],
        inter:     ["var(--font-sans)", "system-ui", "sans-serif"],
        "inter-mono": ["var(--font-mono)", "monospace"],
        /* Back-compat aliases — kept so legacy classNames like `font-geist-mono`
           (PhaseTracker.tsx) keep rendering the current Inter/JetBrains Mono stack
           without touching every component. Remove in a future cleanup sprint. */
        geist:     ["var(--font-sans)", "system-ui", "sans-serif"],
        "geist-mono": ["var(--font-mono)", "monospace"],
        display:   ["var(--font-sans)", "system-ui", "sans-serif"],
        body:      ["var(--font-sans)", "system-ui", "sans-serif"],
        condensed: ["var(--font-sans)", "system-ui", "sans-serif"],
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
