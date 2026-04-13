// app/layout.tsx — root layout with ToastProvider (RA-518: async for nonce)
import type { Metadata } from "next";
import { headers } from "next/headers";
import Script from "next/script";
import "./globals.css";
import { ToastProvider } from "@/components/Toast";

export const metadata: Metadata = {
  title: "Pi CEO — Autonomous Dev Platform",
  description: "GitHub repo analysis engine powered by Claude + TAO framework",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const nonce = (await headers()).get("x-nonce") ?? "";
  return (
    <html lang="en">
      <head>
        {/* Reads localStorage before first paint to avoid theme flash — static inline script */}
        <Script
          id="theme-init"
          strategy="beforeInteractive"
          {...(nonce ? { nonce } : {})}
        >{`(function(){try{var t=localStorage.getItem('pi-theme');document.documentElement.className=t==='dark'?'dark':'light';}catch(e){}})();`}</Script>
      </head>
      <body className="bg-bg text-text font-body min-h-screen flex flex-col" {...(nonce ? { "data-nonce": nonce } : {})}>
        <ToastProvider>
          {children}
        </ToastProvider>
      </body>
    </html>
  );
}
