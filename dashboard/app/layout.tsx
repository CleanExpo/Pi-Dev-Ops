// app/layout.tsx — root layout (no nav — nav lives in (main)/layout.tsx)
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Pi CEO — Autonomous Dev Platform",
  description: "GitHub repo analysis engine powered by Claude + TAO framework",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-bg text-text font-body min-h-screen flex flex-col">
        {children}
      </body>
    </html>
  );
}
