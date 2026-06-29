"use client";
// components/ThemeToggle.tsx — sun/moon toggle persisted to localStorage

import { useEffect, useState } from "react";

export default function ThemeToggle() {
  // Dark-first, matching the layout's theme-init script. Starting in "light"
  // desynced the button from the actual <html> class, so the first click set
  // the theme to whatever it already was (a visible no-op).
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    // Trust the real DOM state set by the init script (it has already applied
    // localStorage + the dark-first default), not a fresh re-read.
    const current = document.documentElement.classList.contains("light") ? "light" : "dark";
    setTheme(current);
  }, []);

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    localStorage.setItem("pi-theme", next);
    // Toggle ONLY the theme class via classList — overwriting className wiped
    // the next/font variable classes the init script also sets on <html>,
    // breaking the fonts after a toggle.
    const html = document.documentElement;
    html.classList.toggle("dark", next === "dark");
    html.classList.toggle("light", next === "light");
  }

  return (
    <button
      onClick={toggle}
      title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      className="font-mono text-[13px] transition-all hover:opacity-80"
      style={{
        color: "var(--text)",
        padding: "4px 10px",
        lineHeight: "1",
        background: "rgba(128,120,112,0.12)",
        border: "1px solid var(--border)",
        borderRadius: "3px",
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        gap: "5px",
        fontSize: "12px",
        letterSpacing: "0.08em",
      }}
    >
      <span style={{ fontSize: "14px" }}>{theme === "dark" ? "☀" : "☾"}</span>
      <span>{theme === "dark" ? "LIGHT" : "DARK"}</span>
    </button>
  );
}
