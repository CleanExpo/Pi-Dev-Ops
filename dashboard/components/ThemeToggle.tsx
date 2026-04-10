"use client";
// components/ThemeToggle.tsx — sun/moon toggle persisted to localStorage

import { useEffect, useState } from "react";

export default function ThemeToggle() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const stored = localStorage.getItem("pi-theme");
    const initial = stored === "light" ? "light" : "dark";
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
      className="font-mono text-[13px] transition-opacity hover:opacity-70"
      style={{
        borderLeft: "1px solid var(--c-border)",
        color: "var(--c-chrome)",
        padding: "0 12px",
        lineHeight: "40px",
        background: "none",
        cursor: "pointer",
      }}
    >
      {theme === "dark" ? "☀" : "☾"}
    </button>
  );
}
