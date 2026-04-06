"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import Sidebar from "@/components/Sidebar";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    api
      .me()
      .then(() => setChecking(false))
      .catch(() => router.replace("/"));
  }, [router]);

  if (checking) {
    return (
      <div className="min-h-screen bg-pi-dark flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <span className="inline-block w-6 h-6 border-2 border-pi-border border-t-pi-orange rounded-full animate-spin" />
          <p className="font-mono text-xs text-pi-muted">Verifying session…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-pi-dark">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">{children}</div>
    </div>
  );
}
