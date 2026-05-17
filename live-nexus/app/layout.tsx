import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Unite Group Nexus — Live Meeting Notes",
  description: "Live in-meeting visual aid for Unite Group sales calls.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="bg-bg text-ink h-full antialiased">
      <body className="font-body min-h-full flex flex-col">{children}</body>
    </html>
  );
}
