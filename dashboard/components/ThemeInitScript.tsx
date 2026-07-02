"use client";

import { useSyncExternalStore } from "react";

function subscribe(): () => void {
  return () => {};
}

function getServerSnapshot(): boolean {
  return true;
}

function getClientSnapshot(): boolean {
  return false;
}

interface ThemeInitScriptProps {
  nonce: string;
  code: string;
}

/**
 * Inline theme bootstrap — runs once before paint to avoid FOUC.
 * React 19 warns if <script> is rendered during client re-renders; emit only
 * on the server + hydration pass (MUI InitColorSchemeScript pattern).
 */
export function ThemeInitScript({ nonce, code }: ThemeInitScriptProps) {
  const emitScript = useSyncExternalStore(subscribe, getClientSnapshot, getServerSnapshot);
  if (!emitScript) return null;

  return (
    <script
      id="theme-init"
      nonce={nonce || undefined}
      suppressHydrationWarning
      dangerouslySetInnerHTML={{ __html: code }}
    />
  );
}
