// app/layout.tsx — root layout with Inter + JetBrains Mono + ToastProvider
import type { Metadata } from "next";
import { headers } from "next/headers";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { ToastProvider } from "@/components/Toast";

// Inter: primary UI font. JetBrains Mono: code/terminal companion.
// CSS variables are named generically (--font-sans / --font-mono) so future
// font swaps don't require touching component classNames.
const sans = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: "Pi CEO — Autonomous Dev Platform",
  description: "GitHub repo analysis engine powered by Claude + TAO framework",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const nonce = (await headers()).get("x-nonce") ?? "";
  const themeInit = `(function(){try{var t=localStorage.getItem('pi-theme');document.documentElement.className=(t==='dark'?'dark':'light')+' ${sans.variable} ${mono.variable}';}catch(e){}})();`;
  return (
    // suppressHydrationWarning on <html>: the theme-init script below intentionally
    // mutates <html>.className from localStorage before React hydrates. Without this
    // attribute, React would warn about the className mismatch. Standard pattern for
    // localStorage-driven themes (next-themes uses the same technique).
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        {/* Raw <script> (not next/script) so suppressHydrationWarning can be applied
            directly. Placed in <head> so it runs synchronously before hydration,
            preventing theme flash. */}
        <script
          id="theme-init"
          nonce={nonce || undefined}
          suppressHydrationWarning
          dangerouslySetInnerHTML={{ __html: themeInit }}
        />
      </head>
      <body
        className="bg-background text-text font-sans min-h-screen flex flex-col"
        {...(nonce ? { "data-nonce": nonce } : {})}
      >
        <ToastProvider>
          {children}
        </ToastProvider>
      </body>
    </html>
  );
}
