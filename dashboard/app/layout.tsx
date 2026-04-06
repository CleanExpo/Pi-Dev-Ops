import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Pi CEO — Solo DevOps",
  description: "Agentic harness for Claude Max. Build → Deploy → Repeat.",
  openGraph: {
    title: "Pi CEO",
    description: "Solo DevOps Tool powered by Claude Max",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-pi-dark text-pi-cream font-barlow antialiased">
        {children}
      </body>
    </html>
  );
}
