// app/layout.tsx — root layout with Inter + JetBrains Mono + ToastProvider
import type { Metadata } from "next";
import { headers } from "next/headers";
import localFont from "next/font/local";
import "./globals.css";
import { ToastProvider } from "@/components/Toast";
import { ThemeInitScript } from "@/components/ThemeInitScript";

// Inter: primary UI font. JetBrains Mono: code/terminal companion.
// CSS variables are named generically (--font-sans / --font-mono) so future
// font swaps don't require touching component classNames.
// Self-hosted (app/fonts: the latin woff2 files Google serves, SIL OFL 1.1; the
// licence and copyright notice for each family ship in public/fonts/OFL-*.txt) rather
// than loaded from Google: the Google loader downloads during `next build`, and a
// failed download fails the whole Turbopack build (main CI run 36682119471, 30/09/2026).
const sans = localFont({
  src: [{ path: "./fonts/inter-latin-var.woff2", weight: "100 900", style: "normal" }],
  variable: "--font-sans",
  display: "swap",
});
const mono = localFont({
  src: [{ path: "./fonts/jetbrains-mono-latin-var.woff2", weight: "100 800", style: "normal" }],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Pi CEO — Autonomous Dev Platform",
  description: "GitHub repo analysis engine powered by Claude + TAO framework",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const nonce = (await headers()).get("x-nonce") ?? "";
  // Dark-first per DESIGN.md ("light mode is never the default") + Phill's black-base directive.
  // Light only renders when the user has explicitly toggled it (pi-theme === 'light').
  const themeInit = `(function(){try{var t=localStorage.getItem('pi-theme');document.documentElement.className=(t==='light'?'light':'dark')+' ${sans.variable} ${mono.variable}';}catch(e){}})();`;
  return (
    // suppressHydrationWarning on <html>: the theme-init script below intentionally
    // mutates <html>.className from localStorage before React hydrates. Without this
    // attribute, React would warn about the className mismatch. Standard pattern for
    // localStorage-driven themes (next-themes uses the same technique).
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <body
        className="bg-background text-text font-sans min-h-screen flex flex-col"
        suppressHydrationWarning
        {...(nonce ? { "data-nonce": nonce } : {})}
      >
        <ThemeInitScript nonce={nonce} code={themeInit} />
        <ToastProvider>
          {children}
        </ToastProvider>
      </body>
    </html>
  );
}
