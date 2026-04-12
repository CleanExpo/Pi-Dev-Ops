"use client";
// components/ThemeToggle.tsx — sun/moon toggle persisted to localStorage

import { useEffect, useState } from "react";

export default function ThemeToggle() {
  const [theme, setTheme] = useState<"dark" | "light">("light");

  useEffect(() => {
    const stored = localStorage.getItem("pi-theme");
    const initial = stored === "dark" ? "dark" : "light";
    setTheme(initial);
  }, []);

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    localStorage.setItem("pi-theme", next);
    document.documentElement.className = next;
  }

  return (
    <button
      onClick={toggle}
      title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      className="font-mono text-[13px] transition-all hover:opacity-80"
      style={{
        color: "var(--c-text)",
        padding: "4px 10px",
        lineHeight: "1",
        background: "rgba(128,120,112,0.12)",
        border: "1px solid var(--c-border)",
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
