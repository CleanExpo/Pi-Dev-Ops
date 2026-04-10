// app/layout.tsx — root layout with ToastProvider (RA-518: async for nonce)
import type { Metadata } from "next";
import { headers } from "next/headers";
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
      <body className="bg-bg text-text font-body min-h-screen flex flex-col" {...(nonce ? { "data-nonce": nonce } : {})}>
        <ToastProvider>
          {children}
        </ToastProvider>
      </body>
    </html>
  );
}
