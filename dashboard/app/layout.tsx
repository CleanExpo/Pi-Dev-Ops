// app/layout.tsx — root layout with Geist font + ToastProvider
import type { Metadata } from "next";
import { headers } from "next/headers";
import Script from "next/script";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { ToastProvider } from "@/components/Toast";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono" });

export const metadata: Metadata = {
  title: "Pi CEO — Autonomous Dev Platform",
  description: "GitHub repo analysis engine powered by Claude + TAO framework",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const nonce = (await headers()).get("x-nonce") ?? "";
  return (
    <html lang="en" className={`${geist.variable} ${geistMono.variable}`}>
      <head>
        {/* Reads localStorage before first paint to avoid theme flash */}
        <Script
          id="theme-init"
          strategy="beforeInteractive"
          {...(nonce ? { nonce } : {})}
        >{`(function(){try{var t=localStorage.getItem('pi-theme');document.documentElement.className=(t==='dark'?'dark':'light')+' ${geist.variable} ${geistMono.variable}';}catch(e){}})();`}</Script>
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
